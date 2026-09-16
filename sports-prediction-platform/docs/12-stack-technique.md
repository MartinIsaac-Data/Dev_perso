# 12 — Stack technique et infrastructure

> Critère de décision unique : **minimiser le temps jusqu'au premier match
> correctement prédit et backtesté**, sans créer de dette qui empêcherait de
> passer à 10 ligues et 3 sports. Tout choix qui optimise pour une échelle
> qu'on n'atteindra pas avant deux ans est un mauvais choix.

---

## 1. Backend

| | **Python + FastAPI** | **Python + Django** | **Node.js + NestJS** | **Go** |
| --- | --- | --- | --- | --- |
| Proximité avec le ML | **Native** (même langage, mêmes objets) | Native | **Aucune** (passerelle nécessaire) | Aucune |
| Performance | Bonne (async) | Moyenne | Bonne | **Excellente** |
| Typage / validation | **Pydantic, excellent** | Sérialiseurs DRF | TypeScript + class-validator | Statique |
| Écosystème data | **Le meilleur** | Bon | Faible | Faible |
| ORM / migrations | SQLAlchemy + Alembic | **ORM intégré, admin** | Prisma / TypeORM | sqlc |
| Documentation API | **OpenAPI automatique** | Via extension | Automatique | Manuel |
| Vitesse de développement | Élevée | **Très élevée** (admin gratuit) | Moyenne | Faible |
| Pertinence MVP | **Oui** | Sérieuse alternative | Non | Non |

**Recommandation : Python + FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2.**

Le raisonnement décisif : **le cœur de ce produit est le code quantitatif**.
Les features, les modèles, le backtest et la valorisation sont en Python —
c'est le seul écosystème où scikit-learn, LightGBM, statsmodels, PyMC,
pandas/polars et SHAP coexistent. Choisir Node pour l'API imposerait une
frontière de sérialisation entre l'API et le moteur de calcul, avec deux
implémentations possibles de la même logique de dénouement de paris. C'est
exactement le type de duplication qui produit un skew invisible.

Django a été sérieusement considéré pour son admin gratuit (très utile pour
la revue manuelle des conflits de sources et du matching d'entités). La
décision retenue : **FastAPI + une petite interface d'admin construite dans
le dashboard Next.js**. Si le besoin d'admin explose, `sqladmin` s'ajoute à
FastAPI sans changer de framework.

---

## 2. Base de données

| | **PostgreSQL** | **PostgreSQL + TimescaleDB** | **ClickHouse** | **DuckDB (analytique)** |
| --- | --- | --- | --- | --- |
| Transactionnel | **Oui** | Oui | Non | Non |
| Séries temporelles | Partitions natives | **Excellent** (compression, agrégats continus) | **Excellent** | Bon |
| Analytique lourde | Moyenne | Bonne | **Excellente** | **Excellente** |
| JSONB | **Excellent** | Excellent | Limité | Bon |
| Contraintes d'intégrité | **Fortes** | Fortes | **Faibles** | Faibles |
| Hébergement managé | Partout | Restreint | Restreint | N/A (embarqué) |
| Pertinence MVP | **Oui** | V2 | Non | **Oui, en complément** |

**Recommandation** :

- **PostgreSQL 16** comme base unique de vérité (voir doc 04).
- **Redis** pour le cache d'API, les verrous distribués et les files légères.
- **DuckDB** en complément local pour l'analytique lourde : les backtests
  lisent des exports Parquet depuis l'object storage plutôt que de marteler
  la base de production. C'est gratuit, sans serveur, et **cela résout le
  vrai problème** (un backtest sur 3 saisons ne doit pas bloquer l'API).
- **TimescaleDB** en option activable quand `market.odds_snapshots` dépassera
  ~100 M de lignes. La migration se fait sur une table déjà partitionnée :
  coût faible, donc report justifié.

ClickHouse est écarté : ses contraintes d'intégrité faibles sont
rédhibitoires ici. Le risque principal du projet est la qualité des données,
et PostgreSQL est un allié actif sur ce terrain (voir les `CHECK` du doc 04).

---

## 3. Machine learning

| Besoin | Choix | Justification |
| --- | --- | --- |
| Manipulation de données | **Polars** (+ pandas là où nécessaire) | 5-10× plus rapide, API d'expressions lisible, gère bien les fenêtres temporelles |
| Modèles linéaires, calibration | **scikit-learn** | `IsotonicRegression`, `LogisticRegression`, pipelines |
| Gradient boosting | **LightGBM** | Voir doc 05 §5.3 |
| Modèles statistiques | **statsmodels** + code maison | Poisson/Dixon-Coles s'écrivent en ~150 lignes avec `scipy.optimize` |
| Bayésien (V2) | **PyMC** ou **NumPyro** | Hiérarchique, shrinkage inter-ligues |
| Explicabilité | **SHAP** (TreeSHAP) | Exact sur les arbres |
| Suivi d'expériences | **MLflow** (auto-hébergé) | Modèles, métriques, artefacts, registre de versions |
| Optimisation d'hyperparamètres | **Optuna** | Avec validation temporelle, jamais k-fold aléatoire |
| Sérialisation | **joblib** + hash SHA-256 | Artefact reproductible |

**PyTorch est exclu de la V1** pour les raisons du doc 05 §5.1. Il reste
pertinent en V3 pour une seule chose : des embeddings d'équipes/joueurs
appris, si le volume de données le permet un jour.

---

## 4. Orchestration

Voir doc 09 §4 pour le comparatif détaillé. **Prefect 3**, avec les flows
écrits en Python ordinaire et déployés dans le même conteneur que le worker.

---

## 5. Infrastructure

### 5.1 Trois scénarios de déploiement

| | **A — VPS unique** | **B — PaaS managé** | **C — Kubernetes cloud** |
| --- | --- | --- | --- |
| Composition | 1 VPS, docker compose | Render/Railway/Fly : services managés + Postgres managé | EKS/GKE + RDS + S3 |
| Coût mensuel | **15-40 €** | 60-150 € | 300-800 € |
| Temps de mise en place | 1 jour | **2 heures** | 1-2 semaines |
| Sauvegardes | À gérer soi-même | **Incluses** | Incluses |
| Montée en charge | Verticale uniquement | Horizontale simple | **Illimitée** |
| Charge d'exploitation | Moyenne | **Faible** | Élevée |
| Pertinence MVP | Bonne | **Meilleure** | Non |

**Recommandation : Option B pour démarrer** (PaaS managé, Postgres managé
avec sauvegardes automatiques et *point-in-time recovery*), avec une **option
A documentée** comme repli si le coût devient un sujet.

Le point décisif est la sauvegarde. Reconstituer 3 ans d'historique de cotes
après une perte de données est **impossible** : les cotes passées ne sont pas
re-téléchargeables. La base est donc un actif irremplaçable, et payer 30 €/mois
de plus pour un PITR managé est la meilleure dépense du projet.

### 5.2 Composants

| Composant | Choix | Note |
| --- | --- | --- |
| Conteneurisation | **Docker** + docker compose en local | Un Dockerfile multi-étapes, image unique pour API et workers |
| CI/CD | **GitHub Actions** | Lint, types, tests, migrations en dry-run, build, déploiement |
| Object storage | **S3 compatible** (R2, B2, S3) | Modèles, exports Parquet, rapports de backtest, partitions archivées |
| Cache / files | **Redis** | Cache API, verrous, rate limiting |
| Secrets | Variables d'environnement du PaaS + `.env` local | Jamais de secret en base ni en dépôt |
| Monitoring applicatif | **Sentry** | Erreurs |
| Métriques | **Prometheus + Grafana** (ou le monitoring du PaaS) | Fraîcheur, latence, taux d'erreur d'ingestion |
| Logs | **structlog** en JSON → collecteur du PaaS | Corrélation par `run_id` |
| Monitoring ML | **Tables `ml.calibration_snapshots` + page dédiée** | Voir doc 11 §7 |

### 5.3 Ce qu'il faut monitorer (au-delà de l'infra)

Les métriques d'infrastructure (CPU, latence) ne disent rien de la santé de
ce système. Les vraies alertes sont :

| Métrique | Seuil | Gravité |
| --- | --- | --- |
| Fraîcheur des cotes | > 10 min sur un match à < 3 h | critique |
| Taux d'échec d'ingestion | > 5 % sur 1 h | erreur |
| ECE sur 30 j glissants | > 0.04 | **critique — suspend les signaux** |
| PSI d'une feature surveillée | > 0.25 | avertissement |
| Couverture des compos à T-45 min | < 80 % | avertissement |
| Conflits de sources non résolus | > 20 | avertissement |
| Écart `feature_hash` en recalcul | > 0 | erreur (révision rétroactive) |

---

## 6. Environnements

| Environnement | Base | Données | Usage |
| --- | --- | --- | --- |
| **local** | Postgres en conteneur | Échantillon anonymisé (2 ligues, 1 saison) | Développement |
| **ci** | Postgres éphémère | Fixtures déterministes | Tests |
| **staging** | Postgres managé (petit) | Copie de production à J-1 | Validation de migrations, mode `shadow` |
| **production** | Postgres managé + PITR | Complet | — |

Règle : **les migrations sont toujours appliquées d'abord en staging, sur une
copie récente de la production.** Une migration sur une table de 240 M de
lignes qui prend 40 minutes ne doit pas être découverte en production.

---

## 7. Tests

| Niveau | Outil | Ce qu'il couvre |
| --- | --- | --- |
| Unitaire | pytest | Formules (de-vig, EV, Kelly, dénouement), features |
| **Propriétés** | **Hypothesis** | Invariants mathématiques : `Σ p = 1`, `EV = 0` quand `o = 1/p`, de-vig idempotent, monotonie de l'EV en la cote |
| Intégration | pytest + Postgres éphémère | Requêtes point-in-time, migrations |
| **Anti-fuite** | pytest | Un test dédié par fuite du doc 07 §2 |
| Contrat API | schemathesis (depuis OpenAPI) | Conformité des réponses |
| Régression de modèle | pytest + jeu figé | Le modèle produit les mêmes probabilités qu'au commit de référence sur 200 matchs |
| E2E | Playwright | Parcours principal du dashboard |

Les tests par propriétés sont particulièrement adaptés ici : les formules
financières ont des invariants clairs et vérifiables, et ce sont exactement
les endroits où une erreur de signe passe inaperçue à l'œil nu.

---

## 8. Récapitulatif de la stack recommandée

```
┌───────────────────────────────────────────────────────────────────────┐
│  FRONTEND       Next.js 15 (App Router) · TypeScript · Tailwind       │
│                 shadcn/ui · TanStack Query · Visx · SSE               │
├───────────────────────────────────────────────────────────────────────┤
│  API            FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic        │
├───────────────────────────────────────────────────────────────────────┤
│  ML / QUANT     Polars · scikit-learn · LightGBM · statsmodels        │
│                 SHAP · Optuna · MLflow · (PyMC en V2)                 │
├───────────────────────────────────────────────────────────────────────┤
│  ORCHESTRATION  Prefect 3                                             │
├───────────────────────────────────────────────────────────────────────┤
│  DONNÉES        PostgreSQL 16 (partitionné) · Redis · DuckDB+Parquet  │
│                 Object storage S3-compatible                          │
├───────────────────────────────────────────────────────────────────────┤
│  INFRA          Docker · GitHub Actions · PaaS managé                 │
│                 Sentry · Prometheus/Grafana · structlog               │
└───────────────────────────────────────────────────────────────────────┘
```

**Coût mensuel estimé au démarrage** (hors données) :

| Poste | Coût |
| --- | --- |
| API + worker (PaaS) | 25 € |
| PostgreSQL managé (avec PITR) | 30 € |
| Redis | 10 € |
| Object storage | 5 € |
| Monitoring (offres gratuites) | 0 € |
| **Total infrastructure** | **~70 €/mois** |
| **Données** (le vrai coût — voir doc 16) | **80-400 €/mois** |

> À retenir : **les données coûtent plus cher que l'infrastructure**, souvent
> d'un facteur 3 à 5. C'est un renversement par rapport à l'intuition
> habituelle, et cela doit orienter les arbitrages : mieux vaut un VPS à
> 15 € et un bon fournisseur de cotes que l'inverse.
