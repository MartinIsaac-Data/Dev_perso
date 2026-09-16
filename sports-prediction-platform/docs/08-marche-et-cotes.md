# 08 — Marché, cotes et mouvements

> Le marché n'est pas la cible à battre : c'est le meilleur concurrent
> disponible, et une source d'information de première qualité. Tout le
> travail consiste à l'utiliser sans s'y dissoudre.

---

## 1. Modèle de données des cotes

### 1.1 Les trois niveaux

```
market_types      →  QUOI  : 1X2, Over/Under, Handicap asiatique, BTTS...
selections        →  QUELLE ISSUE d'un marché pour un match précis
odds_snapshots    →  QUELLE COTE, chez QUI, à QUEL MOMENT
```

Cette séparation est ce qui permet d'ajouter un marché (corners, cartons,
player props) **sans toucher au schéma**. Un nouveau marché = une ligne dans
`market_types` + une règle de dénouement.

### 1.2 Marchés couverts

| Marché | Code | Ligne | Issues | Priorité |
| --- | --- | --- | --- | --- |
| Résultat | `1X2` | non | H, D, A | **V1** |
| Double chance | `DC` | non | 1X, 12, X2 | V1 (dérivé, pas de modèle propre) |
| Total buts/points | `OU` | 0.5 → 6.5 | OVER, UNDER | **V1** |
| Handicap asiatique | `AH` | −3 → +3 par 0.25 | HOME, AWAY | **V1** |
| Total asiatique | `AOU` | par 0.25 | OVER, UNDER | V1 |
| Les deux marquent | `BTTS` | non | YES, NO | **V1** |
| Score exact | `CS` | non | "2-1", … | V2 |
| Mi-temps/fin | `HTFT` | non | 9 issues | V2 |
| Total corners | `CORNERS_OU` | non | OVER, UNDER | V2 |
| Total cartons | `CARDS_OU` | non | OVER, UNDER | V2 |
| Vainqueur set (tennis) | `SET_WIN` | non | P1, P2 | V1 (tennis) |
| Total jeux (tennis) | `GAMES_OU` | oui | OVER, UNDER | V1 (tennis) |
| Buteur / points joueur | `PLAYER_*` | variable | variable | V3 |

**Les handicaps en quarts** (−0.25, −0.75) demandent un traitement
particulier : la mise est scindée en deux moitiés sur les deux lignes
entières adjacentes. La règle de dénouement doit gérer `half_won` et
`half_lost` — d'où ces valeurs dans `bet.bets.status`.

### 1.3 Ce qu'on stocke pour chaque cote

| Champ | Pourquoi il est indispensable |
| --- | --- |
| `odds_decimal` | La cote |
| `captured_at` | **Sans lui, la donnée est inutilisable** en backtest |
| `bookmaker_id` | Les bookmakers n'ont pas la même qualité d'information |
| `is_opening` / `is_closing` | Deux instants de référence : le prior du marché et son verdict final |
| `max_stake` | Proxy de liquidité et de confiance du book. Une cote à limite 20 € n'est pas une opportunité |
| `volume_matched` | Exchanges : la vraie mesure de liquidité |
| `is_suspended` | Une cote suspendue n'existe pas. L'oublier gonfle artificiellement le backtest |

### 1.4 Fréquence de capture

| Fenêtre avant le match | Fréquence |
| --- | --- |
| > 72 h | 1× / 6 h |
| 72 h → 24 h | 1× / heure |
| 24 h → 3 h | 1× / 15 min |
| 3 h → 30 min | 1× / 5 min |
| 30 min → coup d'envoi | 1× / min |

Volumétrie résultante : ~40 snapshots par sélection et par bookmaker, soit
l'ordre de 650 000 lignes/jour pour un périmètre significatif (voir doc 04
§3.5).

**Cote d'ouverture** : le premier snapshot observé **n'est pas** forcément
l'ouverture réelle. Il faut le marquer comme `is_opening` seulement si la
capture a démarré à moins de 30 minutes de la publication du marché.
Autrement, `is_opening = false` et la feature `odds_drift_since_open` est
marquée manquante. Confondre les deux produit des mouvements fantômes.

---

## 2. Consensus et hiérarchie des bookmakers

Tous les bookmakers ne se valent pas. Trois catégories :

| Catégorie | Caractéristiques | Rôle dans le système |
| --- | --- | --- |
| **Sharp** (limites élevées, marge faible, acceptent les gagnants) | Marge 2-3 %, réagissent au flux informé | **Référence de vérité**. Leur cote de clôture est le meilleur estimateur disponible |
| **Grand public** (marge 5-8 %, limitent les gagnants) | Suivent les sharps avec un délai | **Cible d'exécution** : c'est là que se trouvent les écarts |
| **Exchanges** | Pas de marge, une commission | Référence + exécution, mais liquidité variable |

Le consensus est **pondéré**, jamais une moyenne simple :

```
ω_b  ∝  w_sharp(b)  ×  1/overround_b  ×  log(1 + max_stake_b)
```

**Attention au faux consensus** : 15 bookmakers grand public qui affichent la
même cote ne constituent pas 15 opinions indépendantes — ils copient tous la
même source. Le nombre effectif d'opinions indépendantes est bien inférieur
à `n_bookmakers`. La feature `market_dispersion` (écart-type des probabilités
dévigorisées) est un meilleur indicateur de la véritable incertitude du
marché.

---

## 3. Mouvements de cotes

### 3.1 Travailler en log-odds, jamais en cotes brutes

Une variation de 0.10 sur une cote de 1.50 et sur une cote de 8.00 n'ont rien
à voir. La bonne unité :

```
Δ = log( o_après / o_avant )
```

ou, mieux encore, en probabilité dévigorisée :

```
Δp = p_devig(t₂) − p_devig(t₁)
```

### 3.2 Qu'est-ce qu'un mouvement « significatif » ?

Un seuil absolu (« 5 % de variation ») est arbitraire et donne trop d'alertes
sur les marchés volatils, trop peu sur les marchés stables. Il faut
**normaliser par la volatilité habituelle de ce type de marché**.

```
σ_référence(marché, fenêtre, temps avant match)
    = écart-type historique de Δ log-odds sur des marchés comparables

z = Δ log-odds / σ_référence

mouvement significatif  ⟺  |z| > 2.5
```

`σ_référence` est estimé par marché × tranche de cote × fenêtre temporelle.
C'est une table de référence recalculée chaque mois.

### 3.3 Taxonomie des mouvements

| Type | Signature | Interprétation | Action |
| --- | --- | --- | --- |
| **Drift** | Mouvement lent, tous books, faible z | Ajustement normal (météo, compos attendues) | Rien |
| **Steam move** | Mouvement rapide, **simultané sur ≥ 60 % des books**, z > 3 | De l'argent informé est entré | **Recalculer, ne pas parier contre** |
| **Reverse line movement** | La cote bouge **contre** le sens du volume public | L'argent sharp s'oppose au public | Signal fort — mais souvent déjà exploité |
| **Limit change** | `max_stake` change sans que la cote bouge | Le book ajuste son exposition | Indicateur de confiance |
| **Correction** | Mouvement isolé chez un seul book, retour rapide | Erreur de tarification corrigée | Ignorer (et se méfier si on l'avait « saisie ») |
| **Suspension** | `is_suspended = true` | News en cours d'intégration | **Bloquer tout signal** |

### 3.4 Détection du steam move

```python
def detect_steam(selection_id, window_min=10, z_threshold=3.0, book_ratio=0.6):
    moves = deltas_by_bookmaker(selection_id, window_min)
    moved = [b for b, d in moves.items() if abs(z_score(d)) > z_threshold]
    same_direction = all_same_sign(moves[b] for b in moved)
    return (len(moved) / len(moves) >= book_ratio) and same_direction
```

**Comportement du système face à un steam move** : il ne parie pas dans le
sens du mouvement (le train est parti) et il ne parie **surtout pas** contre.
Il **recalcule** : si le modèle disposait déjà de l'information qui a causé
le mouvement (une compo publiée, par exemple), le signal reste valide ; si le
modèle n'a aucune explication au mouvement, **le marché sait quelque chose
que le système ignore** et tout signal est suspendu.

Cette règle — « un mouvement inexpliqué invalide le signal » — est l'une des
protections les plus efficaces contre les paris sur information périmée.

### 3.5 Utiliser le mouvement comme feature

| Feature | Définition | Valeur prédictive |
| --- | --- | --- |
| `odds_drift_since_open` | `log(o_actuelle / o_ouverture)` | **Bonne** : le marché intègre l'information au fil du temps |
| `odds_drift_24h` | Sur 24 h | Bonne |
| `odds_drift_velocity` | Δ par heure sur 3 h | Moyenne, bruitée |
| `market_dispersion` | Écart-type entre books | Bonne, surtout comme mesure d'incertitude |
| `is_steam_move` | Booléen | Utile comme **filtre**, pas comme prédicteur |
| `limit_trend` | Δ `max_stake` | Faible mais non nul |

**Piège majeur** : ces features sont extrêmement puissantes en apparence
parce qu'elles agrègent l'information de milliers de participants. Un modèle
qui les reçoit atteindra facilement un excellent log-loss — et n'aura **aucun
edge**, puisqu'il ne fera que constater ce que le marché a déjà décidé. Elles
sont donc rangées dans le membre M4 (modèle marché) de l'ensemble, dont le
poids est plafonné (doc 05 §6.3).

---

## 4. Closing Line Value (CLV)

```
CLV = o_prise / o_clôture − 1
```

Ou en probabilité, ce qui est plus rigoureux :

```
CLV_prob = p_clôture_devig − p_prise_devig
```

La seconde forme est préférable parce qu'elle neutralise les variations de
marge entre l'instant de prise et la clôture.

**Pourquoi c'est la métrique reine** : la cote de clôture d'un bookmaker
liquide est, empiriquement, le meilleur estimateur public de la probabilité
réelle. Battre systématiquement la clôture signifie que l'on a de
l'information avant le marché. C'est **la définition opérationnelle d'un
edge**, et elle converge bien plus vite que le ROI.

Exemple : un pari pris à 2.10 dont la clôture est à 1.98.

```
CLV = 2.10 / 1.98 − 1 = +6.06 %
```

Même si ce pari est perdu, la décision était bonne.

**Précaution** : le CLV doit être mesuré contre la clôture d'un **bookmaker
sharp**, pas contre celle du bookmaker où le pari a été pris. Sinon, on
mesure le déplacement d'un book particulier, pas celui du marché.

---

## 5. Ce que le marché sait et que le modèle ignorera toujours

Liste honnête, à garder sous les yeux :

| Information | Le modèle y a-t-il accès ? |
| --- | --- |
| Compositions officielles | Oui, à T-60 min |
| Blessure signalée à l'entraînement de la veille | **Non** (sauf provider très rapide) |
| Conflit interne, joueur en instance de transfert | **Non** |
| Rotation décidée mais non annoncée | **Non** |
| Volume de paris et positionnement du public | **Non** |
| Information des équipes elles-mêmes | **Non** |
| État de forme observé à l'entraînement | **Non** |
| Météo locale de dernière minute | Partiellement |

Cette asymétrie est structurelle. Elle implique que :

1. Les signaux détectés loin du coup d'envoi (J-3) sont plus nombreux mais
   moins fiables — le marché n'a pas encore intégré l'information.
2. Les signaux détectés près du coup d'envoi sont plus rares mais plus
   solides.
3. **Un signal qui persiste malgré un marché stable et liquide est
   statistiquement plus souvent une erreur du modèle qu'une erreur du
   marché.** C'est le prior qu'il faut adopter.

---

## 6. Architecture d'ingestion des cotes

```
                    ┌─────────────────────────────────────┐
 Provider A ───────▶│  Normalisation des identifiants      │
 Provider B ───────▶│  (matching match/marché/sélection)   │
 Exchange   ───────▶└───────────────┬─────────────────────┘
                                    ▼
                    ┌─────────────────────────────────────┐
                    │  Validation : cote > 1.0,            │
                    │  overround plausible [0.5 %, 25 %],  │
                    │  variation < 60 % en 1 min           │
                    └───────────────┬─────────────────────┘
                                    ▼
                    ┌─────────────────────────────────────┐
                    │  Déduplication (hash) →               │
                    │  INSERT market.odds_snapshots         │
                    └───────────────┬─────────────────────┘
                                    ▼
             ┌──────────────────────┴───────────────────────┐
             ▼                                              ▼
  ┌────────────────────────┐                   ┌────────────────────────┐
  │ Calcul de-vig (5       │                   │ Détection de mouvement │
  │ méthodes) → market_    │                   │ → odds_movements       │
  │ probabilities          │                   │ → alertes si |z|>2.5   │
  └────────────────────────┘                   └────────────────────────┘
```

### Le problème du matching des identifiants

C'est **le point de fragilité n°1** de tout le pipeline de cotes. Le provider
de cotes appelle l'équipe « Man United », le provider de stats « Manchester
Utd », et le troisième « Manchester United FC ».

Stratégie en trois passes :

1. **Identifiant externe** quand le provider en fournit un stable
   (`external_refs` JSONB) — le seul cas fiable.
2. **Matching déterministe** sur (date ± 1 jour, compétition, paire
   d'équipes déjà mappées).
3. **Matching flou** (trigram + distance de Levenshtein normalisée) avec
   **seuil haut**, et écriture dans `raw.entity_mappings` avec
   `resolved_by = 'fuzzy'` et un score de confiance.

Toute correspondance floue sous un seuil de confiance part dans une file de
revue manuelle. **Un mauvais matching d'équipe est pire qu'une donnée
manquante** : il produit silencieusement des cotes attribuées au mauvais
match, et donc des « values » spectaculaires et entièrement fausses.

Contrôle automatique : si l'overround d'un marché reconstruit est hors de
[0.5 %, 25 %], le matching est presque certainement faux. Ce contrôle simple
attrape la grande majorité des erreurs d'appariement.
