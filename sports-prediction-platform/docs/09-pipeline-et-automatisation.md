# 09 — Data pipeline, qualité, orchestration et alertes

---

## 1. Le pipeline de bout en bout

```
   ┌────────────┐
   │ API/Fichier│
   └──────┬─────┘
          │  1. INGESTION — connecteur par provider, aucune transformation
          ▼
   ┌──────────────────────────────────────────────┐
   │ raw.observations (JSONB + fetched_at)         │  append-only, immuable
   └──────┬───────────────────────────────────────┘
          │  2. VALIDATION SYNTAXIQUE — schéma attendu, types, champs requis
          ▼
   ┌──────────────────────────────────────────────┐
   │ Quarantaine si invalide → ops.data_quality    │
   └──────┬───────────────────────────────────────┘
          │  3. RÉSOLUTION D'ENTITÉS — mapping provider → canonique
          ▼
   ┌──────────────────────────────────────────────┐
   │ raw.entity_mappings                           │
   └──────┬───────────────────────────────────────┘
          │  4. CANONISATION — écriture bitemporelle, résolution de conflits
          ▼
   ┌──────────────────────────────────────────────┐
   │ core.*  stats.*  market.*                     │
   └──────┬───────────────────────────────────────┘
          │  5. VALIDATION SÉMANTIQUE — cohérence métier, plausibilité
          ▼
   ┌──────────────────────────────────────────────┐
   │ ops.data_quality_checks                       │
   └──────┬───────────────────────────────────────┘
          │  6. FEATURE ENGINEERING — point-in-time, versionné
          ▼
   ┌──────────────────────────────────────────────┐
   │ features.values (as_of_ts, feature_hash)      │
   └──────┬───────────────────────────────────────┘
          │  7. INFÉRENCE — ensemble + calibration
          ▼
   ┌──────────────────────────────────────────────┐
   │ ml.predictions + ml.explanations              │
   └──────┬───────────────────────────────────────┘
          │  8. VALORISATION — de-vig, EV, seuils
          ▼
   ┌──────────────────────────────────────────────┐
   │ ml.value_signals                              │
   └──────┬───────────────────────────────────────┘
          │  9. DIFFUSION
          ▼
   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
   │  API REST    │     │  Dashboard   │     │  Alertes     │
   └──────────────┘     └──────────────┘     └──────────────┘
```

---

## 2. Gestion des problèmes de données

### 2.1 Données manquantes

La question n'est jamais « comment imputer ? » mais « **pourquoi c'est
manquant ?** ». Trois régimes, trois traitements :

| Régime | Exemple | Traitement |
| --- | --- | --- |
| **MCAR** (manquant au hasard) | Panne d'API sur un lot de matchs | Imputation standard + flag |
| **MAR** (dépend d'observables) | Pas de xG en 2ᵉ division (le provider ne couvre pas) | Imputation conditionnelle au niveau de ligue + flag |
| **MNAR** (dépend de l'inobservé) | Pas de compo publiée parce que le club cache une absence | **Ne pas imputer.** Le fait même d'être manquant est un signal : le modéliser comme catégorie |

Politiques par famille de données :

| Donnée manquante | Politique |
| --- | --- |
| Statistique avancée (xG) | Shrinkage vers la moyenne de ligue, pondéré par `n_matches` + flag |
| Cote d'un bookmaker | Ignorer ce book dans le consensus, ajuster `n_bookmakers` |
| **Toutes les cotes** | **Bloquer la prédiction** : pas de marché = pas de comparaison possible |
| Composition | Utiliser le modèle de composition probable, marquer `lineup_status = 'unknown'` |
| Météo | Valeurs saisonnières moyennes du stade + flag |
| Blessures | Supposer l'effectif du dernier match disponible + dégrader le score de qualité |
| Statistiques d'un promu | Shrinkage vers la moyenne de division inférieure ajustée |

### 2.2 Doublons

Trois niveaux de déduplication :

1. **Payload identique** : hash SHA-256, rejet à l'insertion (index unique
   sur `(provider, entity_kind, provider_entity_id, payload_sha256,
   fetched_at)`).
2. **Même match, deux fois dans `core`** : détection par
   (date ± 36 h, compétition, paire d'équipes). Une contrainte
   d'exclusion applicative empêche la création d'un doublon.
3. **Doublon sémantique inter-providers** : deux providers créent deux
   `match_id` différents pour le même match. C'est le rôle de
   `raw.entity_mappings` ; détection par le même critère + revue manuelle.

### 2.3 Pannes d'API

| Situation | Comportement |
| --- | --- |
| Timeout / 5xx | **Retry exponentiel** : 4 tentatives (2 s, 8 s, 32 s, 128 s) + jitter |
| 429 (rate limit) | Respecter `Retry-After` ; token bucket côté client pour ne pas y arriver |
| 4xx (sauf 429) | Pas de retry. Alerte : c'est une erreur de notre côté |
| Échec persistant | **Circuit breaker** : le provider est marqué dégradé pendant 15 min |
| Provider indisponible et secondaire présent | Bascule sur le secondaire, marqué dans `provider_id` |
| Aucun provider disponible | Prédiction non produite. **Jamais de prédiction sur données périmées sans le dire** |

Le principe transversal : **dégrader explicitement plutôt que silencieusement**.
Une prédiction produite avec des données de 5 jours doit porter
`data_quality = 0.35`, pas être présentée comme normale.

### 2.4 Données en retard

Un provider qui publie les stats avancées à J+3 impose deux règles :

1. Le backtest doit respecter ce délai — d'où `recorded_at`.
2. En production, une prédiction à J-1 ne peut pas utiliser les stats du
   match de J-2. **Le lag est une propriété déclarée de chaque source** et le
   moteur de features le fait respecter.

```yaml
sources:
  opta_match_stats:
    typical_lag_hours: 8
    max_lag_hours: 72
    revision_window_hours: 96      # au-delà, la donnée est considérée figée
```

### 2.5 Sources en conflit

Le cas le plus fréquent : deux providers donnent un xG différent, ou un score
différent.

Politique de résolution, dans l'ordre :

```
1. Si un provider est déclaré autoritaire pour ce champ → il gagne
   (ex. : le score officiel de la fédération prime toujours)
2. Sinon, si l'écart est faible (< tolérance du champ) → moyenne pondérée
   par trust_score
3. Sinon → le provider au trust_score le plus élevé gagne,
   ET l'écart est enregistré dans ops.source_conflicts
4. Si l'écart dépasse un seuil critique (ex. score différent)
   → quarantaine du match + alerte + revue manuelle
```

**Le conflit est toujours tracé, jamais résolu silencieusement.** Le taux de
conflits par provider est une métrique de qualité : un provider dont le taux
de conflit augmente voit son `trust_score` baisser automatiquement.

### 2.6 Corrections historiques

Quand un provider corrige le passé :

```
1. La nouvelle valeur est insérée (nouvelle ligne, nouveau recorded_at)
2. L'ancienne reçoit superseded_at
3. Les feature_hash des prédictions concernées sont recalculés
4. Si un hash change → événement ops : "révision rétroactive détectée"
5. Les backtests affectés sont marqués comme "à rejouer"
```

Le point 5 est crucial : un backtest exécuté avant une correction massive
n'est plus valide, et le système doit le savoir.

---

## 3. Contrôles de qualité

### 3.1 Les cinq familles

| Famille | Exemples de contrôles | Sévérité |
| --- | --- | --- |
| **Complétude** | Tous les matchs de la journée sont présents ; chaque match a ≥ 5 bookmakers | error |
| **Validité** | `0 ≤ possession ≤ 100` ; `shots_on_target ≤ shots` ; `odds > 1.0` | critical |
| **Cohérence** | `Σ buts des événements = score final` ; somme des minutes ≈ 990 (football) | error |
| **Plausibilité** | xG d'équipe ∈ [0, 8] ; pace NBA ∈ [88, 112] ; overround ∈ [0.5 %, 25 %] | warning |
| **Fraîcheur** | Dernier succès de chaque source < intervalle attendu | error |

### 3.2 Contrôles statistiques (dérive)

Au-delà des règles fixes, un contrôle de **distribution** :

```
Pour chaque feature surveillée :
    PSI (Population Stability Index) entre la fenêtre courante (30 j)
    et la fenêtre d'entraînement

    PSI < 0.10  → stable
    0.10 – 0.25 → dérive modérée, surveiller
    PSI > 0.25  → dérive forte, ALERTE : envisager un ré-entraînement
```

```
PSI = Σ_b ( actual_b − expected_b ) · ln( actual_b / expected_b )
```

Ce contrôle attrape les changements silencieux : un provider qui modifie sa
définition de xG, une règle de jeu qui change, une nouvelle ligue au
comportement différent.

### 3.3 Le score de qualité des données (par match)

```
DataQuality = Σ_c  w_c · score_c
```

| Composant `c` | Poids `w_c` | Score |
| --- | --- | --- |
| Compositions | 0.25 | 1.0 confirmée · 0.6 probable · 0.2 inconnue |
| Statistiques récentes | 0.20 | `min(n_matchs_avec_stats / 8, 1)` |
| Cotes | 0.20 | `min(n_bookmakers / 8, 1) × fraîcheur` |
| Blessures / absences | 0.15 | 1.0 si < 24 h · 0.5 si < 72 h · 0.1 sinon |
| Historique | 0.10 | `min(n_matchs_historiques / 30, 1)` |
| Météo | 0.05 | 1.0 si prévision < 12 h |
| Ratings | 0.05 | `1 − exp(−n_matchs/10)` |

Affichage (cf. section 26 du cahier des charges) :

```
Lineup confirmed       ✓   1.00
Recent statistics      ✓   1.00   (8/8 matchs)
Odds updated           ✓   0.95   (11 books, il y a 4 min)
Weather available      ✓   1.00
Player injuries        ✓   1.00   (mis à jour il y a 6 h)
Historical data        ✓   1.00   (30+ matchs)
Ratings converged      ~   0.78   (12 matchs cette saison)
─────────────────────────────────
Data Quality : 94 %
```

**Usage strict** : sous `DataQuality < 0.75`, aucun signal de value n'est
émis. La prédiction reste affichée, avec un bandeau explicite.

---

## 4. Orchestration

### 4.1 Comparaison des orchestrateurs

| | **Cron + scripts** | **Celery Beat** | **Prefect 3** | **Dagster** | **Airflow** |
| --- | --- | --- | --- | --- | --- |
| Courbe d'apprentissage | Nulle | Faible | **Faible** | Moyenne | Élevée |
| Observabilité | Aucune | Faible | **Bonne** | Excellente | Bonne |
| Retries / dépendances | À coder | Basiques | **Natifs** | Natifs | Natifs |
| Notion d'actif de données | Non | Non | Partielle | **Native** | Non |
| Coût d'infrastructure | 0 | Faible | Faible (worker + API) | Moyen | **Élevé** |
| Backfill | Manuel | Manuel | Bon | **Excellent** | Bon |
| Pertinence MVP | Non | Non | **Oui** | Bon choix V2 | Non |

**Recommandation : Prefect 3.** Les flows sont du Python ordinaire
(décorateurs), ce qui évite la double écriture ; l'observabilité est
suffisante ; le coût d'exploitation est faible. Dagster est meilleur sur la
notion de *data asset* et de lignage — c'est le candidat naturel quand le
nombre de sources dépassera la dizaine.

Airflow est écarté : le rapport puissance/coût d'exploitation ne se justifie
pas à cette échelle.

### 4.2 Les flows

| Flow | Déclencheur | Fréquence | Durée cible |
| --- | --- | --- | --- |
| `sync_fixtures` | cron | 1× / 6 h | < 2 min |
| `sync_results` | cron | 1× / 15 min (fenêtre de match) | < 1 min |
| `sync_match_stats` | événement `match_finished` + retard | H+4, H+24, H+72 | < 5 min |
| `sync_injuries` | cron | 4× / jour | < 3 min |
| `sync_lineups` | cron dense à T-90 → T-30 min | 1× / 2 min | < 30 s |
| `sync_weather` | cron | T-72 h, T-24 h, T-3 h | < 1 min |
| `sync_odds` | cron adaptatif (§ doc 08) | 1 min → 6 h | < 60 s |
| `compute_ratings` | après `sync_results` | 1× / jour | < 5 min |
| `compute_player_impact` | cron | 1× / semaine | < 30 min |
| `compute_features` | avant chaque run de prédiction | 2× / match | < 2 min |
| `run_predictions` | T-24 h et T-55 min | 2× / match | < 3 min |
| `evaluate_predictions` | après `sync_results` | 1× / jour | < 5 min |
| `recalibrate` | cron | 1× / mois | < 20 min |
| `retrain` | manuel + proposition automatique | ~1× / trimestre | < 2 h |
| `data_quality_sweep` | cron | 1× / heure | < 2 min |
| `refresh_materialized_views` | cron | 1× / 2 min | < 10 s |

### 4.3 Le déclenchement événementiel qui compte le plus

Le run `T-55 min` ne doit pas être purement horaire : il doit être **déclenché
par la publication des compositions**.

```
sync_lineups détecte une compo officielle
        │
        ├──▶ événement lineup_published(match_id)
        │
        ├──▶ recalcul des features d'effectif
        ├──▶ run de prédiction immédiat
        ├──▶ comparaison avec la prédiction précédente
        └──▶ si |Δp| > 3 pts → alerte "prédiction modifiée"
```

C'est le moment où le système a le plus de valeur ajoutée : les compos sont
publiques mais tous les bookmakers ne réagissent pas instantanément sur tous
les marchés.

### 4.4 Idempotence et rejouabilité

Toutes les tâches sont idempotentes :

- L'ingestion déduplique par hash.
- La canonisation est un upsert sur des clés naturelles.
- Le calcul de features est déterministe à `as_of_ts` fixé.
- Les prédictions sont insérées avec un `run_id` distinct — on n'écrase
  jamais, on ajoute.

Conséquence pratique : **rejouer n'importe quel flow sur n'importe quelle
période est sûr.** C'est ce qui rend le backfill trivial et le debug possible.

---

## 5. Alertes

### 5.1 Catalogue

| Alerte | Condition | Sévérité | Canal |
| --- | --- | --- | --- |
| **Mouvement de cote significatif** | `|z| > 2.5` sur un marché suivi | info | Dashboard + push |
| **Steam move** | ≥ 60 % des books, même sens, z > 3 | warning | Push |
| **Composition publiée** | Nouvelle compo officielle | info | Dashboard |
| **Joueur clé absent** | Absent avec `PITS > seuil` | warning | Push |
| **Prédiction fortement modifiée** | `|Δp| > 3 pts` entre deux runs | warning | Push |
| **Signal de value** | Toutes conditions du doc 06 §4.2 remplies | info | Push |
| **Signal invalidé** | Un signal actif ne passe plus les conditions | warning | Push |
| **Données périmées** | `ops.data_freshness_status.is_stale` | error | Slack/email |
| **Échec d'ingestion répété** | 3 échecs consécutifs | error | Slack/email |
| **Dérive de features** | PSI > 0.25 | warning | Email hebdo |
| **Dégradation de calibration** | ECE > 0.04 sur 30 j glissants | **critical** | Email + suspension des signaux |
| **Conflit de sources critique** | Scores divergents | error | Revue manuelle |
| **Drawdown** | −15 % puis −25 % | warning / critical | Email |

### 5.2 Anti-spam

Une plateforme qui alerte trop n'est plus lue. Trois mécanismes :

1. **Déduplication** : clé `dedupe_key` + fenêtre horaire (index unique en
   base, doc 04).
2. **Hystérésis** : un signal doit franchir le seuil de 2.5 % pour s'activer
   mais ne se désactive qu'en dessous de 1.5 %. Sans cela, une cote qui
   oscille autour du seuil génère 40 alertes.
3. **Regroupement** : les alertes de même famille sur le même match sont
   fusionnées en une notification.

### 5.3 L'alerte la plus importante

**La dégradation de calibration est la seule alerte qui suspend
automatiquement le système.** Si l'ECE sur 30 jours glissants dépasse 0.04,
les signaux de value sont désactivés jusqu'à revue humaine.

Raison : un modèle décalibré produit des EV faux dans le *bon* sens
apparent — il semble trouver plus d'opportunités, précisément parce qu'il est
sur-confiant. Sans ce garde-fou, la dégradation du modèle se manifeste par
une **augmentation** du nombre de signaux, ce qui est le pire signal
d'alarme possible pour un opérateur humain.
