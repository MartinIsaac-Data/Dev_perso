# 11 — Dashboard, explicabilité, confiance et qualité des données

> Le produit n'est pas « un site qui affiche des pronostics ». C'est un
> instrument de mesure. L'interface doit donc rendre **l'incertitude aussi
> visible que la prédiction** — faute de quoi elle ment par omission.

---

## 1. Architecture frontend

### 1.1 Comparaison des options

| | **React (SPA + Vite)** | **Next.js (App Router)** | **Vue / Nuxt** |
| --- | --- | --- | --- |
| Rendu serveur | Non (sauf ajout) | **Oui, natif** | Oui (Nuxt) |
| SEO | Faible | **Fort** | Fort |
| Écosystème data-viz | Excellent | Excellent | Bon |
| Streaming / Server Components | Non | **Oui** | Partiel |
| Complexité | **Faible** | Moyenne | Faible |
| Recrutement / documentation | Excellent | Excellent | Moyen |
| Coût d'hébergement | Statique (~0) | Node ou edge | Node |
| Pertinence MVP | Bonne | **Meilleure** | Bonne |

**Recommandation : Next.js (App Router) + TypeScript.** Trois raisons
factuelles :

1. **Le rendu serveur résout le problème de fraîcheur.** Une page de match
   rendue côté serveur avec `revalidate: 30` donne des cotes à jour sans
   cascade de requêtes client, et sans écran de chargement.
2. **Le SEO compte** si le produit doit être consulté publiquement : les
   pages de match sont exactement le type de contenu indexable.
3. Le coût de complexité par rapport à une SPA Vite est aujourd'hui faible,
   et la migration inverse (Next → SPA) est plus simple que l'inverse.

Stack complémentaire :

| Besoin | Choix | Pourquoi |
| --- | --- | --- |
| État serveur | **TanStack Query** | Cache, revalidation, invalidation par événement |
| Composants | **shadcn/ui + Tailwind** | Pas de dépendance lourde, contrôle total du rendu |
| Graphiques | **Visx ou Recharts** (SVG) | Contrôle des spécifications de marque (§2), pas de canvas |
| Tables | **TanStack Table** | Le tableau de marchés est la vue la plus dense |
| Temps réel | **EventSource (SSE)** | Voir doc 10 §6 |

---

## 2. Spécification des visualisations

> Règle appliquée systématiquement : **la forme est choisie par le travail
> que le lecteur doit faire**, jamais par habitude. Et parfois la bonne forme
> n'est pas un graphique.

### 2.1 Table de correspondance

| Donnée | Travail du lecteur | Forme retenue | Forme rejetée |
| --- | --- | --- | --- |
| P(H) / P(D) / P(A) | Lire trois valeurs qui somment à 1 | **Barre empilée horizontale 100 %** + 3 valeurs en chiffres | Camembert (3 secteurs illisibles) |
| Modèle **vs** marché, par issue | Comparer deux valeurs par item | **Dumbbell** (deux points reliés par un segment, une ligne par issue) | Barres groupées (double la charge visuelle) |
| Expected goals A vs B | Comparer deux entités sur une même échelle | **Dumbbell** ou barres divergentes autour de 0 | Deux jauges |
| Évolution des cotes | Tendance dans le temps | **Ligne** (1 série par issue, 3 max), axe en probabilité dévigorisée | **Jamais de double axe** cote + probabilité |
| Forme récente (10 matchs) | Signal de tendance compact | **Sparkline** dans une tuile, + pastilles V/N/D | Un histogramme à 10 barres |
| xG cumulé sur la saison | Tendance, deux équipes | **Ligne, 2 séries**, avec légende + étiquettes directes | — |
| Courbe de calibration | Écart à une référence | **Ligne vs diagonale de référence** ; l'écart en **divergent** (gris neutre au centre) | Barres |
| Niveau de confiance | Un ratio unique face à une limite | **Meter** (jauge linéaire sur la même rampe) | Jauge type compteur de voiture, camembert à 2 parts |
| Data Quality | Une note + son détail | **Meter + liste de contrôles** (✓ / ~ / ✗) | Donut |
| Tableau des marchés (Model P, Odds, Fair, Edge, EV) | Lire et comparer 8-15 lignes chiffrées | **Table**, avec une micro-barre divergente dans la colonne EV | Un graphique — au-delà de ~7 classes porteuses de sens, la table gagne |
| Évolution de bankroll (backtest) | Tendance longue, ordres de grandeur | **Ligne en échelle log** | Échelle linéaire (écrase le début) |
| Drawdown | Écart sous une ligne de référence | **Aire sous la ligne 0**, divergent | — |
| Contributions SHAP | Magnitude signée, 6-8 items | **Barres divergentes horizontales** triées par |valeur| | Waterfall (difficile à lire à cette densité) |

### 2.2 Règles non négociables appliquées partout

| Règle | Application dans ce produit |
| --- | --- |
| **Jamais de double axe** | Les cotes et les probabilités ne partagent jamais un graphique. Si les deux sont nécessaires : deux graphiques empilés partageant l'axe des temps |
| **Couleur catégorielle en ordre fixe** | H = teinte 1, D = teinte 2, A = teinte 3, **toujours**, y compris quand une issue est filtrée. La couleur suit l'entité, jamais son rang |
| **Séquentiel = une teinte, clair → foncé** | Heatmap de la grille de scores exacts : une seule teinte |
| **Divergent = deux teintes + gris neutre au centre** | Edge et EV : positif / négatif avec **zéro en gris**, jamais une teinte au point neutre |
| **Palette validée par script, pas à l'œil** | La palette catégorielle passe le validateur (bande de clarté, plancher de chroma, séparation CVD ΔE ≥ 8, contraste) avant tout déploiement |
| **Légende dès 2 séries, étiquettes directes jusqu'à 4** | L'identité ne repose jamais sur la couleur seule |
| **Texte en jetons d'encre, jamais en couleur de série** | Les pourcentages sont en encre primaire ; la pastille colorée à côté porte l'identité |
| **Couleurs de statut réservées** | Vert/ambre/rouge sont réservés à la qualité des données et aux alertes. Ils ne servent **jamais** à colorer une issue de match — sinon « domicile » paraîtrait « bon » |
| **Mode sombre choisi, pas inversé** | Les pas sont re-sélectionnés dans les mêmes rampes et re-validés contre la surface sombre |
| **Couche de survol par défaut** | Réticule + infobulle sur toute ligne/aire ; infobulle par marque sur barres et cellules |

> Le point sur les couleurs de statut mérite d'être souligné : dans un
> produit de paris, colorer la barre « victoire domicile » en vert et
> « défaite » en rouge introduit un jugement de valeur qui n'a aucun sens
> (l'utilisateur peut parier sur n'importe quelle issue) et qui pousse
> inconsciemment vers le favori. Les issues sont **catégorielles**, neutres.

---

## 3. La page de match

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Ligue 1 · J7 · 20 sept. 2026 20:00 (UTC+2) · Stade de la Beaujoire          │
│                                                                              │
│   FC NANTES                    vs                    STADE RENNAIS           │
│   Elo 1720 · 7e                                      Elo 1650 · 11e          │
│                                                                              │
│  ┌── Données ──────────────────────────────────────────────────────────┐    │
│  │  Compo confirmée ✓    Cotes il y a 4 min ✓    Qualité : ▰▰▰▰▰▰▰▰▰▱ 94 % │  │
│  │  Fiabilité du modèle : ▰▰▰▰▰▰▰▱▱▱ 72 %   ⓘ                          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  PROBABILITÉS DU MODÈLE                                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ ███████████████████████ 48.2 % ██████████ 26.4 % ██████████ 25.4 %   │   │
│  │        Nantes                      Nul            Rennes             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  MODÈLE vs MARCHÉ                      BUTS ATTENDUS                        │
│  Nantes  marché ●────────● modèle      Nantes  ●──────────  1.62            │
│          46.2 %        48.2 %          Rennes  ●───────     1.08            │
│  Nul     modèle ●──● marché            Total                2.70            │
│          26.4 %    27.3 %              Score le plus probable : 1-1 (12.4 %) │
│  Rennes  modèle ●──● marché                                                 │
│          25.4 %    26.5 %                                                   │
│                                                                              │
│  MARCHÉS                                                                     │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Marché        Sél.  Model P  Odds   Fair   Edge     EV      Signal   │   │
│  │ ───────────────────────────────────────────────────────────────────  │   │
│  │ 1X2           1     48.24 %  2.10   2.073  +2.07   ▏+1.30 %   —      │   │
│  │ 1X2           X     26.36 %  3.50   3.793  −0.95  ▕−7.73 %    —      │   │
│  │ 1X2           2     25.40 %  3.60   3.937  −1.12  ▕−8.57 %    —      │   │
│  │ O/U 2.5       Over  50.69 %  1.92   1.973  −0.10  ▕−2.67 %    —      │   │
│  │ O/U 2.5       Under 49.31 %  1.98   2.028  +0.10  ▕−2.37 %    —      │   │
│  │ BTTS          Oui   53.56 %  1.85   1.867  +2.24  ▏ −0.91 %   —      │   │
│  │ ───────────────────────────────────────────────────────────────────  │   │
│  │ Aucun signal de value sur ce match.                              ⓘ   │   │
│  │ Le meilleur écart (1X2 · 1, +1.30 % EV) est inférieur à            │   │
│  │ l'incertitude du modèle (±2.5 pts). Voir « pourquoi ».               │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  [ Explication ]  [ Mouvement des cotes ]  [ Effectifs ]  [ Forme ]  [ H2H ] │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Lire la ligne BTTS.** Elle a un edge **positif** (+2.24 pts : le modèle
estime 53.56 % là où le marché dévigorisé donne 51.32 %) et pourtant un EV
**négatif** (−0.91 %). La marge du bookmaker sur ce marché consomme
entièrement l'écart. C'est le cas le plus pédagogique de toute l'interface :
il montre pourquoi le classement se fait par EV et jamais par edge, et
pourquoi les deux colonnes sont affichées côte à côte.

**Le bloc le plus important de cette page est le message « Aucun signal ».**
La majorité des matchs n'offrent aucune value, et l'interface doit présenter
cela comme le **résultat normal et attendu** d'une analyse réussie, pas comme
un échec ou un vide. Une plateforme qui affiche des opportunités sur tous les
matchs est une plateforme qui ment.

---

## 4. Explicabilité

### 4.1 Ce qu'il faut répondre

« Pourquoi le modèle estime 48.2 % ? » se décompose en trois questions
distinctes, et l'interface doit les séparer :

| Question | Réponse |
| --- | --- |
| **Par rapport à quoi ?** | Par rapport à une référence explicite (le taux de base domicile de la ligue : 43.1 %) |
| **Qu'est-ce qui a poussé vers le haut / vers le bas ?** | Les contributions SHAP groupées |
| **Qu'est-ce qui pourrait me faire changer d'avis ?** | L'analyse de sensibilité |

### 4.2 Affichage

```
POURQUOI 48.2 % ?

Référence : victoire à domicile en Ligue 1              43.1 %
────────────────────────────────────────────────────────────────
Ratings d'équipe (Elo +74)               ██████████     +4.8 pt
Avantage du terrain (Beaujoire)          ███████        +3.2 pt
Forme récente xG (+0.41/match)           ████           +2.1 pt
Absence Mostafa (attaquant, PITS −0.09)  ███            −2.0 pt
Signal de marché (le marché est plus bas)███            −2.1 pt
Fatigue (3 jours de repos vs 6)          █              −0.9 pt
H2H (poids 0.4 — faible)                                 0.0 pt
────────────────────────────────────────────────────────────────
Probabilité finale                                      48.2 %

ⓘ Contributions calculées par TreeSHAP sur le modèle ML et par
  décomposition additive sur les modèles statistiques. Elles sont
  additives en log-odds ; leur somme en points de probabilité peut
  différer du total de ±0.3 pt.
```

### 4.3 Méthodes

| Méthode | Usage | Limite à afficher |
| --- | --- | --- |
| **TreeSHAP** | Contributions par prédiction sur LightGBM | Exact pour les arbres ; les features corrélées se partagent le crédit de façon arbitraire |
| **Décomposition additive** | Pour les modèles statistiques (Elo, Dixon-Coles), on décompose λ | Exacte par construction |
| **Importance globale (gain)** | Vue « quelles features comptent en général » | Ne dit rien sur *cette* prédiction |
| **Partial dependence / ICE** | Page d'analyse du modèle, pas la page de match | Trompeur en présence de corrélation forte |
| **Analyse de sensibilité** | « Que faudrait-il pour que ce soit un pari ? » | La plus utile pour l'utilisateur |

### 4.4 L'analyse de sensibilité — la fonctionnalité qui manque partout

```
QUE FAUDRAIT-IL POUR QUE CE SOIT UN PARI ?

Pour un EV > +2 %, il faudrait P(Nantes) > 48.6 %.  Actuellement : 48.24 %.

Scénarios :
  Si Mostafa était disponible (λ 1.62 → 1.71)    →  P = 49.5 %  ·  EV = +3.99 %  ✓
  Si la cote montait à 2.15                      →  P inchangée ·  EV = +3.72 %  ✓
  Si λ_Nantes était 5 % plus bas (1.54)          →  P = 46.9 %  ·  EV = −1.52 %  ✗
  Si λ_Rennes était 10 % plus élevé (1.19)       →  P = 46.6 %  ·  EV = −2.13 %  ✗

Conclusion : la prédiction est à la frontière. L'incertitude du modèle
(±2.5 pts) dépasse l'écart au marché (+2.07 pts). Pas de signal.
```

Cette vue transforme un nombre opaque en objet manipulable, et elle est
honnête : elle montre que la conclusion dépend d'hypothèses fragiles.

---

## 5. Le système de confiance — ce qu'il signifie précisément

### 5.1 Pourquoi « Confiance : 87 % » est une mauvaise réponse

Un pourcentage sans définition invite l'utilisateur à le lire comme une
probabilité — ce qu'il n'est pas. Le système expose donc **deux nombres
distincts**, jamais fusionnés :

| Indicateur | Définition précise | Ce qu'il n'est pas |
| --- | --- | --- |
| **Data Quality** | Part de l'information attendue qui est effectivement disponible et fraîche | Une mesure de la justesse du modèle |
| **Reliability** | Probabilité *a posteriori* que la probabilité annoncée soit exacte à ±3 points, estimée sur l'historique de prédictions comparables | Une probabilité de gagner le pari |

### 5.2 Calcul de la fiabilité (Reliability)

```
Reliability = g( ECE_historique(bac, compétition),
                 σ_p (dispersion bootstrap),
                 désaccord_ensemble,
                 n_matchs_comparables,
                 DataQuality )
```

Concrètement, en cinq composants, chacun dans [0,1] :

| Composant | Mesure | Poids |
| --- | --- | --- |
| **Calibration historique** | `1 − min(ECE_bac / 0.05, 1)` sur ce bac de probabilité et cette compétition | 0.30 |
| **Précision paramétrique** | `1 − min(σ_p / 0.06, 1)` (bootstrap) | 0.25 |
| **Accord de l'ensemble** | `1 − min(écart-type(p_membres) / 0.08, 1)` | 0.20 |
| **Complétude des données** | `DataQuality` | 0.15 |
| **Liquidité du marché** | `min(n_books_effectifs / 8, 1) × (1 − overround/0.10)` | 0.10 |

### 5.3 Comment l'afficher sans créer une fausse certitude

```
Fiabilité : 72 %  ▰▰▰▰▰▰▰▱▱▱

  Ce que cela signifie :
  Sur les 340 prédictions passées dans des conditions comparables
  (Ligue 1, probabilité 45-55 %, compo confirmée), la probabilité
  annoncée s'est écartée de la fréquence observée de moins de
  3 points dans 72 % des cas.

  Ce que cela ne signifie PAS :
  ✗ que Nantes a 72 % de chances de gagner
  ✗ que ce pari a 72 % de chances d'être gagnant
  ✗ une garantie de quoi que ce soit
```

**Le principe** : un indicateur de fiabilité doit être **défini par une
mesure empirique reproductible**, pas par une intuition. S'il ne peut pas
être calculé à partir de l'historique, il ne doit pas être affiché.

Cela implique une conséquence importante : **pendant les premiers mois, la
fiabilité n'est pas calculable** (pas d'historique). L'interface doit alors
afficher « Fiabilité : non établie — moins de 100 prédictions comparables »
plutôt qu'une valeur par défaut. C'est un cas que la plupart des produits
esquivent, et c'est précisément le cas le plus fréquent au lancement.

---

## 6. Data Quality Score dans l'interface

```
QUALITÉ DES DONNÉES                                     94 %  ▰▰▰▰▰▰▰▰▰▱

  ✓  Compositions confirmées          il y a 12 min       1.00
  ✓  Statistiques récentes            8/8 derniers matchs 1.00
  ✓  Cotes à jour                     11 books · 4 min    0.95
  ✓  Blessures et suspensions         il y a 6 h          1.00
  ✓  Historique                       38 matchs           1.00
  ✓  Météo                            prévision à 3 h     1.00
  ~  Convergence des ratings          12 matchs saison    0.78

  ⚠ Sous 75 %, aucun signal de value n'est émis.
```

Chaque ligne est cliquable et mène à la donnée source — la traçabilité fait
partie du produit, pas seulement des logs.

---

## 7. Les autres vues

| Vue | Contenu | Priorité |
| --- | --- | --- |
| **Liste des matchs** | Filtres (sport, compétition, date, qualité min, signal), tri par EV ajusté du risque — **jamais par probabilité** | V1 |
| **Page équipe** | Ratings dans le temps, forme, xG cumulé, effectif, calendrier et fatigue | V1 |
| **Mouvement des cotes** | Ligne par issue en probabilité dévigorisée, marqueurs sur les événements (compo publiée, steam) | V1 |
| **Historique des prédictions** | Comment la probabilité de *ce* match a évolué entre J-7 et le coup d'envoi | V2 |
| **Performance du modèle** | Courbe de calibration, Brier vs marché, CLV, décomposition de Murphy | **V1 — non négociable** |
| **Backtests** | Bankroll (log), drawdown, stratifications, CLV | V2 |
| **Suivi de paris papier** | Journal, ROI, CLV, drawdown | V2 |
| **Santé des données** | Fraîcheur par source, conflits, dérive PSI | V1 (vue admin) |

> La page « Performance du modèle » est en V1 délibérément, avant même les
> backtests. Un produit probabiliste qui ne montre pas sa propre calibration
> demande à l'utilisateur de le croire sur parole. C'est exactement ce que ce
> projet refuse d'être.

---

## 8. Accessibilité et honnêteté

| Exigence | Mise en œuvre |
| --- | --- |
| Identité jamais par la couleur seule | Légende + étiquettes directes + motif en mode contraste forcé |
| Vue tabulaire disponible | Tout graphique a un bouton « voir les données » |
| Contraste | Validé par script sur les deux surfaces (claire et sombre) |
| Mode sombre | Pas choisi par inversion : pas re-sélectionnés dans les mêmes rampes et revalidés |
| **Mention permanente** | En pied de chaque page de prédiction : « Estimations probabilistes produites par un modèle statistique. Elles comportent une incertitude quantifiée et ne constituent ni une prédiction certaine ni un conseil. » |
| **Pas de langage de certitude** | Bannir « va gagner », « pari sûr », « banco ». Le vocabulaire du produit est celui de la probabilité et de l'écart |
