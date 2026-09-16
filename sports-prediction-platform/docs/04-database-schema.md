# 04 — Schéma de base de données

> Le DDL complet et **exécutable** est dans [`../sql/schema.sql`](../sql/schema.sql).
> Il a été appliqué et testé sur PostgreSQL 16 : 53 tables, 4 tables
> partitionnées, 4 vues, 142 index. Les contraintes d'intégrité ont été
> vérifiées (rejet effectif d'un `shots_on_target > shots`), ainsi que la
> colonne générée `outcome_1x2` et les vues applicatives.

---

## 1. Organisation en schémas

| Schéma | Contenu | Volumétrie | Règle d'écriture |
| --- | --- | --- | --- |
| `raw` | Payloads bruts des providers | **Très forte** | Append-only. `UPDATE`/`DELETE` révoqués |
| `core` | Modèle canonique agnostique au sport | Moyenne | Bitemporel |
| `stats` | Statistiques de match, une table par sport | Forte | Versionné (`recorded_at`/`superseded_at`) |
| `market` | Bookmakers, marchés, cotes | **Très forte** | Append-only pour les snapshots |
| `features` | Feature store, ratings, PITS | Moyenne | Immuable par `as_of_ts` |
| `ml` | Modèles, prédictions, calibration, signaux | Forte | Append-only |
| `bet` | Backtests, paris, bankroll | Faible | Mutable (dénouement) |
| `ops` | Qualité, fraîcheur, alertes, conflits | Faible | Mutable |

**Pourquoi des schémas et pas des préfixes de table** : les droits se posent
par schéma. Le rôle de l'API a `SELECT` sur `core`, `market`, `ml` et rien
sur `raw` ; le rôle d'ingestion a `INSERT` sur `raw` et rien ailleurs. Une
faille dans l'API ne peut pas corrompre l'historique brut.

---

## 2. Bitemporalité : les deux axes du temps

C'est la décision structurante du schéma. Deux horodatages, jamais
confondus :

| Axe | Colonnes | Question à laquelle il répond |
| --- | --- | --- |
| **Temps métier** | `valid_from` / `valid_to` | À quelle période ce fait était-il vrai ? |
| **Temps de connaissance** | `recorded_at` / `superseded_at` | À partir de quand le savions-nous ? |

Exemple concret, une blessure :

```
Le 12 mars à 09h00, le club annonce : "Joueur X, blessé, absent 3 semaines"
  → valid_from = 2026-03-10 (la blessure date du match du 10)
    recorded_at = 2026-03-12 09:00

Le 14 mars à 18h00, correction : "en réalité, absent 6 semaines"
  → l'ancienne ligne reçoit superseded_at = 2026-03-14 18:00
    une nouvelle ligne est insérée avec recorded_at = 2026-03-14 18:00
```

Une prédiction horodatée au 13 mars doit voir la **première** version. La
requête point-in-time canonique est donc toujours de cette forme :

```sql
SELECT DISTINCT ON (player_id)
       *
FROM   core.availabilities
WHERE  player_id = $1
  AND  recorded_at <= $as_of_ts                 -- on ne savait pas plus tard
  AND  (superseded_at IS NULL OR superseded_at > $as_of_ts)
  AND  valid_from <= $as_of_ts
  AND  (valid_to IS NULL OR valid_to >= $as_of_ts)
ORDER  BY player_id, recorded_at DESC;
```

**Ce motif est encapsulé dans une seule fonction du repository.** Aucun autre
code n'a le droit d'écrire ces clauses à la main : c'est la principale source
d'erreurs de fuite, et une fonction unique se teste.

---

## 3. Tables principales — spécifications

### 3.1 `core.matches` — la table centrale

| Colonne | Type | Contrainte | Note |
| --- | --- | --- | --- |
| `match_id` | BIGINT IDENTITY | **PK** | |
| `sport_id` | SMALLINT | **FK** → `core.sports` | Dénormalisé depuis competition pour éviter une jointure sur le chemin chaud |
| `season_id`, `competition_id` | INT | **FK** | |
| `stage`, `matchday` | TEXT, SMALLINT | | |
| `tie_id`, `leg` | BIGINT, SMALLINT | `leg IN (1,2)` | Regroupe aller/retour |
| `kickoff_utc` | TIMESTAMPTZ | **NOT NULL** | Pivot de tout le point-in-time |
| `venue_id` | INT | **FK** | |
| `is_neutral_venue`, `is_behind_closed_doors` | BOOLEAN | | Modulent l'avantage domicile |
| `home_competitor_id`, `away_competitor_id` | BIGINT | **FK**, `home <> away` | |
| `referee_id` | BIGINT | **FK** | |
| `status` | TEXT | `CHECK` sur 7 valeurs | `postponed` exclut le match du dataset |

**Index** :

```sql
ix_matches_kickoff   (kickoff_utc)                          -- balayages temporels
ix_matches_season    (season_id, kickoff_utc)               -- calcul de classement
ix_matches_home      (home_competitor_id, kickoff_utc DESC) -- forme récente
ix_matches_away      (away_competitor_id, kickoff_utc DESC) -- forme récente
ix_matches_upcoming  (kickoff_utc) WHERE status='scheduled' -- index partiel, chemin chaud
ix_matches_tie       (tie_id) WHERE tie_id IS NOT NULL
```

> Les deux index `home`/`away` séparés sont volontaires : la requête « les 15
> derniers matchs de l'équipe X » est un `UNION ALL` de deux parcours
> d'index, bien plus rapide qu'un `OR` sur une colonne unique.

### 3.2 `core.competitors` — équipes **et** joueurs individuels

Une seule table pour les deux, avec `kind IN ('team','individual')`. Le
tennis n'est alors pas un cas particulier : un match tennis est un match
entre deux `competitors` de kind `individual`. Tout le noyau (ratings,
forme, fatigue, cotes, backtest) fonctionne sans modification.

`core.players` reste séparée : elle représente les **membres d'une équipe**.
Pour le tennis, un `player` et un `competitor` coexistent et sont reliés par
`external_refs`.

### 3.3 `core.match_results`

`outcome_1x2` est une **colonne générée stockée** :

```sql
outcome_1x2 CHAR(1) GENERATED ALWAYS AS (
    CASE WHEN home_score > away_score THEN 'H'
         WHEN home_score < away_score THEN 'A'
         ELSE 'D' END) STORED
```

Pourquoi : le dénouement des paris est la partie du système où une erreur est
silencieuse et coûteuse. Laisser la base calculer l'issue élimine toute
divergence entre le code de backtest et le code de production.

`period_scores JSONB` porte les mi-temps, quart-temps ou sets — la structure
varie par sport, c'est exactement le cas où JSONB est justifié.

### 3.4 `raw.observations` — partitionnée par mois

| Colonne clé | Rôle |
| --- | --- |
| `fetched_at` | **Instant de disponibilité**. Clé de partition, et clé de tout l'anti-look-ahead |
| `payload JSONB` | Le corps de réponse tel quel |
| `payload_sha256` | Déduplication : un même payload re-téléchargé n'est pas ré-inséré |

Index GIN `jsonb_path_ops` sur `payload` : permet de retrouver a posteriori
d'où vient une valeur suspecte (« quel provider a dit que ce match était à
20h ? »), ce qui est indispensable au debug de qualité de données.

Partitionnement **par RANGE sur `fetched_at`** : le détachement d'une
partition ancienne (archivage vers S3 en Parquet) est instantané, et la
rétention se gère par `DETACH PARTITION` sans `VACUUM` massif.

### 3.5 `market.odds_snapshots` — la table la plus volumineuse

Estimation : 30 matchs/jour × 12 marchés × 3 issues × 15 books × 40
snapshots = **~650 000 lignes/jour**, soit ~240 M/an pour un périmètre
significatif. C'est la table qui dimensionne l'infrastructure.

Trois décisions :

1. **Partition RANGE mensuelle sur `captured_at`** — nécessaire, pas
   optionnel.
2. **Index partiels sur `is_opening` et `is_closing`** — ces deux snapshots
   sont interrogés en permanence (CLV, features d'ouverture) alors qu'ils
   représentent < 5 % des lignes. Un index partiel tient en mémoire ; un
   index complet non.
3. **Vue matérialisée `market.current_odds`** — le `DISTINCT ON (selection,
   bookmaker) ... ORDER BY captured_at DESC` est trop coûteux pour être
   exécuté à chaque affichage. Rafraîchie en `CONCURRENTLY` toutes les 2
   minutes.

**Option écartée : TimescaleDB.** Comparaison :

| | PostgreSQL natif partitionné | TimescaleDB |
| --- | --- | --- |
| Compression | TOAST seulement | **Compression colonne (~10×)** |
| Agrégats continus | Vues matérialisées manuelles | Natifs, incrémentaux |
| Rétention | `DETACH PARTITION` scripté | Politique déclarative |
| Opérabilité | Standard, n'importe quel hébergeur | Extension à installer, moins d'hébergeurs managés |
| Coût MVP | 0 | 0 en self-hosted, payant en cloud managé |
| Pertinence MVP | **Oui** | Oui, à partir de ~100 M lignes |

**Recommandation** : PostgreSQL natif en V1. Les tables volumineuses sont
déjà partitionnées, donc la migration vers TimescaleDB est un
`create_hypertable()` sur une table existante — le coût du report est
quasi nul, alors que le coût d'adoption immédiate (dépendance, hébergeur
contraint) est réel.

### 3.6 `features.values` — le feature store

```
PK (match_id, competitor_id, as_of_ts, feature_set_version)
```

La clé primaire dit tout : **une valeur de feature n'existe que relativement
à un instant de calcul**. Il est structurellement impossible de stocker « la
feature de ce match » sans dire à quel moment.

`payload JSONB` plutôt que 117 colonnes : les features changent de version
toutes les deux semaines en phase de R&D ; une table à colonnes larges
imposerait une migration à chaque itération. Le coût est une lecture JSONB,
négligeable au regard du volume (quelques milliers de lignes par jour). Quand
l'ensemble de features se stabilisera, une table colonnaire dérivée pourra
être matérialisée pour l'entraînement.

`feature_hash` : SHA-256 du dictionnaire canonique. **C'est le détecteur de
révision rétroactive** : si on recalcule les features d'un match passé avec
le même `as_of_ts` et que le hash change, un provider a modifié son
historique. Alerte immédiate.

### 3.7 `features.ratings_snapshots`

Deux horodatages, encore :

- `valid_from` : à partir de quand ce rating s'applique
- `computed_at` : quand il a été calculé

Le point-in-time exige `computed_at <= as_of_ts`. Sans cette colonne, un
re-entraînement des ratings attaque/défense sur toute la saison
contaminerait tous les backtests de la saison — c'est la fuite la plus
fréquente et la plus difficile à repérer dans ce domaine.

### 3.8 `ml.predictions` et `ml.value_signals`

`ml.predictions` est partitionnée par `as_of_ts` (mensuel) : les backtests
génèrent des millions de prédictions et doivent pouvoir être purgés
partition par partition.

Champs notables :

| Colonne | Rôle |
| --- | --- |
| `probabilities JSONB` | Distribution complète, jamais une « prédiction » |
| `prob_sigma JSONB` | Incertitude par issue (bootstrap) — alimente le système de confiance |
| `component_probs JSONB` | Probabilité de chaque sous-modèle avant stacking — indispensable à l'explication et au diagnostic |
| `feature_hash` | Reproductibilité |
| `data_quality`, `reliability` | Deux notions distinctes (doc 11) |
| `lineup_status` | `unknown`/`predicted`/`confirmed` : change l'interprétation de tout le reste |

`ml.value_signals` sépare le **calcul** de l'edge de la **décision** :
`threshold_passed` et `suppression_reason` permettent d'auditer les signaux
rejetés. On garde la trace des signaux non actionnés — sinon on ne peut pas
mesurer a posteriori si le seuil était bon.

### 3.9 `bet.bets`

Le champ `status` couvre `half_won`/`half_lost`, indispensables pour les
handicaps asiatiques en quarts (−0.25, −0.75). Beaucoup de systèmes oublient
ce cas et faussent leur ROI.

`clv` est stocké au dénouement : c'est la métrique n°1 de validation
(doc 07).

---

## 4. Stratégie d'indexation — principes appliqués

| Principe | Application |
| --- | --- |
| **Index partiel dès qu'un filtre est constant** | `WHERE status='scheduled'`, `WHERE is_closing`, `WHERE NOT passed` |
| **Index couvrant les tris fréquents** | `(competitor_id, kickoff_utc DESC)` |
| **GIN sur JSONB seulement pour le forensic** | `raw.observations.payload` ; **pas** sur `features.values.payload` (jamais interrogé par contenu) |
| **Trigram sur les noms** | `core.competitors.name`, `core.players.full_name` — pour le rapprochement flou inter-providers |
| **Pas d'index sur les colonnes à faible cardinalité seules** | `status`, `is_home` : toujours en position secondaire |

Total : 142 index. C'est beaucoup, et c'est assumé : le profil est
lecture-intensive (backtests, dashboard) et écriture par lots (ingestion),
pas transactionnel.

---

## 5. Contraintes d'intégrité — la première ligne de défense qualité

Les contraintes `CHECK` sont le filet le moins cher contre les données
pourries. Exemples embarqués :

```sql
CHECK (shots_on_target <= shots)
CHECK (passes_completed <= passes)
CHECK (possession_pct BETWEEN 0 AND 100)
CHECK (fgm <= fga)
CHECK (fg3m <= fg3a)
CHECK (first_serve_in <= first_serve_total)
CHECK (odds_decimal > 1.0)
CHECK (home_competitor_id <> away_competitor_id)
CHECK (end_date > start_date)
```

Une seule de ces contraintes a déjà justifié son existence lors du test de
validation : l'insertion de `shots=8, shots_on_target=12` est rejetée par la
base. Sans elle, cette ligne aurait produit un ratio de précision de tir de
150 % et un modèle discrètement corrompu.

**Important** : ces contraintes s'appliquent à `stats.*` et `core.*`, jamais
à `raw.*`. La couche raw doit accepter les données pourries — c'est son rôle.
Le rejet a lieu à la canonisation, et le conflit est tracé dans
`ops.source_conflicts`.

---

## 6. Migrations et versionnement

- **Outil** : Alembic (cohérent avec un backend Python/SQLAlchemy).
- **Règle** : toute migration est réversible ou explicitement marquée
  irréversible avec une justification.
- **Migrations de données séparées des migrations de schéma** — une migration
  de schéma doit s'appliquer en quelques secondes.
- **Partitions créées à l'avance** par un job mensuel (3 mois d'avance), pas
  par migration.

---

## 7. Rétention et archivage

| Données | Conservation en ligne | Après |
| --- | --- | --- |
| `raw.observations` | 90 jours | Parquet sur object storage, partition détachée |
| `market.odds_snapshots` | 24 mois | Agrégat (open/close/min/max/n_moves) conservé, détail archivé |
| `ml.predictions` (mode backtest) | 30 jours | Purge (reproductible depuis le config hash) |
| `ml.predictions` (mode live/shadow) | Illimité | — |
| `core.*`, `stats.*` | Illimité | — |
| `bet.bets` | Illimité | — |

Le principe : **tout ce qui est reproductible est purgeable, tout ce qui est
une observation du monde est conservé.**

---

## 8. Estimation de taille à 3 ans

| Table | Lignes | Taille estimée |
| --- | --- | --- |
| `market.odds_snapshots` | ~700 M | ~90 Go (partitionné, archivé au-delà de 24 mois) |
| `raw.observations` | ~40 M actives | ~60 Go (JSONB compressé) |
| `core.match_events` | ~25 M | ~8 Go |
| `ml.predictions` | ~15 M | ~6 Go |
| `features.values` | ~3 M | ~4 Go |
| Reste | — | ~2 Go |
| **Total en ligne** | | **~170 Go** |

Dimensionnement cible : une instance PostgreSQL 8 vCPU / 32 Go RAM / 500 Go
SSD suffit largement jusque-là. **Le projet n'a pas de problème de scale ; il
a un problème de qualité de données.** C'est là que doit aller l'effort.
