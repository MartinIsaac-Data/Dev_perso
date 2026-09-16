# 05 — Ratings, modèles statistiques et ML

> Ce document couvre : les systèmes de rating, les modèles de score, la
> comparaison des algorithmes ML, l'architecture d'ensemble et la
> calibration. C'est le cœur quantitatif du système.

---

## 1. Systèmes de rating : comparaison

Un rating est un **résumé compressé de la force**, mis à jour
séquentiellement. Son intérêt n'est pas la précision brute mais la
robustesse : il fonctionne avec peu de données, ne fuit pas si on respecte
l'ordre chronologique, et sert de prior à tous les autres modèles.

| | **Elo** | **Glicko-2** | **SPI-like** | **Poisson attaque/défense** | **Bayésien hiérarchique** |
| --- | --- | --- | --- | --- | --- |
| Sortie | 1 nombre | Rating + RD + volatilité | Off/Def rating + proba | α (attaque), β (défense) | Distributions postérieures |
| Modélise l'incertitude | Non | **Oui** | Non | Non (sauf erreurs std) | **Oui, nativement** |
| Gère les scores | Via facteur de marge | Non | Oui | **Oui, directement** | Oui |
| Sépare attaque/défense | Non | Non | Oui | **Oui** | Oui |
| Données nécessaires | Très peu | Peu | Moyennes | Moyennes | Moyennes |
| Coût de calcul | Trivial | Trivial | Faible | Faible (MLE) | **Élevé (MCMC)** |
| Gère l'inactivité | Non | **Oui** (RD augmente) | Partiel | Non | Oui |
| Multi-compétitions | Difficile | Difficile | Oui | Oui avec effets | **Oui, nativement** |
| Interprétabilité | Excellente | Bonne | Bonne | **Excellente** | Moyenne |
| Complexité d'implémentation | 20 lignes | 80 lignes | ~300 lignes | ~150 lignes | ~400 lignes + Stan/PyMC |
| Pertinence MVP | **Oui** | **Oui (tennis)** | Non | **Oui (football)** | Non (V2) |

### Recommandation

| Sport | Rating principal | Rating secondaire | Pourquoi |
| --- | --- | --- | --- |
| Football | **Poisson attaque/défense** (Dixon-Coles) | Elo pondéré par la marge | Le modèle de score a besoin d'α et β, pas d'un scalaire |
| Basketball | **Ratings ajustés (ORtg/DRtg/Pace)** | Elo pondéré par la marge | Le score se modélise par une normale sur le différentiel |
| Tennis | **Elo par surface** | Glicko-2 pour l'incertitude | Peu de matchs, inactivité fréquente : le RD de Glicko est précieux |

Le bayésien hiérarchique est **la bonne réponse à terme** (il gère
nativement le shrinkage inter-ligues, les promus, et l'incertitude), mais son
coût de calcul et de mise au point en fait une V2. Décision : on écrit
l'interface de rating de façon à pouvoir le brancher sans toucher au reste.

---

## 2. Elo, la version qu'on implémente réellement

### 2.1 Formule de base

```
E_A = 1 / ( 1 + 10^( -(R_A + H − R_B) / 400 ) )
R_A' = R_A + K · M · (S_A − E_A)
```

- `H` : avantage du terrain **en points Elo**, estimé par compétition
- `S_A` ∈ {1, 0.5, 0} (victoire, nul, défaite)
- `K` : vitesse d'apprentissage
- `M` : multiplicateur de marge de victoire

### 2.2 Multiplicateur de marge (indispensable au football)

Gagner 4-0 est plus informatif que gagner 1-0. Mais l'effet doit être
**logarithmique et corrigé de l'autocorrélation** : les équipes fortes
gagnent largement *parce qu'*elles sont fortes, ce qui gonfle leur Elo si on
n'y prend garde.

```
M = ln(|GD| + 1) · ( 2.2 / ( 0.001·|R_A + H − R_B| + 2.2 ) )
```

Le second terme amortit la marge quand l'écart de rating est déjà grand.

**Exemple calculé** : A (1720, avantage domicile 65) reçoit B (1650) et gagne
2-0.

```
E_A = 1 / (1 + 10^(-(1720+65-1650)/400)) = 0.6851
M   = ln(3) · (2.2 / (0.001·135 + 2.2)) = 1.0986 · 0.9422 = 1.0351 → 1.065 avec GD=2
R_A' = 1720 + 20 · 1.065 · (1 − 0.6851) = 1726.7          (soit +6.7)
```

Une victoire 2-0 attendue rapporte donc **moins de 7 points** : le système
est correctement peu réactif, ce qui est le comportement souhaité.

### 2.3 Choix de K

| Contexte | K |
| --- | --- |
| Football, championnat national | 20 |
| Football, coupe européenne | 24 (moins de matchs, plus d'information par match) |
| Basketball NBA | 14 (82 matchs, beaucoup de bruit par match) |
| Tennis | 24, décroissant avec le nombre de matchs joués : `K = 250/(n+5)^0.4` |

K est un hyperparamètre : il est **optimisé sur le log-loss en validation
temporelle**, pas choisi par tradition.

### 2.4 Gestion de l'intersaison et des promus

```
R_début_saison = μ_ligue + ρ · (R_fin_saison_précédente − μ_ligue)
```

avec ρ ≈ 0.75 (régression vers la moyenne de ligue). Pour un promu :

```
R_promu = μ_ligue_supérieure − δ  +  ρ' · (R_dans_division_inférieure − μ_division_inférieure)
```

où δ est l'écart moyen mesuré entre divisions (≈ 100-150 points Elo entre
deux divisions européennes). **Sans cet ajustement, les promus sont
systématiquement surévalués les 8 premières journées** — une des erreurs les
plus coûteuses en début de saison.

---

## 3. Modèle de score football : Poisson → Dixon-Coles

### 3.1 Poisson indépendant (le point de départ)

```
λ_dom = exp( μ + α_dom − β_ext + γ )        γ = avantage du terrain
λ_ext = exp( μ + α_ext − β_dom )

P(X = x, Y = y) = Poisson(x; λ_dom) · Poisson(y; λ_ext)
```

Les paramètres (μ, α_i, β_i, γ) sont estimés par maximum de vraisemblance
pondéré par la récence :

```
ℓ(θ) = Σ_i  φ_i · [ log Poisson(x_i; λ_dom,i) + log Poisson(y_i; λ_ext,i) ]
φ_i  = exp( −ξ · Δt_i )         ξ ≈ 0.0065 / jour  (demi-vie ≈ 107 jours)
```

avec la contrainte d'identifiabilité `Σα_i = 0` et `Σβ_i = 0`.

**Le défaut connu du Poisson indépendant** : il sous-estime les scores
nuls faibles (0-0, 1-1) et surestime les 1-0 / 0-1. L'écart est
systématique et suffisamment grand pour être exploitable *contre* vous.

### 3.2 Correction Dixon-Coles

```
P(X=x, Y=y) = τ(x, y, λ_dom, λ_ext, ρ) · Poisson(x; λ_dom) · Poisson(y; λ_ext)

τ(0,0) = 1 − λ_dom · λ_ext · ρ
τ(0,1) = 1 + λ_dom · ρ
τ(1,0) = 1 + λ_ext · ρ
τ(1,1) = 1 − ρ
τ(x,y) = 1              pour tout autre couple
```

Avec ρ < 0, la correction augmente P(0-0) et P(1-1) et diminue P(1-0) et
P(0-1) — exactement la distorsion observée. ρ est estimé conjointement,
typiquement entre −0.03 et −0.15 selon la ligue.

**Effet mesuré sur l'exemple du doc 15** (λ_dom = 1.62, λ_ext = 1.08,
ρ = −0.05) :

| Issue | Poisson indépendant | Dixon-Coles | Écart |
| --- | --- | --- | --- |
| P(1-1) | 0.1176 | 0.1235 | +0.59 pt |
| P(0-0) | 0.0672 | 0.0731 | +0.59 pt |
| P(1-0) | 0.1089 | 0.1030 | −0.59 pt |
| P(0-1) | 0.0726 | 0.0667 | −0.59 pt |
| **P(Nul)** | **0.2474** | **0.2591** | **+1.18 pt** |

Un écart de 1.18 point sur le nul, à une cote de 3.50, représente
**4.12 % d'EV** (`0.0118 × 3.50`).
C'est plus que tout ce qu'une feature exotique apportera jamais.
**Conclusion : la correction Dixon-Coles est non négociable, et elle est
gratuite.**

### 3.3 Alternative : Poisson bivarié / copules

| | Dixon-Coles | Poisson bivarié (Karlis-Ntzoufras) | Copule |
| --- | --- | --- | --- |
| Corrélation modélisée | Seulement sur les scores faibles | Positive uniquement | Arbitraire |
| Réalisme | Bon | Limité (la corrélation réelle est souvent négative) | Excellent |
| Complexité | Faible | Moyenne | Élevée |
| Recommandation | **V1** | Non | V3 |

Le Poisson bivarié classique ne peut modéliser qu'une corrélation **positive**
entre les scores, or la corrélation empirique au football est légèrement
négative. Dixon-Coles est donc à la fois plus simple et plus juste.

### 3.4 De la grille aux marchés

Une fois la grille `P(x,y)` calculée (on tronque à 12-12, la masse résiduelle
est < 10⁻⁶ et on renormalise), **tous** les marchés en dérivent :

```
P(1)          = Σ_{x>y} P(x,y)
P(X)          = Σ_{x=y} P(x,y)
P(2)          = Σ_{x<y} P(x,y)
P(Over n.5)   = Σ_{x+y > n} P(x,y)
P(BTTS)       = Σ_{x≥1, y≥1} P(x,y)
P(1X)         = P(1) + P(X)
P(score exact)= P(x,y)
P(AH −0.5)    = P(1)
P(AH −1.5)    = Σ_{x−y ≥ 2} P(x,y)
P(AH −0.25)   = 0.5·P(1) + 0.5·[P(1)/(P(1)+P(2))]   (moitié remboursée sur nul)
```

**C'est l'avantage décisif du modèle statistique sur le ML direct** : une
seule estimation (λ_dom, λ_ext, ρ) produit une distribution **cohérente**
sur tous les marchés. Un classifieur ML entraîné séparément sur 1X2, sur
Over 2.5 et sur BTTS produira des probabilités mutuellement incohérentes —
par exemple P(Over 2.5) et P(BTTS) incompatibles avec P(1X2). Cette
incohérence est immédiatement visible par un utilisateur et détruit la
crédibilité du produit.

---

## 4. Modèles de score des autres sports

### 4.1 Basketball — normale sur le différentiel

```
E[total]  = pace_attendu × (ORtg_A + ORtg_B) / 100
E[marge]  = pace_attendu × (ORtg_A − DRtg_B − ORtg_B + DRtg_A) / 100 + HCA

pace_attendu = pace_A × pace_B / pace_ligue

marge ~ Normale( E[marge], σ )        σ ≈ 11 à 12 points en NBA
P(victoire A) = Φ( E[marge] / σ )
P(total > L)  = 1 − Φ( (L − E[total]) / σ_total )      σ_total ≈ 15-17
```

σ est estimé empiriquement et **dépend du pace** : plus de possessions = plus
de variance absolue. Une régression de |résidu| sur le pace donne
σ(pace) directement.

### 4.2 Tennis — chaîne de Markov sur le point

Tout découle de deux nombres : `p` = probabilité que A gagne un point sur son
service, `q` = probabilité que B gagne un point sur le sien.

```
P(gagner un jeu | p)   → formule fermée (somme sur les chemins jusqu'à 40-40 + suite géométrique)
P(gagner un set)       → convolution sur les jeux + tie-break
P(gagner le match)     → best-of-3 ou best-of-5
```

L'estimation de `p` et `q` se fait par ajustement mutuel :

```
p_A = serve_won_A_ajusté + (return_won_B_moyen_tour − return_won_moyen_ligue)
```

**Avantage majeur** : ce modèle produit nativement les marchés de sets, de
jeux, de handicap de jeux et de total de jeux, tous cohérents entre eux.
C'est un des rares sports où le modèle structurel bat très largement toute
approche ML directe.

**Piège tennis n°1** : les abandons. Un match perdu par abandon n'est pas un
match perdu ; il faut une politique explicite (exclusion de l'échantillon
d'entraînement, mais comptabilisation dans le dénouement des paris, qui suit
les règles du bookmaker).

---

## 5. Machine Learning : comparaison argumentée

### 5.1 Le contexte statistique qui décide de tout

| Contrainte | Valeur réaliste |
| --- | --- |
| Observations (3 saisons, 5 ligues) | ~5 500 matchs |
| Features candidates | 45 à 117 |
| Ratio obs/features | 47 à 120 |
| Rapport signal/bruit | **Très faible** : le meilleur modèle public bat à peine le marché |
| Non-stationnarité | Forte (règles, VAR, COVID, styles) |
| Classes | 3 déséquilibrées (~45/25/30) |

**Ce contexte disqualifie le deep learning.** Pas par principe, mais par
arithmétique : un réseau de neurones a besoin de beaucoup plus de données
que ce que le sport en produit. Le football mondial produit environ 200 000
matchs de haut niveau par an, toutes ligues confondues — et seule une
fraction est utilisable avec des stats avancées. Un LLM s'entraîne sur 10¹³
tokens ; ici on dispose de 10⁴ lignes. La régularisation implicite d'un
modèle simple est un avantage, pas une limitation.

### 5.2 Comparaison

| Modèle | Force | Faiblesse | Verdict V1 |
| --- | --- | --- | --- |
| **Régression logistique (multinomiale)** | Calibrée nativement, interprétable, très robuste en petit échantillon, extrapole raisonnablement | Pas d'interactions sans les écrire à la main | **Oui — baseline obligatoire** |
| **Régression logistique ordinale** | Exploite l'ordre H > D > A | Hypothèse de proportionnalité discutable | Oui, à tester |
| **Random Forest** | Robuste, peu de réglage | **Mal calibré** (probabilités tassées vers 0.5), n'extrapole pas | Non |
| **XGBoost** | Très performant, mature | Réglage sensible, plus lent que LightGBM | Alternative |
| **LightGBM** | Rapide, gère nativement les NaN et les catégories, `monotone_constraints` | Surapprend vite en petit échantillon | **Oui — modèle ML principal** |
| **CatBoost** | Excellent sur les catégorielles, moins de surapprentissage par ordered boosting | Plus lent, moins de contrôle fin | Alternative sérieuse |
| **Réseaux de neurones** | Capacité de représentation | Données insuffisantes, calibration instable, non interprétable | **Non en V1** |
| **Modèles bayésiens (PyMC/Stan)** | Incertitude native, shrinkage hiérarchique, priors experts | Coût de calcul, courbe d'apprentissage | **V2** |
| **Poisson / Dixon-Coles** | Cohérence multi-marchés, peu de paramètres, interprétable | Ignore les features contextuelles | **Oui — modèle statistique principal** |
| **Ensemble (stacking)** | Combine des biais différents | Risque de double comptage, plus difficile à diagnostiquer | **Oui** |

### 5.3 Pourquoi LightGBM et pas un réseau — le raisonnement complet

1. **Nature des features** : essentiellement tabulaires, hétérogènes,
   partiellement manquantes. C'est exactement le domaine où les GBM dominent
   encore les réseaux dans la littérature (les benchmarks tabulaires le
   confirment de façon constante).
2. **Interactions** : ce qu'on cherche vraiment (fatigue × profondeur
   d'effectif, enjeu × rotation, style A × style B) est une interaction
   d'ordre 2-3 entre variables tabulaires. Un GBM à profondeur 4 les capte
   naturellement.
3. **Contraintes de monotonie** : LightGBM permet d'imposer que
   P(victoire domicile) soit croissante en `elo_diff`. **C'est un outil de
   régularisation redoutable** dans un contexte de faible signal : il
   interdit au modèle d'apprendre des non-monotonies absurdes issues du
   bruit. Un réseau ne l'offre pas simplement.
4. **Explicabilité** : SHAP sur un GBM est exact et rapide (TreeSHAP). Sur un
   réseau, c'est approximatif et coûteux. Or l'explicabilité est une
   exigence produit (doc 11), pas un confort.
5. **Coût** : entraînement en secondes ⇒ on peut se permettre une validation
   temporelle glissante à 50 plis, ce qui est la seule façon honnête
   d'évaluer ici.

### 5.4 Hyperparamètres de départ (LightGBM, objectif multiclasse)

```python
params = {
    "objective": "multiclass", "num_class": 3, "metric": "multi_logloss",
    "learning_rate": 0.02,
    "num_leaves": 15,              # volontairement petit : ~5 500 lignes
    "max_depth": 4,
    "min_data_in_leaf": 120,       # fort : évite les feuilles anecdotiques
    "feature_fraction": 0.7,
    "bagging_fraction": 0.8, "bagging_freq": 1,
    "lambda_l1": 0.5, "lambda_l2": 5.0,
    "monotone_constraints": [...], # +1 sur elo_diff, xg_diff ; -1 sur pits_missing
    "num_boost_round": 3000, "early_stopping_rounds": 150,
}
```

`num_leaves = 15` et `min_data_in_leaf = 120` semblent très conservateurs.
Ils le sont délibérément : avec ce rapport signal/bruit, **tout modèle qui
semble bien apprendre apprend du bruit.**

---

## 6. Architecture d'ensemble

```
   ┌──────────────────────┐  ┌──────────────────────┐  ┌────────────────────┐  ┌──────────────────┐
   │  M1 Statistique      │  │  M2 ML (LightGBM)    │  │  M3 Rating         │  │  M4 Marché       │
   │  Dixon-Coles         │  │  features contexte   │  │  Elo → logistique  │  │  cotes dévigo-   │
   │  → grille de scores  │  │  → P(H/D/A)          │  │  → P(H/D/A)        │  │  risées (Shin)   │
   └──────────┬───────────┘  └──────────┬───────────┘  └─────────┬──────────┘  └────────┬─────────┘
              │                         │                        │                      │
              └─────────────┬───────────┴────────────┬───────────┴──────────────────────┘
                            ▼                        ▼
                  ┌───────────────────────────────────────────┐
                  │  STACKING  : régression logistique         │
                  │  multinomiale sur les LOG-ODDS des         │
                  │  membres, entraînée en validation          │
                  │  temporelle out-of-fold                    │
                  └────────────────────┬──────────────────────┘
                                       ▼
                  ┌───────────────────────────────────────────┐
                  │  CALIBRATION : isotonique (ou beta)        │
                  │  sur fenêtre glissante 18 mois             │
                  └────────────────────┬──────────────────────┘
                                       ▼
                             PROBABILITÉ FINALE  +  σ (bootstrap)
```

### 6.1 Le stacking, concrètement

Chaque membre *m* produit `p_m = (p_H, p_D, p_A)`. Le méta-modèle prend en
entrée les log-odds :

```
z_m,k = log( p_m,k / (1 − p_m,k) )

logit P_final,k  =  w_0,k + Σ_m w_m,k · z_m,k  +  v · reliability
```

Deux raisons de travailler en log-odds plutôt qu'en probabilités :

1. L'espace des log-odds est non borné : la combinaison linéaire ne sort
   jamais de [0,1] après la sigmoïde.
2. Un mélange linéaire de probabilités bien calibrées est **sous-confiant**
   (il tire vers le centre). Un mélange en log-odds préserve la netteté.

### 6.2 Le problème du double comptage — et sa solution

C'est le risque principal de cette architecture. Trois canaux de fuite
d'information entre membres :

| Double comptage | Mécanisme | Solution retenue |
| --- | --- | --- |
| M1 et M3 partagent la force d'équipe | Les λ de Dixon-Coles et l'Elo mesurent la même chose | **On ne donne pas l'Elo au modèle ML** : M2 reçoit le contexte (fatigue, enjeu, absences), pas la force brute. M3 reste un membre indépendant |
| M2 reçoit `market_prob` **et** M4 est le marché | Le marché compte double, les poids deviennent instables | **Deux variantes de M2 entraînées** : `M2_nomarket` (sans feature marché) dans l'ensemble, `M2_market` uniquement pour diagnostic. Décision par défaut : **le marché n'entre que par M4** |
| Le stacking est entraîné sur les mêmes matchs que les membres | Le méta-modèle surestime les membres surappris | **Prédictions out-of-fold obligatoires** : chaque membre prédit un pli qu'il n'a jamais vu, en respectant l'ordre temporel |

**Diagnostic permanent** : on surveille la matrice de corrélation des
log-odds entre membres. Si `corr(M1, M3) > 0.95`, les deux membres sont
redondants et il faut en fusionner un. En pratique, on observe typiquement :

```
          M1(stat)  M2(ML)  M3(rating)  M4(marché)
M1          1.00
M2          0.72     1.00
M3          0.88     0.66      1.00
M4          0.81     0.70      0.79        1.00
```

`corr(M1, M3) = 0.88` est élevé mais acceptable ; il justifie de donner à M3
un poids faible dans le stacking — ce que le méta-modèle fera de lui-même.

### 6.3 Combien de poids donner au marché ?

C'est **la** décision la plus lourde de conséquences du projet.

| Poids marché | Conséquence |
| --- | --- |
| `w = 0` | Le modèle ignore une information de très haute qualité. Log-loss dégradé, mais les edges détectés sont « purs » — et souvent faux |
| `w = 0.3 – 0.4` | Zone recommandée. Le modèle reste capable de s'écarter du marché quand il a une raison forte |
| `w = 0.7+` | Le modèle devient un lisseur de cotes. Excellent log-loss, **zéro value détectable** |
| `w = 1` | Vous avez réimplémenté le bookmaker |

**Recommandation** : laisser le stacking **estimer** `w` sur données
historiques, puis le **plafonner** à 0.45. Le plafond est une décision de
produit : au-delà, le système n'a plus d'utilité propre.

Impact mesuré sur l'exemple du doc 15 :

```
EV sans blend marché (w=0)     : +3.61 %
EV avec blend w = 0.35         : +1.30 %
```

Le blend absorbe **64 % de l'edge apparent**. C'est douloureux et c'est
correct : la plus grande partie de cet edge était de l'excès de confiance du
modèle.

---

## 7. Calibration

### 7.1 Pourquoi elle prime sur l'accuracy

Un modèle qui annonce 60 % et gagne 60 % du temps est **parfait**, même si
son accuracy n'est que de 60 %. Un modèle qui annonce 90 % et gagne 60 % du
temps est dangereux : il produira des mises Kelly catastrophiques.

En pari sportif, **une probabilité mal calibrée n'est pas une imprécision,
c'est une perte financière directe et quantifiable** :

```
Perte d'EV = (p_annoncée − p_réelle) × cote
```

Une sur-confiance de 3 points à une cote de 2.50 coûte 7.5 % d'EV — soit
plus que tout l'edge espéré.

### 7.2 Méthodes

| Méthode | Principe | Avantages | Inconvénients | Verdict |
| --- | --- | --- | --- | --- |
| **Platt scaling** | Sigmoïde ajustée sur les scores | 2 paramètres, robuste en petit échantillon | Impose une forme sigmoïde | Bon si < 1 000 obs |
| **Isotonique** | Fonction monotone par morceaux | Non paramétrique, très flexible | Surapprend sous ~1 000 obs ; escaliers | **Retenu** (> 2 000 obs) |
| **Beta calibration** | Famille à 3 paramètres | Plus souple que Platt, plus stable qu'isotonique | Moins connu | **Retenu si échantillon limité** |
| **Vector/temperature scaling** | Un paramètre global de température | Trivial, préserve le classement | Correction uniforme seulement | Complément utile |

**Décision** : isotonique par défaut, beta en repli sous 2 000 observations,
**réajustée mensuellement sur une fenêtre glissante de 18 mois**. La
calibration est un artefact versionné au même titre que le modèle
(`ml.model_versions.calibrator_uri`).

### 7.3 Contrainte de somme

Après calibration séparée des trois issues, la somme ne fait plus 1. Deux
options :

- *Option A* : renormalisation proportionnelle. Simple, mais déforme
  légèrement la calibration.
- *Option B (retenue)* : calibration **multiclasse** (Dirichlet ou vector
  scaling sur les log-odds), qui préserve la contrainte par construction.

En pratique, l'écart après isotonique séparée est de l'ordre de 1-2 % ; la
renormalisation proportionnelle reste acceptable en V1, et la calibration
multiclasse est un objectif V2.

---

## 8. Métriques d'évaluation : lesquelles comptent vraiment

| Métrique | Formule | Pertinence ici |
| --- | --- | --- |
| **Log loss** | `−(1/N) Σ Σ y_ik log p_ik` | **Primaire.** Pénalise sévèrement la sur-confiance, qui est le péché mortel |
| **Brier score (multiclasse)** | `(1/N) Σ Σ (p_ik − y_ik)²` | **Primaire.** Décomposable en fiabilité − résolution + incertitude |
| **Brier Skill Score** | `1 − BS/BS_ref` | **Primaire.** Référence = marché dévigorisé. C'est la seule question qui compte |
| **ECE** | `Σ_b (n_b/N)·|acc_b − conf_b|` | **Primaire.** Mesure l'écart de calibration |
| **MCE** | `max_b |acc_b − conf_b|` | Secondaire, sensible aux bacs peu peuplés |
| **Courbe de fiabilité** | Graphique | **Primaire** pour le diagnostic visuel |
| **ROC-AUC** | Aire sous la courbe | **Secondaire.** Mesure le classement, pas la calibration. Un modèle peut avoir un AUC excellent et être inutilisable |
| **Accuracy** | % de bonnes prédictions | **Quasi inutile.** Sur du 1X2, prédire toujours « domicile » donne ~45 %. Ne jamais l'afficher comme métrique principale |
| **Precision / Recall / F1** | — | **Non pertinentes.** Elles supposent une décision binaire ; le système ne décide pas, il estime |
| **CLV** | `cote_prise / cote_clôture − 1` | **La métrique reine en production** (doc 07) |
| **ROI / Yield** | Profit / mise | Mesure bruitée à court terme. Nécessaire mais très lente à converger |

### La décomposition de Murphy — l'outil de diagnostic

```
Brier = Fiabilité − Résolution + Incertitude
```

| Terme | Signification | Que faire s'il est mauvais |
| --- | --- | --- |
| **Fiabilité** (bas = bon) | Écart entre probabilité annoncée et fréquence observée | Problème de **calibration** → recalibrer |
| **Résolution** (haut = bon) | Capacité à s'écarter du taux de base | Problème de **features/modèle** → il n'y a pas assez de signal |
| **Incertitude** | Variance intrinsèque du phénomène | Irréductible. C'est le plancher |

Cette décomposition dit **quoi corriger**. Un Brier médiocre avec une bonne
fiabilité et une faible résolution signifie : le modèle est honnête mais ne
sait rien. Recalibrer n'y changera rien — il faut de meilleures features. À
l'inverse, une mauvaise fiabilité se corrige en une après-midi.

---

## 9. Quantifier l'incertitude de la probabilité elle-même

Le système doit produire non seulement `p` mais `σ_p`. Trois sources :

| Source d'incertitude | Méthode d'estimation |
| --- | --- |
| **Paramètres** (λ, α, β mal estimés) | Bootstrap par blocs temporels : ré-estimer le modèle sur B = 200 rééchantillons, observer la dispersion de `p` |
| **Features** (données manquantes, compo inconnue) | Propagation : simuler les compositions selon `p(titulaire)`, recalculer, observer la dispersion |
| **Désaccord entre membres** | Écart-type des `p_m` de l'ensemble |

```
σ_p = sqrt( σ²_paramètres + σ²_features + σ²_désaccord )
```

**Usage** : le signal de value n'est émis que si

```
EV − k · σ_EV  >  seuil        avec k ≈ 1
```

C'est-à-dire : **l'edge doit survivre à un écart-type d'incertitude.** Sur
l'exemple du doc 15, avec un EV de +1.30 % et un σ_EV de l'ordre de 2.5 %
(déduit de la table de sensibilité), le signal est **rejeté**. C'est le
comportement souhaité.
