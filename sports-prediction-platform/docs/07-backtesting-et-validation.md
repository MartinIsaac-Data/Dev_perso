# 07 — Moteur de backtesting, anti-leakage et validation

> Le backtest est le seul instrument qui distingue un modèle d'une opinion.
> Il est aussi l'endroit où il est le plus facile de se mentir à soi-même.
> Ce document est donc écrit en posture défensive : chaque mécanisme existe
> pour empêcher une erreur précise et documentée.

---

## 1. Principe : la simulation par horloge

Le moteur ne « rejoue » pas des données : il **rejoue le temps**. Une
horloge virtuelle avance, et à chaque instant le système ne peut accéder
qu'à ce qui existait à cet instant.

```
pour chaque instant t dans la grille temporelle (pas = 1 heure) :
    ┌────────────────────────────────────────────────────────────┐
    │ 1. Matchs éligibles : kickoff ∈ [t, t + horizon]            │
    │ 2. Features     ← feature_store.get(match, as_of_ts = t)    │
    │    (interdit : toute donnée avec recorded_at > t)           │
    │ 3. Modèle       ← model_registry.get(trained_before = t)    │
    │    (interdit : un modèle entraîné après t)                  │
    │ 4. Probabilités ← modèle.predict(features)                  │
    │ 5. Cotes        ← odds.snapshot_at(selection, t)            │
    │    (interdit : cotes de clôture si t < clôture)             │
    │ 6. Signal       ← valuation.evaluate(p, odds, σ, qualité)   │
    │ 7. Décision     ← staking.size(signal, bankroll_t)          │
    │ 8. Pari enregistré avec odds_taken = cote réellement         │
    │    disponible à t, jamais la meilleure cote a posteriori     │
    └────────────────────────────────────────────────────────────┘

au dénouement du match :
    résultat → settlement → profit → bankroll → CLV
```

**L'interdiction est appliquée par le code, pas par la discipline.** En mode
`backtest`, le repository refuse toute requête sans `as_of_ts`, et toute
requête dont le résultat contiendrait une ligne avec `recorded_at > as_of_ts`
lève une exception. C'est un test d'intégration permanent.

---

## 2. Les onze fuites de données, et la parade de chacune

| # | Fuite | Comment elle se produit | Parade dans ce système |
| --- | --- | --- | --- |
| 1 | **Look-ahead direct** | Utiliser le résultat du match dans ses propres features | `as_of_ts < kickoff` vérifié à l'écriture de chaque feature |
| 2 | **Révision rétroactive** | Le provider corrige un xG à J+3 ; le backtest lit la version corrigée | Bitemporalité : filtre `recorded_at <= as_of_ts` |
| 3 | **Ratings ré-estimés sur tout l'historique** | Les α/β de Poisson estimés sur la saison entière, utilisés pour prédire la journée 5 | `ratings_snapshots.computed_at <= as_of_ts` |
| 4 | **Normalisation globale** | StandardScaler ajusté sur tout le dataset (moyenne incluant le futur) | Statistiques d'imputation et de scaling figées dans l'artefact du modèle, calculées sur la fenêtre d'entraînement uniquement |
| 5 | **Cotes de clôture en entrée** | `closing_odds` utilisée comme feature — elle intègre l'information de dernière minute | `market_prob_devig_closing` marquée `forbidden`, refusée par le moteur de features |
| 6 | **Compositions officielles trop tôt** | Utiliser la compo confirmée pour une prédiction horodatée à J-1 | `lineup_confirmed_strength` n'est calculable que si `as_of_ts >= lineups.published_at` |
| 7 | **Sélection du modèle sur le test** | Choisir les hyperparamètres en regardant la performance finale | Découpage en trois : train / validation temporelle / **holdout jamais regardé** |
| 8 | **Survivorship bias** | Ne garder que les équipes/compétitions encore présentes aujourd'hui | Univers défini historiquement : toute équipe ayant existé à `t` est incluse |
| 9 | **Biais de disponibilité des cotes** | Ne backtester que les matchs pour lesquels on a des cotes archivées — or ce sont les matchs les plus liquides | Taux de couverture mesuré et publié ; résultats stratifiés par liquidité |
| 10 | **Meilleure cote a posteriori** | Prendre la meilleure cote observée sur toute la fenêtre pré-match | `odds_taken` = cote disponible **à l'instant de la décision**, chez un bookmaker accessible |
| 11 | **Fuite météo** | Utiliser la météo observée plutôt que la prévision | `core.weather_observations.kind = 'forecast'` avec `fetched_at <= as_of_ts` |

> Les fuites 2, 3 et 5 sont les plus fréquentes et **les plus difficiles à
> détecter** : elles ne produisent pas de résultats absurdes, juste un
> backtest trop beau de 2 à 5 points de ROI. C'est exactement l'ampleur qui
> fait croire à un edge réel.

### Le test de fuite automatisé

Un test exécuté en CI sur chaque modification du pipeline :

```
1. Prendre 200 matchs passés au hasard
2. Calculer les features avec as_of_ts = kickoff − 1h
3. Recalculer les mêmes features 6 mois plus tard
4. Comparer les feature_hash
   → différence = un provider a révisé l'historique
   → si la révision affecte des features utilisées : ALERTE
```

Ce test ne prévient pas la fuite, il la **détecte**. C'est la seule façon
fiable de découvrir qu'un provider a modifié son passé.

---

## 3. Protocole de validation temporelle

### 3.1 Découpage

```
│◄──── ENTRAÎNEMENT ────►│◄─ VALIDATION ─►│◄─ EMBARGO ─►│◄─ HOLDOUT ─►│
│      2019 – 2023       │  2024 – 2024   │   30 jours  │ 2025 – 2026 │
                                                ▲
                                     évite la contamination par les
                                     features à fenêtre longue
```

**L'embargo** est indispensable : une feature de forme avec une demi-vie de
90 jours calculée le 1ᵉʳ janvier utilise des matchs de novembre. Sans
embargo, la frontière train/test est poreuse. La durée de l'embargo est
`3 × la plus longue demi-vie de feature`.

### 3.2 Validation croisée glissante (walk-forward)

```
Pli 1 : train [2019-01 → 2021-12]  test [2022-01 → 2022-06]
Pli 2 : train [2019-01 → 2022-06]  test [2022-07 → 2022-12]
Pli 3 : train [2019-01 → 2022-12]  test [2023-01 → 2023-06]
...
```

Fenêtre **expansive** (et non glissante) parce que le volume de données est
le facteur limitant. Une fenêtre glissante serait préférable en cas de forte
non-stationnarité : les deux sont testées, et le choix est mesuré, pas
supposé.

**Interdit formel** : la validation croisée k-fold aléatoire. Elle place des
matchs de mai dans le train et des matchs de mars dans le test, avec des
équipes dont les ratings sont partagés. Le gain de performance apparent est
massif et entièrement illusoire.

### 3.3 Le holdout, règle d'or

Le holdout (la période la plus récente) est **regardé une seule fois**, au
moment de la décision go/no-go. Chaque coup d'œil supplémentaire le
contamine : à la cinquième itération, on a implicitement optimisé dessus.

Discipline pratique : le holdout est dans une partition séparée, son accès
est loggé, et le nombre d'évaluations est compté et publié dans le rapport.

---

## 4. Métriques de backtest

### 4.1 Métriques de qualité probabiliste (primaires)

| Métrique | Cible | Interprétation |
| --- | --- | --- |
| **Log loss** | < celui du marché dévigorisé | Si supérieur, le modèle est pire que les cotes |
| **Brier score** | idem | |
| **Brier Skill Score vs marché** | **> 0** | La seule question : bat-on le marché ? |
| **ECE** | < 0.02 | Calibration |
| **Décomposition Murphy** | Fiabilité ↓, Résolution ↑ | Diagnostic |

> **Le BSS contre le marché est le juge de paix.** Un BSS négatif signifie
> que le modèle est moins informatif que les cotes ; dans ce cas, tout ROI
> positif observé est du bruit, quelle que soit sa taille.

### 4.2 Métriques financières (secondaires mais nécessaires)

| Métrique | Formule | Piège |
| --- | --- | --- |
| **ROI / Yield** | `Σ profit / Σ mises` | Converge très lentement. À 500 paris, l'intervalle de confiance à 95 % fait ±8 points |
| **Profit** | `Σ profit` | Dépend du staking, pas comparable entre configurations |
| **Hit rate** | `n_gagnés / n_paris` | **Trompeur** : un hit rate de 30 % à cote 4.00 est excellent |
| **Max drawdown** | `max(peak − trough) / peak` | Métrique de survie, à regarder avant le ROI |
| **Plus longue série perdante** | — | Dimensionne la tolérance psychologique et la bankroll |
| **Évolution de bankroll** | Série temporelle | À afficher en log |
| **Ratio de Sharpe des paris** | `μ_profit / σ_profit × √n` | Comparable entre stratégies |
| **CLV moyen** | `moyenne(o_prise / o_clôture − 1)` | **La plus importante** |
| **% de paris à CLV positif** | — | Cible > 55 % |

### 4.3 Pourquoi le CLV prime sur le ROI

Le ROI a besoin de **milliers** de paris pour converger. Le CLV converge en
quelques **centaines**, parce qu'il mesure directement la qualité de la
décision, pas le résultat aléatoire du match.

```
ROI      = signal (l'edge)  +  bruit (la variance des résultats)
CLV      = signal (l'edge)  +  bruit résiduel du marché, bien plus faible
```

Interprétation :

| CLV | ROI | Diagnostic |
| --- | --- | --- |
| Positif | Positif | Edge réel, probablement |
| **Positif** | **Négatif** | Edge réel, malchance. **Continuer** |
| **Négatif** | **Positif** | **Chance. Le modèle n'a pas d'edge.** Danger maximal : c'est le scénario où l'on se convainc d'avoir réussi |
| Négatif | Négatif | Pas d'edge. Arrêter |

**Règle de gouvernance** : aucun passage en production sans CLV positif
statistiquement significatif sur au moins 300 paris papier. Un ROI positif
avec un CLV négatif est un motif de **rejet**, pas de validation.

Test de significativité :

```
t = moyenne(CLV) / ( écart-type(CLV) / √n )
```

avec un seuil à t > 2 et n ≥ 300.

---

## 5. Contrôles de réalisme du backtest

Un backtest qui ignore les frictions surestime systématiquement la
performance. Les frictions à modéliser :

| Friction | Modélisation | Impact typique |
| --- | --- | --- |
| **Cote non obtenue** | Probabilité de refus croissante avec l'edge affiché : `p_refus = min(0.6, 2 × edge)` | −0.5 à −1.5 pt de ROI |
| **Limites de mise** | `stake = min(stake_kelly, max_stake × facteur_compte)` | Variable |
| **Slippage** | Appliquer la cote à `t + 90 secondes` plutôt qu'à `t` | −0.3 pt |
| **Commission (exchange)** | `profit_net = profit_brut × (1 − commission)` | −2 à −5 % du profit |
| **Comptes limités** | Après 100 paris gagnants sur un book, diviser `max_stake` par 5 | Fort à long terme |
| **Arrondi des mises** | Arrondir à l'unité | Négligeable |

> Le **scénario pessimiste** (toutes frictions actives, méthode de de-vig la
> plus défavorable, cotes moyennes plutôt que meilleures) est le seul
> résultat à communiquer. Le scénario optimiste sert uniquement à borner.

---

## 6. Tests de robustesse obligatoires

Un résultat de backtest n'est recevable qu'accompagné de ces analyses :

| Test | Ce qu'il détecte |
| --- | --- |
| **Stratification par ligue** | Un ROI global positif porté par une seule ligue = surapprentissage |
| **Stratification par saison** | Performance concentrée sur une saison = non-stationnarité ou chance |
| **Stratification par bac de cotes** | Edge concentré sur les cotes > 6.00 = calibration défaillante sur les outsiders |
| **Stratification par bac d'edge** | L'edge réalisé doit croître avec l'edge annoncé. Sinon, le signal n'est pas monotone donc pas réel |
| **Sensibilité à la méthode de de-vig** | Si Shin donne +4 % et proportionnelle −1 %, le résultat est un artefact |
| **Sensibilité au seuil d'EV** | La performance doit varier continûment. Un pic sur un seuil précis = surapprentissage |
| **Test de permutation** | Mélanger aléatoirement les résultats et refaire tourner : le ROI doit s'effondrer à 0 |
| **Backtest sur modèle aléatoire** | Un modèle qui produit des probabilités tirées au hasard doit donner un ROI ≈ −marge |
| **Analyse des 20 plus gros gains** | Si 80 % du profit vient de 5 paris, il n'y a pas de stratégie |

Le dernier test est le plus révélateur en pratique. Un edge réel produit un
profit **diffus**. Un profit concentré sur quelques coups est de la variance.

---

## 7. Architecture technique du moteur

```
backtest/
├── clock.py          # horloge virtuelle, grille temporelle
├── universe.py       # définition historique de l'univers (anti-survivorship)
├── data_access.py    # repository point-in-time — LE point de contrôle unique
├── engine.py         # boucle principale
├── settlement.py     # règles de dénouement par marché (partagées avec la prod)
├── staking.py        # méthodes de mise (partagées avec la prod)
├── frictions.py      # refus, limites, slippage, commissions
├── metrics.py        # ROI, CLV, Brier, drawdown, Murphy
├── report.py         # rapport HTML + artefacts
└── config.py         # configuration déclarative, hashée
```

### Configuration déclarative et hashée

```yaml
backtest:
  name: "fb_1x2_v0.3_pessimistic"
  model_version: "football_1x2_ensemble@0.3.0"
  period: { start: 2024-07-01, end: 2026-06-30 }
  universe:
    competitions: [FR1, EN1, ES1, IT1, DE1]
    markets: [1X2, OU]
  decision_point: "kickoff - 3h"
  odds_source: average          # best | average | sharp | specific
  devig_method: shin
  edge_threshold: 0.02
  uncertainty_k: 1.0
  staking: { method: fractional_kelly, fraction: 0.25, cap_pct: 0.02 }
  frictions: { rejection: true, limits: true, slippage_sec: 90, commission: 0.0 }
  initial_bankroll: 10000
```

Le SHA-256 de cette configuration est stocké avec les résultats
(`bet.backtests.config_sha256`) avec le commit git. **Tout résultat non
reproductible à partir de ces deux valeurs est jeté.**

---

## 8. Le piège du backtest itératif

Le vrai danger n'est pas un backtest mal codé — c'est **un backtest bien codé
exécuté 200 fois**.

À chaque itération (« et si on retirait la météo ? », « et si le seuil était
à 2.5 % ? »), on sélectionne implicitement la configuration qui a le mieux
marché **sur ce jeu de données**. Après 200 essais, on a construit un modèle
surajusté au backtest lui-même, sans avoir écrit une seule ligne de code
fautive.

Parades :

| Parade | Mise en œuvre |
| --- | --- |
| **Compter les essais** | Chaque exécution est journalisée. Le compteur est affiché dans le rapport |
| **Ajuster l'attente** | Avec *n* essais indépendants, le meilleur ROI attendu sous l'hypothèse nulle vaut approximativement `σ·√(2 ln n)`. À n = 200 et σ = 4 %, cela donne **+13 %** (borne simple) ou **+10 %** avec la correction du second ordre. Autrement dit : après 200 essais, un backtest à +10 % de ROI est **exactement ce qu'on attend d'un modèle sans aucun edge** |
| **Pré-enregistrer les hypothèses** | Décider *à l'avance* quelles features tester et quels seuils, et s'y tenir |
| **Réserver le holdout** | Une seule évaluation |
| **Validation prospective (paper trading)** | Le seul test véritablement propre |

> Ce dernier point mérite d'être dit clairement : **aucun backtest, aussi
> rigoureux soit-il, ne remplace 3 à 6 mois de paper trading en aveugle.**
> Le backtest sert à éliminer les mauvaises idées rapidement, pas à prouver
> qu'une idée est bonne.

---

## 9. Rapport de backtest — contenu obligatoire

Tout rapport contient, dans cet ordre :

1. **Configuration** (hash, commit, période, univers) et **nombre d'essais
   antérieurs**
2. **Couverture** : % de matchs avec cotes disponibles, % avec compos, % avec
   stats avancées — avant tout résultat
3. **Métriques probabilistes**, avec la ligne « marché dévigorisé » comme
   référence sur chaque ligne
4. **Courbe de fiabilité** modèle vs marché
5. **Métriques financières** en scénario pessimiste, avec intervalles de
   confiance bootstrap
6. **CLV** : distribution, moyenne, t-statistique, % positif
7. **Toutes les stratifications** de la section 6
8. **Les 20 paris les plus profitables et les 20 plus coûteux**, avec leur
   explication SHAP
9. **Limites connues** rédigées explicitement

Un rapport sans les sections 2, 6 et 9 est incomplet et ne doit pas servir de
base à une décision.
