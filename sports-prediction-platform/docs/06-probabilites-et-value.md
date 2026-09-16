# 06 — Probabilités, fair odds, EV et bankroll

> Toutes les formules de ce document sont implémentées dans un module unique
> (`platform/valuation/`), testées par propriétés, et utilisées à l'identique
> par le dashboard et par le moteur de backtest. Une divergence entre les deux
> serait invisible et fatale.

---

## 1. Probabilité implicite d'une cote

### 1.1 Formule brute

Pour une cote décimale `o` :

```
q_brut = 1 / o
```

`q_brut` **n'est pas une probabilité** : c'est une probabilité *plus la
marge du bookmaker*. La somme sur toutes les issues d'un marché dépasse 1.

```
Overround (vigorish)  :   V = Σ_k (1 / o_k)
Marge en %            :   m = V − 1
Marge normalisée      :   m_norm = (V − 1) / V      ← la vraie « part » prise
```

**Exemple réel** (le match du doc 15) :

| Issue | Cote | `1/o` |
| --- | --- | --- |
| Domicile | 2.10 | 0.4762 |
| Nul | 3.50 | 0.2857 |
| Extérieur | 3.60 | 0.2778 |
| **Somme** | | **1.0397** |

Overround = **3.97 %**. Marge normalisée = 3.82 %.

### 1.2 Retirer la marge : cinq méthodes

C'est un problème **mal posé** : on observe 3 nombres et on cherche 3
probabilités qui somment à 1, plus un paramètre de marge. Il faut une
hypothèse sur *comment* le bookmaker répartit sa marge. Les méthodes
diffèrent uniquement par cette hypothèse.

#### A. Proportionnelle (multiplicative)

```
p_k = (1/o_k) / V
```

*Hypothèse* : la marge est proportionnelle à la probabilité. C'est la
méthode la plus utilisée et **la plus fausse** : elle suppose que le
bookmaker prend la même marge relative sur un favori à 1.20 et sur un outsider
à 15.00, ce qui est empiriquement contredit.

#### B. Additive (marge égale)

```
p_k = (1/o_k) − (V − 1) / n
```

*Hypothèse* : la marge est répartie en parts égales en points de
probabilité. Peut produire des probabilités négatives sur les gros outsiders
(cote > 30). Simple mais fragile.

#### C. Odds-ratio (Cheung)

On cherche `c` tel que :

```
p_k / (1 − p_k)  =  c · [ q_k / (1 − q_k) ]        avec  Σ p_k = 1
```

Résolu par recherche dichotomique sur `c`. *Hypothèse* : la marge est
multiplicative **sur les cotes d'échange** (odds ratio), ce qui correspond
mieux aux pratiques réelles de tarification.

#### D. Shin

C'est la méthode qui a un **modèle économique** derrière elle. Shin (1992)
postule qu'une proportion `z` des paris provient de parieurs informés
(insiders) et que le bookmaker se protège en gonflant ses cotes. On résout
pour `z` :

```
p_k = [ sqrt( z² + 4·(1−z)·q_k²/V ) − z ] / [ 2·(1−z) ]

avec  q_k = 1/o_k,   V = Σ q_j,   et  z  tel que  Σ p_k = 1
```

*Propriété clé* : Shin retire **plus** de marge sur les outsiders que sur les
favoris. Cela corrige partiellement le **favourite–longshot bias** (les gros
outsiders sont systématiquement sur-cotés en probabilité implicite). C'est la
méthode la plus défendable théoriquement.

#### E. Power

```
p_k = q_k^(1/τ)    avec τ tel que  Σ p_k = 1
```

Bon compromis empirique, souvent proche de Shin.

### 1.3 Comparaison sur le cas réel

Cotes 2.10 / 3.50 / 3.60, overround 3.97 % :

| Méthode | p(Dom) | p(Nul) | p(Ext) | Paramètre |
| --- | --- | --- | --- | --- |
| Proportionnelle | 0.4580 | 0.2748 | 0.2672 | — |
| Additive | 0.4630 | 0.2725 | 0.2646 | — |
| Odds-ratio | 0.4609 | 0.2734 | 0.2657 | c = 0.9406 |
| **Shin** | **0.4617** | **0.2731** | **0.2652** | z = 0.0199 |

L'écart entre méthodes est ici de **0.5 point** sur le favori. Ce n'est pas
négligeable : à une cote de 2.10, 0.5 point de probabilité = **1.05 % d'EV**,
soit près de l'ordre de grandeur de l'edge total recherché.

> **Conséquence opérationnelle** : le choix de la méthode de dévigorisation
> n'est pas un détail d'implémentation. Il doit être un paramètre explicite
> du backtest, et les résultats doivent être présentés avec la méthode
> utilisée. Un backtest qui ne précise pas sa méthode de de-vig n'est pas
> interprétable.

**Recommandation** : **Shin** par défaut, avec les cinq méthodes calculées et
stockées dans `market.market_probabilities`. Le backtest teste la sensibilité
des résultats à ce choix ; si la rentabilité disparaît en passant de Shin à
proportionnelle, elle n'existait pas.

### 1.4 Le cas des marchés à deux issues

Pour un Over/Under ou un handicap asiatique, le problème est plus simple
(2 issues, marges plus faibles) mais un piège demeure : le **de-vig sur un
marché à 2 issues avec la méthode proportionnelle est équivalent à supposer
une marge symétrique**, ce qui est généralement faux — le bookmaker déplace
sa marge du côté où il attend du volume.

Exemple : Over 2.5 à 1.92 / Under 2.5 à 1.98, overround 2.59 %.

| Méthode | p(Over) | p(Under) |
| --- | --- | --- |
| Proportionnelle | 0.5079 | 0.4921 |
| Shin | 0.5079 | 0.4921 |

Ici les deux coïncident (à 4 décimales) parce que les cotes sont proches ;
l'écart se creuse sur les lignes déséquilibrées.

### 1.5 Le meilleur estimateur de marché n'est pas une seule cote

```
p_consensus =  Σ_b  ω_b · p_b^(devig)        avec  Σ ω_b = 1
```

Pondération recommandée :

```
ω_b ∝ exp( θ · sharpness_b )  ×  (1 / overround_b)  ×  liquidité_b
```

En pratique : **la cote dévigorisée d'un bookmaker « sharp » à limites
élevées vaut plus que la moyenne de 20 bookmakers grand public**, qui se
copient les uns les autres et donnent une illusion de consensus
indépendant. Mesurer `n_bookmakers` n'a donc de sens que corrigé de cette
corrélation.

---

## 2. Fair odds

```
Fair Odds  =  1 / p_modèle
```

C'est la cote à laquelle un pari serait exactement neutre (EV = 0).

Sur l'exemple :

| Issue | p finale | Fair odds | Cote marché | Verdict |
| --- | --- | --- | --- | --- |
| Domicile | 0.4824 | **2.073** | 2.10 | Cote > fair → value potentielle |
| Nul | 0.2636 | **3.793** | 3.50 | Cote < fair → pas de value |
| Extérieur | 0.2540 | **3.937** | 3.60 | Cote < fair → pas de value |

> Note : la somme des probabilités implicites des fair odds vaut exactement
> 1 — par construction, il n'y a pas de marge. Un « ensemble de fair odds »
> dont la somme des inverses dépasse 1 signale un bug.

---

## 3. Expected Value (EV)

### 3.1 Formule

Pour une mise unitaire sur une cote décimale `o` avec une probabilité
estimée `p` :

```
EV  =  p · (o − 1)  −  (1 − p) · 1   =   p · o  −  1
```

L'EV s'exprime en **fraction de la mise**. `EV = +0.013` signifie +1.3 % de
la mise en espérance par pari, répété à l'infini, **si p est juste**.

### 3.2 Edge

```
Edge  =  p_modèle  −  p_marché(dévigorisée)
```

L'edge est en **points de probabilité**. Attention à ne pas confondre :

| | Edge | EV |
| --- | --- | --- |
| Unité | Points de probabilité | Fraction de la mise |
| Lecture | « Je pense que c'est 2.07 pts plus probable que le marché » | « Je gagne 1.30 % par mise en espérance » |
| Relation | `EV ≈ Edge × o` (approximativement, si la cote est proche de la fair du marché) | |

Sur l'exemple : Edge = 0.4824 − 0.4617 = **+2.07 pts**, EV = 0.4824 × 2.10 −
1 = **+1.30 %**. Vérification : 0.0207 × 2.10 = 0.0435 ≠ 0.0130 — l'écart
vient de la marge du bookmaker, qui absorbe la différence. **C'est pourquoi
il faut toujours regarder l'EV, pas l'edge** : l'edge ignore le coût de
transaction.

### 3.3 Le seuil à franchir

Pour que l'EV soit positif à la cote 2.10, il faut :

```
p > 1 / 2.10 = 0.4762
```

Or le marché dévigorisé dit 0.4617. **Le modèle doit donc être supérieur au
marché d'au moins 1.45 point de probabilité rien que pour atteindre le
seuil de rentabilité.** C'est le mur que la marge bookmaker érige, et c'est la
raison pour laquelle la quasi-totalité des matchs ne présentent aucune value.

---

## 4. Détection de la value : la partie qu'il ne faut pas bâcler

### 4.1 Le critère naïf (à ne pas utiliser seul)

```
si EV > seuil (ex. 3 %)  →  signal
```

Ce critère est faux en pratique pour quatre raisons :

1. Il ignore l'incertitude sur `p`.
2. Il ignore le fait que, sur des milliers de comparaisons, on va trouver des
   EV positifs **par pur hasard** (problème des comparaisons multiples).
3. Il ignore la qualité de la cote : une cote à limite 50 € sur un petit
   bookmaker n'est pas une opportunité, c'est une erreur d'affichage.
4. Il ignore l'antisélection : si vous obtenez une cote nettement meilleure
   que partout ailleurs, la raison la plus probable est que **vous savez
   moins que le bookmaker**, pas l'inverse.

### 4.2 Le critère retenu

Un signal n'est émis que si **toutes** les conditions suivantes sont
remplies :

```
(1)  EV − k·σ_EV  >  seuil_EV                    k = 1,  seuil_EV = 2 %
(2)  data_quality  ≥  0.75
(3)  n_bookmakers  ≥  5
(4)  la cote n'est pas un outlier isolé :
         |log(o_cible) − log(médiane des o)|  <  2.5 × MAD
(5)  max_stake  ≥  mise_recommandée
(6)  le marché n'a pas bougé de plus de 3 % dans les 10 dernières minutes
         (protection contre une cote périmée / une news non intégrée)
(7)  la calibration du modèle sur ce bac de probabilité est validée
         (|p_annoncée − p_observée| < 2 pts sur les 12 derniers mois)
```

La condition (4) est contre-intuitive mais essentielle : **une cote isolée
très supérieure aux autres est presque toujours une erreur ou une information
manquante, pas une opportunité.** On la traite comme suspecte, pas comme un
cadeau.

La condition (7) est la plus importante et la plus souvent oubliée : si le
modèle est mal calibré dans la zone 45-55 %, tout signal dans cette zone est
invalide, quelle que soit la taille de l'EV.

Chaque rejet est **tracé** dans `ml.value_signals.suppression_reason`. Sans
cette trace, impossible de savoir a posteriori si les seuils sont trop
stricts ou trop laxistes.

### 4.3 Correction pour comparaisons multiples

Si l'on évalue 30 matchs × 12 marchés × 3 issues = ~1 000 comparaisons par
jour, un seuil d'EV à 2 % produira des faux positifs en masse. Deux
parades :

- **Réduire l'espace de recherche** : ne tester que les marchés où le modèle
  a démontré une calibration solide (souvent : 1X2 et Over/Under buts, pas
  les scores exacts).
- **Ajuster le seuil par marché** selon le nombre de tests et la variance
  historique du signal sur ce marché — une forme empirique de contrôle du
  taux de fausses découvertes.

---

## 5. Limites des calculs d'EV — à afficher dans le produit

| Limite | Conséquence |
| --- | --- |
| **L'EV suppose que `p` est juste** | C'est l'hypothèse la plus forte et la moins vérifiable. Un EV de +5 % avec un modèle sur-confiant de 3 points est en réalité négatif |
| **L'EV ignore la variance** | Deux paris à +3 % d'EV, l'un à cote 1.50, l'autre à 15.00, n'ont pas le même risque de ruine |
| **L'EV ignore la corrélation** | Trois paris sur le même match ne sont pas indépendants. Leur variance combinée est très supérieure à la somme |
| **L'EV ignore la disponibilité** | La cote affichée n'est pas toujours la cote obtenue (limites, refus, fermeture) |
| **L'EV ignore la contrainte de compte** | Un compte limité ou fermé annule tout edge futur |
| **Le marché bouge** | Une cote de 2.10 à J-3 peut être à 1.95 au coup d'envoi. Le vrai test est le CLV |

**Règle d'affichage** : ne jamais montrer un EV sans montrer, à côté, son
incertitude et la qualité des données. Un `+4.2 % (σ ±3.1 %, données 61 %)`
raconte une histoire complètement différente de `+4.2 %`.

---

## 6. Bankroll et staking

### 6.1 Comparaison des méthodes

| Méthode | Formule | Avantages | Risques | Quand l'utiliser |
| --- | --- | --- | --- | --- |
| **Flat** | mise = constante | Trivial, variance maîtrisée, **ne dépend pas de la qualité de `p`** | Ne capitalise pas ; sous-optimal si l'edge est réel | **Les 500 premiers paris** |
| **Pourcentage fixe** | mise = c × bankroll | Ajustement automatique, ruine impossible (mathématiquement) | Croissance lente, ignore la taille de l'edge | Bon compromis long terme |
| **Kelly complet** | `f = (p·o − 1)/(o − 1)` | Maximise la croissance logarithmique **si `p` est exact** | **Extrêmement sensible à l'erreur sur `p`**. Drawdowns de 50 %+ courants | Jamais en pratique |
| **Kelly fractionnaire** | `f' = φ · f`, φ ∈ [0.1, 0.5] | Réduit la variance quadratiquement, ne perd que linéairement en croissance | Reste dépendant de `p` | **Après validation du CLV** |

### 6.2 Kelly, et pourquoi il faut s'en méfier

```
f* = (p·o − 1) / (o − 1)  =  EV / (o − 1)
```

Sur l'exemple : `f* = 0.0130 / 1.10 = 0.0118`, soit **1.18 % de la bankroll**.

Le problème fondamental : **Kelly suppose `p` connu**. Si l'on surestime `p`
de seulement 2 points (0.4824 → 0.4624), l'EV réel devient `0.4624 × 2.10 −
1 = −2.9 %` et l'on mise 1.18 % de sa bankroll sur un pari perdant. Miser
Kelly avec une probabilité incertaine, c'est **parier sur sa propre
calibration**.

Résultat classique : surestimer son edge d'un facteur 2 et miser Kelly
complet produit une croissance **négative** — pire que de ne pas parier du
tout. C'est pourquoi la littérature et la pratique convergent vers
**Kelly fractionnaire à φ ≤ 0.25**.

| Fraction | Mise sur l'exemple | Croissance relative | Variance relative |
| --- | --- | --- | --- |
| Kelly complet (φ=1) | 1.18 % | 100 % | 100 % |
| Demi-Kelly (φ=0.5) | 0.59 % | 75 % | **25 %** |
| Quart-Kelly (φ=0.25) | **0.30 %** | ~44 % | **6 %** |

Le demi-Kelly conserve 75 % de la croissance pour un quart de la variance.
C'est un arbitrage remarquablement favorable, et c'est la raison de sa
popularité.

### 6.3 Kelly « incertain » (recommandé)

Si l'on dispose de σ_p, on peut corriger directement :

```
f_ajusté  =  φ · ( EV − k·σ_EV ) / (o − 1)
```

Cela réalise automatiquement le comportement souhaité : **plus le modèle est
incertain, plus la mise est petite**, et elle tombe à zéro quand
l'incertitude dépasse l'edge. C'est mathématiquement proche du Kelly
bayésien, et beaucoup plus simple à implémenter et à expliquer.

### 6.4 Garde-fous non négociables

| Garde-fou | Valeur | Raison |
| --- | --- | --- |
| Mise maximale par pari | 2 % de la bankroll | Même si Kelly en suggère plus |
| Exposition maximale par match | 3 % | Les marchés d'un même match sont corrélés |
| Exposition maximale par jour | 10 % | Limite le risque de corrélation de ligue |
| Cote maximale | 10.0 | Au-delà, la calibration n'est jamais fiable |
| Arrêt sur drawdown | −25 % | Déclenche une **revue du modèle**, pas une augmentation des mises |
| Paris corrélés | Traités comme un seul pari | Sinon l'exposition réelle est sous-estimée |

### 6.5 La règle qui prime sur toutes les autres

**Une probabilité élevée n'est jamais une raison de parier.**

Un favori à 92 % de probabilité proposé à 1.05 a une EV de
`0.92 × 1.05 − 1 = −3.4 %`. C'est un mauvais pari, avec une très forte
probabilité de gagner. Inversement, un outsider à 12 % proposé à 9.50 a une
EV de `0.12 × 9.50 − 1 = +14 %`.

Le système ne doit **jamais** classer les opportunités par probabilité. Le
classement est par EV ajusté du risque, et l'interface doit rendre cette
distinction impossible à confondre. C'est une exigence de conception de
l'interface autant qu'une règle de calcul.

---

## 7. Récapitulatif des formules

```
────────────────────────────────────────────────────────────────────────────
 Probabilité implicite brute      q  = 1 / o
 Overround                        V  = Σ q_k
 Marge                            m  = V − 1
 De-vig proportionnel             p  = q / V
 De-vig additif                   p  = q − (V−1)/n
 De-vig odds-ratio                p/(1−p) = c · q/(1−q),  Σp = 1
 De-vig Shin                      p  = [√(z² + 4(1−z)q²/V) − z] / [2(1−z)],  Σp = 1
 De-vig power                     p  = q^(1/τ),  Σp = 1

 Fair odds                        o* = 1 / p_modèle
 Edge                             e  = p_modèle − p_marché
 Expected Value                   EV = p_modèle · o − 1
 Seuil de rentabilité             p_min = 1 / o
 Kelly                            f* = (p·o − 1) / (o − 1) = EV / (o−1)
 Kelly fractionnaire incertain    f  = φ · (EV − k·σ_EV) / (o − 1)
 Closing Line Value               CLV = o_prise / o_clôture − 1
 ROI                              ROI = Σ profit / Σ mises
 Yield                            = ROI (même chose ; le « yield » est le ROI par mise)
────────────────────────────────────────────────────────────────────────────
```
