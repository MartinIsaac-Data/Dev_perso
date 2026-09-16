# 03 — Feature dictionary

> Le dictionnaire de features est un **artefact versionné**, pas de la
> documentation. Il est la source de vérité unique : le code de calcul, le
> backtest et l'interface le lisent tous. Si une feature n'est pas déclarée
> ici, elle n'existe pas.

---

## 1. Le contrat d'une feature

Chaque feature est déclarée dans un fichier YAML validé par un schéma, et
implémentée par une fonction pure. La déclaration porte six informations qui
n'ont pas le droit d'être implicites :

```yaml
- name: xg_for_weighted
  version: 3
  entity: team_match          # team_match | player_match | match | competitor
  sport: football             # ou "core" si valable pour tous les sports
  dtype: float32
  description: >
    Moyenne des xG créés par l'équipe sur ses matchs passés, pondérée par
    décroissance exponentielle du temps et ajustée par la qualité défensive
    de l'adversaire.
  formula: |
    w_i = exp(-ln(2) * days_since_i / H)
    x_i = xg_for_i * (league_mean_def_rating / def_rating_opponent_i)
    value = sum(w_i * x_i) / sum(w_i)
  params:
    half_life_days: 90
    min_matches: 3
  availability: T-0           # instant au plus tard où la valeur est connue
  lag_required: none          # aucune donnée postérieure au match source
  leakage_class: safe         # safe | needs_lag | forbidden
  null_policy: shrink_to_league_mean
  monitored: true             # surveillance de dérive en production
  depends_on:
    - stats.football_team_match.xg_for
    - ratings.team_defense
```

### Les trois classes de fuite

| Classe | Définition | Exemples |
| --- | --- | --- |
| `safe` | Calculable uniquement à partir d'événements strictement antérieurs à `as_of_ts` | Elo avant match, xG des matchs passés |
| `needs_lag` | La donnée source est révisée après publication : il faut n'utiliser que la version connue à `as_of_ts` | xG des providers (révisé à J+3), notes joueurs |
| `forbidden` | Impossible à connaître avant le coup d'envoi | Affluence réelle, météo observée, compo réelle si non publiée, minutes jouées du match courant |

Le moteur de features **refuse de calculer** une feature `forbidden` en mode
`live` ou `replay`. C'est une garde d'exécution, pas une convention.

---

## 2. Features du noyau (tous sports)

### 2.1 Identité et contexte

| Feature | dtype | Formule / source | Fuite |
| --- | --- | --- | --- |
| `is_home` | bool | `match.home_competitor_id = competitor_id` | safe |
| `is_neutral_venue` | bool | `venue.is_neutral` | safe |
| `days_since_season_start` | int16 | `kickoff − season.start_date` | safe |
| `season_progress` | float32 | `matchday / total_matchdays` | safe |
| `competition_tier` | int8 | Niveau normalisé (1 = élite) | safe |
| `stage_encoded` | int8 | groupe / 8e / ... / finale | safe |
| `is_two_legged` | bool | `match.tie_id IS NOT NULL` | safe |
| `aggregate_goal_diff` | int8 | Score cumulé avant ce match (0 si aller) | safe |
| `days_since_manager_change` | int16 | `kickoff − manager_spell.start_date` | safe |
| `matches_under_current_manager` | int16 | Compteur | safe |

### 2.2 Ratings (détail dans le doc 05)

| Feature | dtype | Formule | Fuite |
| --- | --- | --- | --- |
| `elo` | float32 | Elo courant avant le match | safe |
| `elo_diff` | float32 | `elo_home + home_adv − elo_away` | safe |
| `elo_surface` | float32 | Elo restreint à la surface (tennis) | safe |
| `rating_attack` | float32 | Paramètre α de l'ajustement Poisson | needs_lag |
| `rating_defense` | float32 | Paramètre β | needs_lag |
| `rating_overall` | float32 | `rating_attack − rating_defense` normalisé | needs_lag |
| `rating_sigma` | float32 | Écart-type postérieur (incertitude du rating) | safe |
| `home_advantage_competition` | float32 | Effet domicile estimé par compétition-saison, avec shrinkage | needs_lag |
| `rating_volatility` | float32 | Écart-type des résidus sur 15 matchs | safe |

> `rating_attack` est `needs_lag` parce que l'ajustement du modèle Poisson
> est ré-estimé périodiquement sur une fenêtre glissante : il faut garantir
> que la version utilisée pour prédire le match du 12 mars a été estimée avec
> des données antérieures au 12 mars. C'est géré par
> `ratings_snapshots.computed_at ≤ as_of_ts`.

### 2.3 Forme

| Feature | Fenêtres | dtype | Fuite |
| --- | --- | --- | --- |
| `form_points_weighted` | H = sport | float32 | safe |
| `form_goals_for_weighted` | H | float32 | safe |
| `form_goals_against_weighted` | H | float32 | safe |
| `form_goal_diff_weighted` | H | float32 | safe |
| `form_home_only` / `form_away_only` | H | float32 | safe |
| `form_n_matches` | H | int8 | safe |
| `form_reliability` | — | float32 | safe |
| `form_vs_expectation` | 10 | float32 | needs_lag |

```
form_reliability = 1 − exp(−form_n_matches / 4)
```

Cette feature sert au modèle **et** au score de qualité des données. Une
équipe avec 2 matchs joués a une `form_reliability` de 0.39 : le modèle
apprend à ne pas y croire.

### 2.4 Fatigue et calendrier

| Feature | dtype | Formule | Fuite |
| --- | --- | --- | --- |
| `rest_days` | int8 | `kickoff − dernier_match.kickoff` en jours | safe |
| `matches_3d`, `matches_7d`, `matches_14d` | int8 | Comptes | safe |
| `minutes_load_14d` | float32 | Somme des minutes des titulaires probables | needs_lag |
| `travel_km_since_last` | float32 | Haversine entre stades | safe |
| `tz_shift` | int8 | Δ fuseau avec le match précédent | safe |
| `extra_time_14d` | int8 | Nombre de prolongations | safe |
| `squad_depth` | float32 | Nb de joueurs avec `PITS > seuil` | needs_lag |
| `fatigue_score` | float32 | Formule composite (doc 02 §F) | safe |
| `congestion_next_7d` | int8 | Matchs programmés dans les 7 jours suivants | safe |

> **Rappel de conception** : `fatigue_score` **n'entre pas** dans le modèle
> ML (double comptage avec ses composants). Il alimente le modèle statistique
> et l'affichage. Les composants bruts entrent dans le GBM.

### 2.5 Enjeu et contexte

| Feature | dtype | Formule | Fuite |
| --- | --- | --- | --- |
| `p_title`, `p_qualification`, `p_relegation` | float32 | Monte-Carlo 10 000 simulations du reste de saison | safe |
| `stakes_swing` | float32 | `max_objectif |p(obj|V) − p(obj|D)|` | safe |
| `is_dead_rubber` | bool | `stakes_swing < 0.02` pour les deux équipes | safe |
| `competing_priority_ratio` | float32 | `stakes_swing` du prochain match autre compétition ÷ celui-ci | safe |
| `is_derby` | bool | Table de faits + distance < 30 km | safe |
| `must_win_margin` | int8 | Buts nécessaires pour se qualifier | safe |

### 2.6 Effectif (dérivées du PITS)

| Feature | dtype | Formule | Fuite |
| --- | --- | --- | --- |
| `pits_missing_off` | float32 | Σ PITS offensif des indisponibles pondéré par p(titulaire) | needs_lag |
| `pits_missing_def` | float32 | Idem défensif | needs_lag |
| `pits_missing_total` | float32 | Somme | needs_lag |
| `pits_top1_missing` | float32 | PITS du meilleur joueur absent | needs_lag |
| `lineup_status` | enum | `unknown` / `predicted` / `confirmed` | safe |
| `lineup_predicted_strength` | float32 | Σ PITS × p(titulaire) du onze probable | needs_lag |
| `lineup_confirmed_strength` | float32 | Σ PITS du onze confirmé | **forbidden avant T-60min** |
| `squad_continuity_season` | float32 | % de minutes de la saison N−1 conservées | safe |
| `returning_from_injury_minutes` | float32 | Minutes accordées à des joueurs revenant de blessure | needs_lag |

`lineup_confirmed_strength` est marquée `forbidden` **conditionnellement** :
le moteur autorise son calcul seulement si `as_of_ts ≥ lineup.published_at`.
C'est la garde qui empêche le backtest d'utiliser les compos officielles
pour des prédictions horodatées à T-24h.

### 2.7 H2H

| Feature | dtype | Formule | Fuite |
| --- | --- | --- | --- |
| `h2h_residual_goaldiff` | float32 | Voir doc 02 §J.2 | needs_lag |
| `h2h_residual_logodds` | float32 | Idem, en log-odds de victoire | needs_lag |
| `h2h_weight` | float32 | `Σ w_i` | safe |
| `h2h_n_matches` | int8 | Compte brut (affichage uniquement) | safe |

### 2.8 Marché (utilisées avec discipline — voir doc 08)

| Feature | dtype | Fuite | Usage autorisé |
| --- | --- | --- | --- |
| `market_prob_devig_opening` | float32 | safe | Ensemble + feature ML |
| `market_prob_devig_current` | float32 | safe si snapshot ≤ as_of_ts | Ensemble + feature ML |
| `market_overround` | float32 | safe | Qualité / liquidité |
| `market_n_bookmakers` | int8 | safe | Proxy de liquidité |
| `market_dispersion` | float32 | safe | Écart-type des probas entre books |
| `odds_drift_24h` | float32 | safe | Δ log-odds sur 24 h |
| `odds_drift_velocity` | float32 | safe | Δ log-odds par heure sur 3 h |
| `is_steam_move` | bool | safe | Mouvement concerté (doc 08) |
| `market_prob_devig_closing` | float32 | **forbidden** | **Évaluation uniquement (CLV)**, jamais en entrée de modèle |

---

## 3. Features spécifiques — football

| Feature | Formule | Fuite |
| --- | --- | --- |
| `xg_for_weighted`, `xg_against_weighted` | Pondérée + ajustée adversaire | needs_lag |
| `npxg_for_weighted` | xG hors penalty | needs_lag |
| `xg_diff_weighted` | Différence | needs_lag |
| `xg_overperformance` | `(buts − xG)` pondéré sur 12 matchs | needs_lag |
| `xpts_overperformance` | Points réels − points attendus des grilles xG | needs_lag |
| `shots_pg`, `sot_pg` | Pondéré | safe |
| `ppda`, `ppda_against` | Pondéré, normalisé par ligue-saison | needs_lag |
| `def_line_height_m` | Hauteur moyenne des actions défensives | needs_lag |
| `directness` | Progression verticale par passe | needs_lag |
| `counter_shot_ratio` | % de tirs ≤ 15 s après récupération | needs_lag |
| `setpiece_xg_share` | Part du xG sur CPA | needs_lag |
| `box_touches_pg` | Touches dans la surface | needs_lag |
| `corners_for_pg`, `corners_against_pg` | Poisson corners | safe |
| `fouls_pg`, `cards_pg` | Modèle cartons | safe |
| `keeper_psxg_minus_goals` | Sur-performance du gardien | needs_lag |
| `style_cluster_coords[0..7]` | Coordonnées dans l'espace de style | needs_lag |
| `matchup_press_vs_buildup` | Interaction (doc 02 §E) | needs_lag |
| `promoted_flag` | Promu cette saison | safe |
| `prev_division_strength` | Elo moyen de la division précédente | safe |

## 4. Features spécifiques — basketball

| Feature | Formule | Fuite |
| --- | --- | --- |
| `ortg_adj`, `drtg_adj` | Ratings ajustés adversaire | needs_lag |
| `pace_adj` | Pace ajusté adversaire | needs_lag |
| `expected_pace` | `f(pace_A, pace_B, moyenne ligue)` | needs_lag |
| `efg_pct`, `tov_pct`, `orb_pct`, `ft_rate` | Four factors, off & def | needs_lag |
| `three_pt_rate` | `3PA / FGA` | safe |
| `three_pt_pct_regressed` | `3P%` avec shrinkage bayésien vers la moyenne ligue | safe |
| `is_back_to_back` | `rest_days = 0` ou 1 | safe |
| `is_third_in_four` | 3 matchs en 4 jours | safe |
| `road_trip_game_number` | Rang dans un déplacement long | safe |
| `starters_rapm_sum` | Σ RAPM des 5 majeurs probables | needs_lag |
| `bench_rapm_avg` | RAPM moyen du banc | needs_lag |
| `minutes_concentration` | Indice de Herfindahl des minutes | needs_lag |
| `garbage_time_share` | % de minutes en garbage time (nettoyage) | needs_lag |

## 5. Features spécifiques — tennis

| Feature | Formule | Fuite |
| --- | --- | --- |
| `serve_points_won_pct` | Pondéré, ajusté par la qualité du relanceur | needs_lag |
| `return_points_won_pct` | Idem | needs_lag |
| `serve_pct_surface` | Restreint à la surface | needs_lag |
| `elo_surface_diff` | Δ Elo de surface | safe |
| `elo_overall_diff` | Δ Elo global | safe |
| `ace_rate`, `df_rate` | Pondéré | needs_lag |
| `first_serve_in_pct` | Pondéré | needs_lag |
| `first_serve_won_pct`, `second_serve_won_pct` | Pondéré | needs_lag |
| `minutes_played_7d`, `sets_played_7d` | Charge réelle | safe |
| `matches_since_return` | Retour de blessure | safe |
| `retirement_rate_24m` | Fréquence d'abandon | safe |
| `best_of` | 3 ou 5 sets | safe |
| `is_indoor` | Salle | safe |
| `altitude_m` | Altitude du tournoi | safe |
| `ranking_points`, `rank` | ATP/WTA (affichage + secours) | safe |
| `h2h_surface_residual` | H2H restreint à la surface | needs_lag |

---

## 6. Gestion des valeurs manquantes

Chaque feature déclare sa `null_policy`. Cinq politiques, jamais d'autre :

| Politique | Comportement | Quand l'utiliser |
| --- | --- | --- |
| `native` | On laisse NaN ; LightGBM gère nativement | Par défaut pour le GBM |
| `shrink_to_league_mean` | `(n·x + k·μ_ligue)/(n+k)` | Stats d'équipe avec peu de matchs |
| `shrink_to_prior_season` | Mélange avec la saison précédente | Début de saison |
| `explicit_zero_plus_flag` | 0 + colonne `is_missing` | Compteurs (ex. `extra_time_14d`) |
| `block_prediction` | La prédiction n'est pas produite | Features critiques absentes (pas de cote, pas de rating) |

**Règle d'or** : toute imputation crée une colonne compagnon
`{feature}_is_imputed`. Sans elle, le modèle ne peut pas apprendre que la
valeur est incertaine, et le score de qualité des données ne peut pas être
calculé.

**Interdit** : imputer par la moyenne calculée sur l'ensemble du dataset
(fuite temporelle — la moyenne inclut le futur). Les statistiques
d'imputation sont calculées sur la fenêtre d'entraînement uniquement et
figées dans l'artefact du modèle.

---

## 7. Versionnement et invalidation

Une feature a une `version`. Changer la formule ou un paramètre
(`half_life_days: 90 → 60`) **incrémente obligatoirement la version**, ce qui
crée une nouvelle colonne logique dans le feature store.

Conséquences :
- Les prédictions passées restent reproductibles (elles référencent `v3`).
- Un backtest déclare explicitement la version de chaque feature.
- Deux versions coexistent pendant la période de comparaison A/B.

Le vecteur de features envoyé à un modèle est hashé :

```
feature_hash = sha256( json_canonique( {nom@version: valeur} ) )
```

Ce hash est stocké dans la table `predictions`. Si on rejoue la prédiction et
que le hash diffère, l'alerte est immédiate : **quelque chose a changé dans
la donnée historique**. C'est le détecteur de révision rétroactive.

---

## 8. Volumétrie estimée

| Élément | Estimation |
| --- | --- |
| Features noyau | ~60 |
| Features football | ~45 |
| Features basketball | ~30 |
| Features tennis | ~28 |
| Features marché | ~12 |
| **Total exploitable football** | **~117** |
| Features réellement utilisées en V1 | **35 à 50** |

> Le passage de 117 à ~45 se fait par ablation mesurée (doc 07), pas par
> intuition. Avec 3 saisons de Ligue 1 + Premier League (~1500 matchs), le
> ratio observations/features doit rester supérieur à 25 pour éviter le
> surapprentissage : **1500 / 45 ≈ 33**. C'est acceptable. À 117 features,
> le ratio tombe à 13 et le modèle surapprend de façon garantie.
> **Cette contrainte est la vraie raison de la hiérarchisation du doc 02.**
