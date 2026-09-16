# Sports Prediction Platform — Dossier de conception

Plateforme probabiliste d'analyse de matchs sportifs : elle estime des
probabilités à partir de données, les compare aux probabilités implicites du
marché, et expose l'écart — avec l'incertitude qui va avec.

Ce dossier est une **conception**, pas une implémentation. L'objectif de cette
phase est que chaque décision technique et quantitative soit écrite,
justifiée et contestable avant qu'une ligne de code de production soit
écrite.

---

## Ce que le système est, et ce qu'il n'est pas

| Le système **est** | Le système **n'est pas** |
| --- | --- |
| Un estimateur de probabilités calibré et mesurable | Un générateur de pronostics « sûrs » |
| Un comparateur modèle / marché | Un oracle qui bat le marché par construction |
| Un moteur de backtesting sans look-ahead | Un backtest optimisé jusqu'à ce que la courbe monte |
| Un système transparent (chaque probabilité est explicable) | Une boîte noire avec un « score de confiance 87 % » |
| Une aide à la décision | Une promesse de gain |

**Le postulat central, à ne jamais perdre de vue** : le marché des paris
sportifs sur les ligues majeures est l'un des marchés prédictifs les plus
efficaces qui existent. La cote de clôture d'un bookmaker liquide est, en
moyenne, un meilleur estimateur que la quasi-totalité des modèles publics.
Un modèle qui trouve 15 % de value sur 40 % des matchs n'a pas trouvé un
marché inefficace : il a un bug, une fuite de données, ou un mauvais
étalonnage. Le système est donc conçu pour que **l'hypothèse par défaut soit
« pas de value »**, et pour que la charge de la preuve pèse sur le modèle.

---

## Les six principes de conception

1. **Probabilités avant prédictions.** La sortie du système est une
   distribution, jamais un « vainqueur ». La métrique reine est le Brier
   score et la calibration, pas l'accuracy.
2. **Point-in-time par construction.** Toute donnée est horodatée à son
   instant de *disponibilité*, pas à son instant de *validité*. Le feature
   store ne sait répondre qu'à la question « que savait-on à l'instant T ? ».
   C'est une contrainte d'architecture, pas une discipline d'analyste.
3. **Le marché est une source, pas une cible.** On n'entraîne pas le modèle à
   reproduire les cotes (ce serait un compresseur de marché). On utilise le
   marché comme un modèle concurrent dans l'ensemble, avec un poids mesuré.
4. **Tout écart doit survivre au coût de transaction.** Un edge de 1 % est du
   bruit devant une marge bookmaker de 4 %. Le seuil d'action est défini
   *après* mesure de la variance du modèle, pas avant.
5. **L'incertitude est un livrable.** Chaque probabilité est accompagnée d'un
   intervalle, d'un score de complétude des données et d'un motif
   d'abstention le cas échéant.
6. **Générique d'abord, spécifique ensuite.** Le noyau (équipes, matchs,
   cotes, marchés, ratings, calibration, backtest) est agnostique au sport.
   Les statistiques avancées et les modèles de score sont des plugins par
   sport.

---

## Architecture globale (vue à 10 000 pieds)

```
  SOURCES                INGESTION            STOCKAGE              CALCUL              DIFFUSION
┌────────────┐      ┌────────────────┐   ┌──────────────┐   ┌────────────────┐   ┌──────────────┐
│ API stats  │      │  Connecteurs   │   │  raw.*       │   │ Feature        │   │  API REST    │
│ API cotes  │─────▶│  (1 par        │──▶│  (payload    │──▶│ engineering    │──▶│  FastAPI     │
│ API météo  │      │   provider)    │   │   JSONB brut │   │ (point-in-time)│   │              │
│ Compos     │      │                │   │   immuable)  │   └───────┬────────┘   │  ▲           │
│ Blessures  │      │  Validation    │   └──────┬───────┘           │            │  │           │
└────────────┘      │  + résolution  │          │                   ▼            │  │           │
                    │  de conflits   │          ▼           ┌────────────────┐   │  │           │
                    └────────────────┘   ┌──────────────┐   │ feature_store  │   │  │           │
                                         │  core.*      │   │ (versionné,    │   │  │           │
                                         │  (modèle     │──▶│  as_of_ts)     │   │  │           │
                                         │   canonique) │   └───────┬────────┘   │  │           │
                                         └──────────────┘           │            │  │           │
                                                                    ▼            │  │           │
                                            ┌───────────────────────────────┐    │  │           │
                                            │  ENSEMBLE                     │    │  │           │
                                            │  ┌─────────────────────────┐  │    │  │           │
                                            │  │ Modèle statistique      │  │    │  │           │
                                            │  │ (Dixon-Coles / Poisson) │  │    │  │           │
                                            │  ├─────────────────────────┤  │    │  │           │
                                            │  │ Modèle ML (LightGBM)    │  │    │  │           │
                                            │  ├─────────────────────────┤  │    │  │           │
                                            │  │ Ratings (Elo bayésien)  │  │    │  │           │
                                            │  ├─────────────────────────┤  │───▶│  │  Next.js  │
                                            │  │ Modèle marché (de-vig)  │  │    │  │  Dashboard│
                                            │  └───────────┬─────────────┘  │    │  │           │
                                            │              ▼                │    │  │           │
                                            │       Stacking (logit)        │    │  │           │
                                            │              ▼                │    │  │           │
                                            │    Calibration isotonique     │    │  │           │
                                            │              ▼                │    │  │           │
                                            │    Probabilité finale         │    │  │           │
                                            └──────────────┬────────────────┘    │  │           │
                                                           ▼                     │  │           │
                                                  ┌──────────────────┐           │  │           │
                                                  │  predictions     │───────────┘  │           │
                                                  │  value_signals   │              │           │
                                                  │  backtests       │──────────────┘           │
                                                  └──────────────────┘                          │
                                                                                   └──────────────┘
                     ▲                                                                    │
                     │                        ORCHESTRATION (Prefect / Dagster)            │
                     └────────────────────────────────────────────────────────────────────┘
                              MONITORING : fraîcheur, dérive, calibration, CLV
```

---

## Plan du dossier

| # | Document | Répond aux questions |
| --- | --- | --- |
| 01 | [Architecture conceptuelle](docs/01-architecture-conceptuelle.md) | Couches, frontières, généricité multi-sport, options A/B/C |
| 02 | [Catalogue des paramètres](docs/02-catalogue-parametres.md) | Toutes les variables, hiérarchisées par impact réel |
| 03 | [Feature dictionary](docs/03-feature-dictionary.md) | Chaque feature : formule, type, fenêtre, classe de fuite |
| 04 | [Schéma de base de données](docs/04-database-schema.md) | Tables, PK/FK, index, partitionnement, bitemporalité |
| 05 | [Ratings et modèles](docs/05-ratings-et-modeles.md) | Elo/Glicko/SPI/Poisson/DC/ML, comparaison argumentée |
| 06 | [Probabilités et value](docs/06-probabilites-et-value.md) | De-vig, fair odds, EV, edge, Kelly, limites |
| 07 | [Backtesting et validation](docs/07-backtesting-et-validation.md) | Moteur, métriques, anti-leakage, protocole |
| 08 | [Marché et cotes](docs/08-marche-et-cotes.md) | Modèle de données odds, mouvements, CLV, steam |
| 09 | [Pipeline et automatisation](docs/09-pipeline-et-automatisation.md) | Ingestion, qualité, scheduling, alertes |
| 10 | [API design](docs/10-api-design.md) | Endpoints REST, contrats, pagination, erreurs |
| 11 | [Frontend et explicabilité](docs/11-frontend-et-explicabilite.md) | Dashboard, SHAP, confiance, data quality score |
| 12 | [Stack technique](docs/12-stack-technique.md) | Front/back/DB/ML/infra, comparatif et recommandation |
| 13 | [MVP et roadmap](docs/13-mvp-et-roadmap.md) | V1/V2/V3, 10 phases détaillées |
| 14 | [Structure du projet](docs/14-structure-du-projet.md) | Arborescence, conventions, CI |
| 15 | [Exemple bout-en-bout](docs/15-exemple-bout-en-bout.md) | Un match, du scraping à l'EV, chiffres réels |
| 16 | [Providers de données](docs/16-providers-de-donnees.md) | Fournisseurs stats/cotes, coûts, pièges |
| 17 | [Risques et plan de validation](docs/17-risques-et-plan-de-validation.md) | Risques techniques, statistiques, go/no-go |

Le DDL exécutable complet est dans [`sql/schema.sql`](sql/schema.sql).

---

## Le résultat qu'il faut avoir en tête avant de commencer

Extrait de l'[exemple bout-en-bout](docs/15-exemple-bout-en-bout.md), sur un
match où le modèle est *plutôt* confiant :

```
Modèle Dixon-Coles        : λ_dom = 1.62   λ_ext = 1.08   ρ = −0.05
  M1 statistique  49.34 %   M2 ML  48.79 %
  M3 rating       50.20 %   M4 marché (Shin, 11 books)  46.17 %
Stacking en log-odds (0.40 / 0.15 / 0.10 / 0.35) → 48.24 %
Cote disponible           : 2.10
Fair odds                 : 2.073
Edge                      : +2.07 pts
EV                        : +1.30 %
Kelly complet / quart     : 1.19 % / 0.30 % de bankroll
Décision                  : AUCUN SIGNAL
```

Et la table de sensibilité, qui est le vrai enseignement :

| λ_dom | λ_ext | P(dom) finale | EV @ 2.10 |
| --- | --- | --- | --- |
| 1.539 (−5 %) | 1.080 | 46.89 % | **−1.52 %** |
| 1.620 | 1.080 | 48.23 % | **+1.30 %** |
| 1.701 (+5 %) | 1.080 | 49.52 % | **+3.99 %** |

Une erreur de 5 % sur un seul paramètre de nuisance — parfaitement banale —
fait passer le pari de perdant à gagnant. **L'edge mesuré (+1.3 %) est plus
petit que l'incertitude du modèle sur lui-même.** Toute l'ingénierie décrite
dans ce dossier existe pour réduire cette incertitude et pour savoir quand
s'abstenir, pas pour produire plus de signaux.


---

## Où trouver chaque livrable demandé

| # | Livrable | Emplacement |
| --- | --- | --- |
| 1 | Architecture globale | [01](docs/01-architecture-conceptuelle.md) · schéma ci-dessus |
| 2 | Liste complète des paramètres | [02](docs/02-catalogue-parametres.md) |
| 3 | Feature dictionary | [03](docs/03-feature-dictionary.md) |
| 4 | Database schema | [04](docs/04-database-schema.md) + [`sql/schema.sql`](sql/schema.sql) |
| 5 | ML architecture | [05](docs/05-ratings-et-modeles.md) |
| 6 | Formules mathématiques | [06](docs/06-probabilites-et-value.md) §7 · [05](docs/05-ratings-et-modeles.md) |
| 7 | Backtesting architecture | [07](docs/07-backtesting-et-validation.md) |
| 8 | API architecture | [10](docs/10-api-design.md) |
| 9 | Frontend architecture | [11](docs/11-frontend-et-explicabilite.md) |
| 10 | MVP scope | [13](docs/13-mvp-et-roadmap.md) §2-4 |
| 11 | Roadmap | [13](docs/13-mvp-et-roadmap.md) §5-6 |
| 12 | Structure GitHub du projet | [14](docs/14-structure-du-projet.md) |
| 13 | Exemple d'un match traité de bout en bout | [15](docs/15-exemple-bout-en-bout.md) |
| 14 | Model Probability → Fair Odds → EV | [15](docs/15-exemple-bout-en-bout.md) §5 |
| 15 | API / data providers potentiels | [16](docs/16-providers-de-donnees.md) |
| 16 | Risques techniques | [17](docs/17-risques-et-plan-de-validation.md) §1 |
| 17 | Risques statistiques | [17](docs/17-risques-et-plan-de-validation.md) §2 |
| 18 | Plan de validation avant production | [17](docs/17-risques-et-plan-de-validation.md) §4-5 |

### Correspondance avec les thèmes du cahier des charges

| Thème | Document |
| --- | --- |
| Paramètres match, forme, performance avancée | [02](docs/02-catalogue-parametres.md) §A-C |
| Joueurs, effectifs, **Player Impact on Team Strength** | [02](docs/02-catalogue-parametres.md) §D |
| Tactique → features quantitatives | [02](docs/02-catalogue-parametres.md) §E |
| Calendrier, **Fatigue Score** et ses limites | [02](docs/02-catalogue-parametres.md) §F |
| Contexte et enjeu sans « motivation 8/10 » | [02](docs/02-catalogue-parametres.md) §G |
| Facteurs environnementaux | [02](docs/02-catalogue-parametres.md) §H |
| Arbitres et marchés concernés | [02](docs/02-catalogue-parametres.md) §I |
| H2H pondéré, et quand ne pas l'utiliser | [02](docs/02-catalogue-parametres.md) §J |
| Ratings : Elo, Glicko, SPI, Poisson, bayésien | [05](docs/05-ratings-et-modeles.md) §1-4 |
| Comparaison ML et recommandation V1 | [05](docs/05-ratings-et-modeles.md) §5 |
| Ensemble model, sans double comptage | [05](docs/05-ratings-et-modeles.md) §6 |
| Calibration et métriques pertinentes | [05](docs/05-ratings-et-modeles.md) §7-8 |
| Bookmakers, marchés, mouvements de cotes | [08](docs/08-marche-et-cotes.md) |
| Probabilités implicites, fair odds, EV, edge | [06](docs/06-probabilites-et-value.md) §1-3 |
| Détection de value et ses limites | [06](docs/06-probabilites-et-value.md) §4-5 |
| Bankroll et staking | [06](docs/06-probabilites-et-value.md) §6 |
| Data pipeline, données manquantes, conflits | [09](docs/09-pipeline-et-automatisation.md) §1-3 |
| Automatisation et scheduling | [09](docs/09-pipeline-et-automatisation.md) §4 |
| Alertes | [09](docs/09-pipeline-et-automatisation.md) §5 |
| Dashboard | [11](docs/11-frontend-et-explicabilite.md) §2-3 |
| Explicabilité (SHAP, sensibilité) | [11](docs/11-frontend-et-explicabilite.md) §4 |
| Système de confiance | [11](docs/11-frontend-et-explicabilite.md) §5 |
| Data Quality Score | [11](docs/11-frontend-et-explicabilite.md) §6 · [09](docs/09-pipeline-et-automatisation.md) §3.3 |
| Stack technique et comparatifs | [12](docs/12-stack-technique.md) |
| Extensibilité multi-sport | [01](docs/01-architecture-conceptuelle.md) §2 |

---

## Avertissement

Aucun modèle ne prédit un résultat sportif avec certitude. Les probabilités
produites ici sont des estimations conditionnées à un jeu d'hypothèses, à des
données partielles et à un historique fini. Un backtest positif n'est pas une
garantie de performance future : il est une condition nécessaire, jamais
suffisante. Ce système est un instrument de mesure, et la première chose
qu'il doit mesurer honnêtement, c'est sa propre faillibilité.
