# 15 — Un match traité de bout en bout

> Tous les chiffres de ce document ont été **calculés**, pas illustrés. La
> grille Dixon-Coles, les quatre méthodes de dévigorisation, le stacking, les
> EV, le Kelly et la table de sensibilité sortent du même code que celui
> spécifié dans ce dossier.
>
> Le match est fictif ; le mécanisme ne l'est pas.

---

## Le match

```
Ligue 1 · Journée 7 · dimanche 20 septembre 2026, 20h00 (UTC+2)
FC NANTES (dom.)  vs  STADE RENNAIS (ext.)
Stade de la Beaujoire · pelouse naturelle · altitude 25 m · à guichets ouverts
```

---

## T−7 j · Ingestion du calendrier

```
Provider fixtures → raw.observations
  entity_kind = 'match'
  fetched_at  = 2026-09-13T04:12:00Z
  payload     = { "id":"prov-88213", "date":"2026-09-20T18:00:00Z",
                  "home":"FC Nantes", "away":"Stade Rennais", ... }

Résolution d'entités :
  "FC Nantes"     → competitor_id 101   (mapping exact, external_ref)
  "Stade Rennais" → competitor_id 118   (mapping exact, external_ref)

Canonisation → core.matches
  match_id 884213 · kickoff_utc 2026-09-20T18:00:00Z · venue_id 44 · status scheduled
```

## T−7 j · Cotes d'ouverture

```
market.selections créées : 1X2 (H/D/A), OU 2.5, BTTS, AH…
market.odds_snapshots, is_opening = true :
  H 2.14 · D 3.45 · A 3.55   (Pinnacle, 2026-09-13T10:00:00Z)
```

## T−5 j → T−3 j · Statistiques et ratings

```
stats.football_team_match alimentée pour les journées 1 à 6
compute_ratings → features.ratings_snapshots (computed_at 2026-09-17T03:00:00Z)

  Nantes  : Elo 1720 · attaque α=+0.18 · défense β=−0.06 · σ=42
  Rennes  : Elo 1650 · attaque α=+0.04 · défense β=+0.02 · σ=38
  Ligue 1 : μ = 0.28 buts (log) · avantage domicile γ = +0.27 · ρ = −0.05
```

## T−72 h · Blessures

```
core.availabilities
  player_id 5521 (Mostafa, attaquant) · status 'injured'
  valid_from 2026-09-17 · recorded_at 2026-09-17T14:20:00Z
  expected_return 2026-10-05
```

## T−24 h · Premier run de prédiction (`pre-lineup`)

Compositions inconnues → `lineup_status = 'unknown'`, `data_quality = 0.81`.
Cette prédiction est archivée mais n'est pas celle qui compte.

## T−60 min · Compositions officielles

```
core.lineups · source='official' · published_at 2026-09-20T17:00:00Z
  Nantes : Mostafa absent (confirmé). Remplacé par Diallo (PITS 0.031).
  Rennes : équipe type.

→ événement lineup_published(884213)
→ recalcul des features
→ run de prédiction #2 (celui qui compte)
```

---

## Étape 1 — Le vecteur de features (extrait)

`as_of_ts = 2026-09-20T17:05:00Z`

| Feature | Valeur | Origine |
| --- | --- | --- |
| `elo_diff` | +74.3 | 1720 + 65 (avantage domicile en points Elo) − 1650 − 4.7 (correction forme) |
| `rating_attack_home` | +0.18 | Ajustement Poisson |
| `rating_defense_away` | +0.02 | Ajustement Poisson |
| `home_advantage_competition` | +0.27 | Ligue 1, saison en cours, avec shrinkage |
| `xg_for_weighted_home` | 1.54 | Pondéré H = 90 j, ajusté adversaire |
| `xg_against_weighted_away` | 1.31 | idem |
| `xg_diff_weighted` | +0.41 | Différence des deux formes |
| `xpts_overperformance_home` | −1.8 | Nantes sous-performe son xG : signal de retour à la moyenne |
| `pits_missing_off_home` | −0.090 | Mostafa (0.121) − Diallo (0.031) |
| `pits_missing_off_away` | 0.000 | Aucun absent significatif |
| `rest_days_home` | 3 | Match de coupe mercredi |
| `rest_days_away` | 6 | |
| `matches_7d_home` | 2 | |
| `travel_km_away` | 108 | Rennes → Nantes |
| `fatigue_score_home` | 26.9 | Formule du doc 02 §F (affichage uniquement) |
| `stakes_swing_home` | 0.031 | Faible : journée 7 |
| `stakes_swing_away` | 0.028 | Faible |
| `h2h_residual_goaldiff` | +0.06 | Quasi nul |
| `h2h_weight` | 0.41 | **Faible → le modèle l'ignorera** |
| `lineup_status` | confirmed | |
| `market_prob_devig_current` | 0.4617 | Consensus Shin, 11 bookmakers |
| `n_bookmakers` | 11 | |
| `market_dispersion` | 0.0089 | Faible dispersion → marché confiant |
| `temperature_c` / `wind_kmh` | 16.0 / 12 | Rien d'extrême |

`feature_hash = sha256(...) = 4f1c…9ab2` · `completeness = 0.94`

---

## Étape 2 — Le modèle statistique (Dixon-Coles)

```
λ_dom = exp( μ + α_Nantes − β_Rennes + γ + ajustement_effectif + ajustement_fatigue )
      = exp( 0.28 + 0.18 − 0.02 + 0.27 − 0.054 − 0.171 )
      = exp( 0.485 )
      = 1.62

λ_ext = exp( μ + α_Rennes − β_Nantes )
      = exp( 0.28 + 0.04 + 0.06 − 0.302 )
      = exp( 0.078 )
      = 1.08

ρ = −0.05      (estimé sur la Ligue 1, 5 saisons)
```

> Le terme `ajustement_effectif = −0.054` provient du PITS :
> `γ_PITS × pits_missing_off = 0.60 × (−0.090)`. L'absence de Mostafa retire
> **5.4 % de buts attendus**, pas 30 % comme le suggérerait une lecture
> naïve de son nombre de buts.

### La grille de scores (extrait, 12×12 tronquée et renormalisée)

| Score | P |
| --- | --- |
| 1-1 | **0.1235** |
| 1-0 | 0.1030 |
| 2-1 | 0.0950 |
| 2-0 | 0.0880 |
| 0-0 | 0.0731 |
| 0-1 | 0.0667 |
| 1-2 | 0.0630 |
| 3-1 | 0.0510 |

### Tous les marchés dérivés de cette seule grille

| Marché | Probabilité |
| --- | --- |
| Victoire Nantes | **0.4934** |
| Nul | **0.2591** |
| Victoire Rennes | **0.2475** |
| 1X (double chance) | 0.7525 |
| 12 | 0.7409 |
| X2 | 0.5066 |
| Over 0.5 | 0.9269 |
| Over 1.5 | 0.7572 |
| **Over 2.5** | **0.5064** |
| Over 3.5 | 0.2859 |
| Over 4.5 | 0.1371 |
| Under 2.5 | 0.4936 |
| **BTTS oui** | **0.5356** |
| BTTS non | 0.4644 |
| Buts attendus dom. / ext. / total | 1.62 / 1.08 / **2.70** |

**Vérification de cohérence** : `P(1) + P(X) + P(2) = 1.0000`. Toutes les
probabilités proviennent de la même distribution jointe, donc aucune
incohérence entre marchés n'est possible par construction.

---

## Étape 3 — Les quatre membres de l'ensemble

| Membre | P(Nantes) | P(Nul) | P(Rennes) | Poids (stacking) |
| --- | --- | --- | --- | --- |
| **M1** Dixon-Coles | 0.4934 | 0.2591 | 0.2475 | 0.40 |
| **M2** LightGBM (contexte, sans feature marché) | 0.4879 | 0.2595 | 0.2527 | 0.15 |
| **M3** Rating (Elo → logistique) | 0.5020 | 0.2550 | 0.2430 | 0.10 |
| **M4** Marché (Shin, 11 books) | 0.4617 | 0.2731 | 0.2652 | **0.35** |

Écart-type des membres sur P(Nantes) : **0.0150** → bon accord de
l'ensemble, ce qui alimente positivement le score de fiabilité.

### Stacking en log-odds

```
logit P_final,k = Σ_m  w_m · logit(p_m,k)      puis renormalisation

Pour H :
  0.40 × logit(0.4934) + 0.15 × logit(0.4879)
+ 0.10 × logit(0.5020) + 0.35 × logit(0.4617)
```

| Issue | Probabilité finale |
| --- | --- |
| Nantes | **0.4824** |
| Nul | **0.2636** |
| Rennes | **0.2540** |

Puis **calibration isotonique** (fenêtre 18 mois, Ligue 1) : sur ce bac de
probabilité le calibrateur est proche de l'identité, l'ajustement est
< 0.2 point. Probabilité finale retenue : **0.4824**.

> Noter l'effet du membre marché : le modèle « pur » disait 49.34 %, le
> marché 46.17 %, le résultat est 48.24 %. **Le marché a absorbé 35 % de
> l'écart.** C'est voulu, et c'est ce qui empêche le système de courir après
> ses propres erreurs.

---

## Étape 4 — Le marché

Meilleures cotes disponibles, 11 bookmakers, snapshot à T−56 min :

| Issue | Meilleure cote | Book | `1/o` |
| --- | --- | --- | --- |
| Nantes | 2.10 | Bet365 | 0.4762 |
| Nul | 3.50 | Unibet | 0.2857 |
| Rennes | 3.60 | Winamax | 0.2778 |
| | | **Somme** | **1.0397** |

Overround = **3.97 %**.

### Dévigorisation, quatre méthodes

| Méthode | P(Nantes) | P(Nul) | P(Rennes) | Paramètre |
| --- | --- | --- | --- | --- |
| Proportionnelle | 0.4580 | 0.2748 | 0.2672 | — |
| Additive | 0.4630 | 0.2725 | 0.2646 | — |
| Odds-ratio | 0.4609 | 0.2734 | 0.2657 | c = 0.9406 |
| **Shin (retenue)** | **0.4617** | **0.2731** | **0.2652** | z = 0.0199 |

---

## Étape 5 — Fair odds, edge et EV

| Issue | P modèle | P marché | Fair odds | Cote | Edge | **EV** | Kelly |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Nantes** | 0.4824 | 0.4617 | **2.073** | 2.10 | **+2.07 pts** | **+1.30 %** | 1.19 % |
| Nul | 0.2636 | 0.2731 | 3.793 | 3.50 | −0.95 pt | −7.73 % | — |
| Rennes | 0.2540 | 0.2652 | 3.937 | 3.60 | −1.12 pt | −8.57 % | — |

### Le calcul, ligne par ligne, pour Nantes

```
Probabilité implicite brute   q = 1 / 2.10                 = 0.4762
Overround                     V = 0.4762+0.2857+0.2778     = 1.0397
Probabilité de marché (Shin)  p_mkt                        = 0.4617
Probabilité du modèle         p_mod                        = 0.4824
Fair odds                     o* = 1 / 0.4824              = 2.073
Edge                          e  = 0.4824 − 0.4617         = +0.0207   (+2.07 pts)
Expected Value                EV = 0.4824 × 2.10 − 1       = +0.0130   (+1.30 %)
Seuil de rentabilité          p_min = 1 / 2.10             = 0.4762
Marge à franchir              0.4762 − 0.4617              = +1.45 pt
Kelly complet                 f* = 0.0130 / 1.10           = 0.0119   (1.19 %)
Kelly 1/4                     f  = 0.0119 / 4              = 0.0030   (0.30 %)
```

---

## Étape 6 — La décision : **pas de pari**

Les sept conditions du doc 06 §4.2 :

| # | Condition | Résultat |
| --- | --- | --- |
| 1 | `EV − 1·σ_EV > 2 %` | **ÉCHEC** — EV = +1.30 %, σ_EV ≈ 2.5 % → borne basse = −1.2 % |
| 2 | `data_quality ≥ 0.75` | ✓ 0.94 |
| 3 | `n_bookmakers ≥ 5` | ✓ 11 |
| 4 | Cote non aberrante | ✓ médiane 2.06, écart dans les clous |
| 5 | `max_stake` suffisante | ✓ 2 500 € |
| 6 | Pas de mouvement > 3 % en 10 min | ✓ marché stable |
| 7 | Calibration validée sur ce bac | ✓ ECE 0.018 en 45-55 % |

```
ml.value_signals
  threshold_passed   = false
  suppression_reason = "ev_below_uncertainty_adjusted_threshold"
```

### Pourquoi c'est le bon résultat

La table de sensibilité (calculée en faisant varier les λ de ±5 % et ±10 %) :

| λ_dom | λ_ext | P(Nantes) finale | EV @ 2.10 |
| --- | --- | --- | --- |
| 1.458 (−10 %) | 1.080 | 45.52 % | −4.40 % |
| 1.539 (−5 %) | 1.080 | 46.89 % | **−1.52 %** |
| **1.620** | **1.080** | **48.23 %** | **+1.30 %** |
| 1.701 (+5 %) | 1.080 | 49.52 % | **+3.99 %** |
| 1.782 (+10 %) | 1.080 | 50.78 % | +6.64 % |
| 1.620 | 0.972 (−10 %) | 49.92 % | +4.82 % |
| 1.620 | 1.188 (+10 %) | 46.61 % | −2.13 % |

**Une erreur de 5 % sur un seul paramètre — ce qui est parfaitement banal —
fait basculer le pari de −1.52 % à +3.99 % d'EV.** L'edge mesuré est plus
petit que l'incertitude du modèle sur lui-même. Parier ici, ce n'est pas
exploiter une inefficience de marché : c'est parier sur la précision de son
propre λ.

C'est le cas **le plus fréquent**, et un système honnête doit le dire.

---

## Étape 7 — Ce qui aurait changé la décision

| Scénario | Conséquence |
| --- | --- |
| Mostafa disponible (λ_dom 1.71) | P = 49.52 % · EV = **+3.99 %** → signal émis, mise 1/4 Kelly = 0.91 % |
| Cote montée à 2.15 | EV = **+3.72 %** → signal émis |
| Compo non confirmée | `data_quality` ≈ 0.72 → **condition 2 en échec**, aucun signal quoi qu'il arrive |
| Marché à 2.10 mais 3 books seulement | **Condition 3 en échec** |
| Cote de 2.35 chez un seul book, médiane à 2.06 | **Condition 4 en échec** — traitée comme suspecte, pas comme une aubaine |

---

## T+0 → T+2 h · Dénouement et évaluation

```
Résultat final : Nantes 2 − 1 Rennes     → outcome_1x2 = 'H'

Évaluation de la prédiction (aucun pari n'a été placé) :
  Brier (multiclasse) = (0.4824−1)² + (0.2636−0)² + (0.2540−0)²  = 0.4019
  Log loss            = −ln(0.4824)                              = 0.7290

  Référence marché :
  Brier marché        = (0.4617−1)² + (0.2731−0)² + (0.2652−0)²  = 0.4347
  Log loss marché     = −ln(0.4617)                              = 0.7728

  → sur ce match, le modèle bat le marché.
  → un match ne prouve rien. Seule la moyenne sur 2 000+ matchs a un sens.

Cote de clôture (Pinnacle) : 2.04
CLV hypothétique si le pari avait été pris à 2.10 : 2.10/2.04 − 1 = +2.94 %
  → la décision aurait été bonne en termes de CLV, même si le signal a été
    supprimé. Ce cas est enregistré : si les signaux supprimés affichent
    systématiquement un CLV positif, c'est que le seuil est trop strict.
```

> Ce dernier point est une boucle de retour essentielle. **Le système mesure
> aussi la qualité de ses abstentions.** Sans cela, on ne peut pas savoir si
> la prudence est calibrée ou simplement paralysante.

---

## Synthèse du parcours

```
Fixture (T−7j) → Cotes d'ouverture → Stats → Ratings → Blessures
      ↓
Compos officielles (T−60min) → 45 features point-in-time (hash 4f1c…9ab2)
      ↓
M1 Dixon-Coles 49.34 %  ·  M2 ML 48.79 %  ·  M3 Rating 50.20 %  ·  M4 Marché 46.17 %
      ↓  stacking en log-odds (0.40 / 0.15 / 0.10 / 0.35)
48.24 %
      ↓  calibration isotonique (< 0.2 pt)
48.24 %  ·  σ ≈ 2.5 pts
      ↓  vs marché Shin 46.17 %  ·  cote 2.10
Fair odds 2.073  ·  Edge +2.07 pts  ·  EV +1.30 %  ·  Kelly 1.19 %
      ↓  7 conditions de décision
AUCUN SIGNAL — l'edge ne survit pas à l'incertitude
      ↓  après le match
Brier 0.4019 vs marché 0.4347  ·  CLV hypothétique +2.94 %  ·  archivé
```
