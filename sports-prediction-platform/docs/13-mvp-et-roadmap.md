# 13 — Périmètre MVP et roadmap

---

## 1. Le principe de découpage

Le critère qui décide de ce qui entre en V1 n'est pas « est-ce utile ? »
(tout est utile) mais : **est-ce nécessaire pour savoir si le système a un
edge ?**

Cela conduit à des choix contre-intuitifs :

- La page « performance du modèle » est en **V1** (sans elle, on ne sait rien).
- Le basketball et le tennis sont en **V2** (ils multiplient le travail
  d'ingestion sans rien apprendre de plus sur la question centrale).
- Le placement automatique de paris n'est **jamais** dans la roadmap.

---

## 2. V1 — « Savoir si ça marche »

**Objectif unique** : produire des probabilités calibrées sur un sport et
quelques ligues, les comparer au marché, et disposer d'un backtest
irréprochable permettant de décider go/no-go.

**Périmètre** :

| Domaine | Contenu V1 |
| --- | --- |
| Sports | **Football uniquement** |
| Compétitions | 5 ligues (Ligue 1, Premier League, Liga, Serie A, Bundesliga) |
| Historique | 5 saisons minimum |
| Marchés | **1X2, Over/Under buts, BTTS** |
| Données | Fixtures, résultats, stats de base + xG, cotes (≥ 8 books), blessures, compos |
| Modèles | Elo pondéré marge · Dixon-Coles · LightGBM · modèle marché · stacking · calibration isotonique |
| Features | ~40, celles du top 15 du doc 02 §K + dérivées |
| Backtesting | Moteur complet avec frictions et CLV |
| API | Matchs, prédictions, cotes, marchés, explication, performance du modèle |
| Dashboard | Liste des matchs · page de match · **page performance du modèle** · page équipe |
| Explicabilité | SHAP groupé + analyse de sensibilité |
| Qualité | Data quality score + score de fiabilité (ou « non établie ») |
| Automatisation | Tous les flows du doc 09 §4.2 |
| Alertes | Mouvement de cote, compo publiée, données périmées, dérive de calibration |
| **Paper trading** | **Journal de paris papier avec suivi du CLV — indispensable** |

**Hors V1** : basketball, tennis, handicaps asiatiques, corners, cartons,
player props, comptes utilisateurs, application mobile, backtests
configurables depuis l'interface.

**Critère de succès de la V1** — mesurable, décidé à l'avance :

```
1.  Brier Skill Score vs marché dévigorisé  >  0     sur le holdout
2.  ECE  <  0.03
3.  CLV moyen  >  0  avec  t > 2  sur ≥ 300 paris papier
4.  Zéro test anti-fuite en échec
5.  Couverture des données  >  90 %  sur les 5 ligues
```

Si le critère 1 ou 3 n'est pas atteint : **le projet ne passe pas en V2
sous cette forme.** On revient aux features et aux modèles. C'est une
décision à prendre froidement et écrite à l'avance, avant de s'être attaché
au produit.

---

## 3. V2 — « Étendre et fiabiliser »

**Objectif** : généraliser à d'autres sports et durcir le système.

| Domaine | Ajouts V2 |
| --- | --- |
| Sports | **Basketball** (NBA + EuroLeague), **Tennis** (ATP/WTA) |
| Compétitions | +10 ligues de football (D2, Portugal, Pays-Bas, Belgique, MLS…) |
| Marchés | Handicap asiatique, total asiatique, score exact, marchés de sets/jeux |
| Modèles | Bayésien hiérarchique pour les ratings · calibration multiclasse · `shadow mode` opérationnel |
| Player Impact | PITS complet avec régression ridge et modèle de composition probable |
| Backtesting | Interface de configuration · comparaison de configurations |
| Dashboard | Historique des prédictions · mouvement des cotes enrichi · page backtests |
| API | Authentification, quotas, endpoints de paris |
| Alertes | Push mobile, seuils configurables |
| Qualité | Détection automatique de révisions rétroactives · tableau de bord des conflits |

---

## 4. V3 — « Approfondir »

| Domaine | Ajouts V3 |
| --- | --- |
| Sports | Hockey, baseball, football américain, rugby, volley (via adaptateurs) |
| Marchés | Corners, cartons, player props |
| Modèles | Embeddings d'équipes/joueurs · modèles de séquence · simulation de match |
| Données | Tracking, données d'entraînement si accessibles |
| Fonctionnalités | Portefeuille multi-stratégies · optimisation de bankroll sous contrainte de corrélation · détection d'arbitrage |
| Produit | Comptes utilisateurs, abonnements, application mobile |

> Les player props sont volontairement tardifs : ils nécessitent des données
> de qualité (minutes attendues, rôle offensif) et leur marché est plus
> efficace qu'il n'y paraît sur les grandes ligues.

---

## 5. Roadmap détaillée — 10 phases

### Phase 1 — Architecture et socle

| | |
| --- | --- |
| **Objectif** | Un squelette exécutable, des frontières posées, une CI qui protège |
| **Tâches** | Repo et structure · docker compose (Postgres, Redis) · FastAPI « hello » · CI (ruff, mypy, pytest, import-linter) · ADR initiales · conventions de logs et de configuration |
| **Technologies** | Python 3.12, FastAPI, Docker, GitHub Actions |
| **Livrables** | Repo qui démarre en une commande · CI verte · 8 ADR écrites |
| **Dépendances** | Aucune |
| **Difficulté** | ★★☆☆☆ |
| **Risques** | Sur-ingénierie. *Parade : aucune abstraction sans deux cas d'usage réels* |
| **Durée** | 1 semaine |

### Phase 2 — Base de données

| | |
| --- | --- |
| **Objectif** | Le schéma du doc 04 en place, avec la bitemporalité opérationnelle |
| **Tâches** | Migrations Alembic · partitionnement et job de création de partitions · contraintes `CHECK` · index · **repository point-in-time unique** · tests d'intégration · seeds de référentiel |
| **Technologies** | PostgreSQL 16, SQLAlchemy 2, Alembic |
| **Livrables** | Schéma appliqué et testé · `PointInTimeRepository` avec sa suite de tests |
| **Dépendances** | Phase 1 |
| **Difficulté** | ★★★☆☆ |
| **Risques** | **Bitemporalité mal comprise → tout le reste est contaminé.** *Parade : cette phase est la plus revue du projet ; les tests point-in-time sont écrits avant le code* |
| **Durée** | 2 semaines |

### Phase 3 — Ingestion de données

| | |
| --- | --- |
| **Objectif** | 5 saisons × 5 ligues en base, avec cotes, et un flux quotidien qui tourne |
| **Tâches** | Connecteurs (fixtures, résultats, stats, cotes, blessures, compos, météo) · résolution d'entités · réconciliation de conflits · contrôles qualité · flows Prefect · backfill historique |
| **Technologies** | httpx, Prefect, tenacity, Polars |
| **Livrables** | ~9 000 matchs · ~8 M snapshots de cotes · tableau de couverture · flows planifiés |
| **Dépendances** | Phase 2 |
| **Difficulté** | ★★★★☆ |
| **Risques** | **Le plus gros risque du projet.** Matching d'entités défaillant · historique de cotes introuvable ou cher · providers qui changent leur format. *Parades : matching en 3 passes avec revue manuelle · acheter l'historique de cotes AVANT de commencer · tests de contrat par provider* |
| **Durée** | **4 à 6 semaines** |

### Phase 4 — Feature engineering

| | |
| --- | --- |
| **Objectif** | Un feature store point-in-time, testé contre la fuite |
| **Tâches** | Registre YAML · moteur de calcul · features noyau et football · ratings Elo · forme pondérée · fatigue · enjeu Monte-Carlo · H2H résiduel · features marché · **tests anti-fuite** |
| **Technologies** | Polars, scipy |
| **Livrables** | ~45 features déclarées et calculées · suite de tests anti-fuite verte · `feature_hash` stable |
| **Dépendances** | Phase 3 |
| **Difficulté** | ★★★★☆ |
| **Risques** | Fuite subtile via les ratings ré-estimés · explosion combinatoire des features. *Parades : `computed_at ≤ as_of_ts` imposé par le repository · budget de 50 features maximum* |
| **Durée** | 3 semaines |

### Phase 5 — Modèle statistique

| | |
| --- | --- |
| **Objectif** | Dixon-Coles opérationnel, meilleur qu'un modèle naïf |
| **Tâches** | MLE Poisson pondéré récence · correction Dixon-Coles · estimation de ρ · grille de scores · dérivation de tous les marchés · avantage domicile par compétition · gestion intersaison et promus |
| **Technologies** | scipy.optimize, numpy |
| **Livrables** | Modèle entraîné · log-loss et Brier vs marché · courbe de calibration |
| **Dépendances** | Phase 4 |
| **Difficulté** | ★★★☆☆ |
| **Risques** | Convergence instable du MLE · ρ mal identifié. *Parades : contraintes d'identifiabilité explicites · bornes sur ρ · valeurs de départ issues des ratings* |
| **Durée** | 2 semaines |

### Phase 6 — Modèle ML et ensemble

| | |
| --- | --- |
| **Objectif** | Un ensemble calibré qui bat (ou pas) le marché — et on le saura |
| **Tâches** | LightGBM multiclasse · contraintes de monotonie · Optuna en validation temporelle · modèle marché (de-vig) · stacking out-of-fold · calibration isotonique · SHAP · analyse d'ablation · registre MLflow |
| **Technologies** | LightGBM, scikit-learn, Optuna, SHAP, MLflow |
| **Livrables** | Modèle champion versionné · rapport d'ablation · matrice de corrélation des membres · calibration |
| **Dépendances** | Phase 5 |
| **Difficulté** | ★★★★☆ |
| **Risques** | **Surapprentissage** (le plus probable) · double comptage du marché · sur-optimisation par itérations répétées. *Parades : num_leaves faible et min_data_in_leaf élevé · budget d'essais compté · holdout scellé* |
| **Durée** | 4 semaines |

### Phase 7 — Backtesting

| | |
| --- | --- |
| **Objectif** | Un verdict chiffré et défendable |
| **Tâches** | Horloge virtuelle · univers historique · frictions · staking · métriques (ROI, CLV, drawdown, Murphy) · stratifications · tests de robustesse · rapport HTML |
| **Technologies** | Polars, DuckDB, Jinja2 |
| **Livrables** | Rapport complet sur le holdout · tests de permutation · sensibilité au de-vig |
| **Dépendances** | Phase 6 |
| **Difficulté** | ★★★★★ |
| **Risques** | **Se mentir à soi-même.** *Parades : comptage des essais · holdout à usage unique · scénario pessimiste comme seul résultat communiqué* |
| **Durée** | 3 semaines |

### Phase 8 — API

| | |
| --- | --- |
| **Objectif** | Exposer proprement, avec la fraîcheur et l'incertitude |
| **Tâches** | Endpoints du doc 10 · schémas Pydantic · pagination curseur · cache Redis · SSE · erreurs RFC 7807 · OpenAPI · tests de contrat |
| **Technologies** | FastAPI, Redis, schemathesis |
| **Livrables** | API documentée · < 200 ms au p95 sur les endpoints de liste |
| **Dépendances** | Phase 7 |
| **Difficulté** | ★★☆☆☆ |
| **Risques** | Requêtes N+1 sur la vue de match · invalidation de cache manquée. *Parades : chargement par lots · invalidation par événement* |
| **Durée** | 2 semaines |

### Phase 9 — Frontend

| | |
| --- | --- |
| **Objectif** | Rendre l'incertitude aussi lisible que la prédiction |
| **Tâches** | Next.js · liste des matchs · page de match · page performance du modèle · page équipe · graphiques selon le doc 11 §2 · validation de palette · mode sombre · SSE |
| **Technologies** | Next.js 15, TypeScript, Tailwind, Visx, TanStack Query |
| **Livrables** | Dashboard responsive · palette validée · vues tabulaires partout |
| **Dépendances** | Phase 8 |
| **Difficulté** | ★★★☆☆ |
| **Risques** | **Créer une fausse impression de certitude** (risque produit majeur). *Parades : revue explicite du vocabulaire · l'incertitude est affichée à côté de chaque probabilité* |
| **Durée** | 3 semaines |

### Phase 10 — Production et validation prospective

| | |
| --- | --- |
| **Objectif** | Tourner en continu, et prouver en aveugle |
| **Tâches** | Déploiement PaaS · sauvegardes et test de restauration · monitoring · alertes · runbooks · **3 à 6 mois de paper trading** · revue mensuelle de calibration |
| **Technologies** | Docker, GitHub Actions, Sentry, Prometheus |
| **Livrables** | Système en production · rapport de paper trading avec CLV · décision go/no-go documentée |
| **Dépendances** | Phase 9 |
| **Difficulté** | ★★★☆☆ |
| **Risques** | Dérive silencieuse · impatience (conclure trop tôt). *Parades : alerte de calibration qui suspend les signaux · nombre minimal de paris fixé à l'avance* |
| **Durée** | 2 semaines + **3 à 6 mois d'observation** |

---

## 6. Vue d'ensemble du calendrier

```
Sem.  1   3   5   7   9  11  13  15  17  19  21  23  25  27
      │   │   │   │   │   │   │   │   │   │   │   │   │   │
P1 ██
P2    ████
P3        ████████████        ← la phase la plus longue et la plus risquée
P4                    ██████
P5                          ████
P6                              ████████
P7                                      ██████
P8                                            ████
P9                                                ██████
P10                                                     ████ + 3-6 mois
      │   │   │   │   │   │   │   │   │   │   │   │   │   │
      └── ~26 semaines jusqu'à la mise en production ──────┘
      └── +3 à 6 mois de paper trading avant toute conclusion ──┘
```

**Environ 6 mois de développement, puis 3 à 6 mois d'observation.** Toute
estimation plus courte suppose que la phase 3 se passe bien — ce qui n'arrive
jamais.

---

## 7. Les cinq décisions à prendre avant de commencer

| Décision | Pourquoi maintenant |
| --- | --- |
| **Fournisseur d'historique de cotes** | Sans historique de cotes, **aucun backtest n'est possible**. C'est le prérequis absolu et c'est souvent payant |
| **Périmètre de ligues** | Détermine le coût des données et la taille de l'échantillon |
| **Budget mensuel de données** | Arbitre entre xG (cher) et stats de base (bon marché) |
| **Critères de succès chiffrés** | Doivent être écrits **avant** de voir le premier résultat |
| **Qui regarde le holdout, et quand** | Une seule personne, une seule fois |

> La première décision est éliminatoire. Un projet qui démarre le
> développement avant d'avoir sécurisé l'historique de cotes construit
> pendant trois mois un système qu'il ne pourra pas valider.
