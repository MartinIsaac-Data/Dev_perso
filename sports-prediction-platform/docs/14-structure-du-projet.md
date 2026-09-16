# 14 — Structure du dépôt

---

## 1. Arborescence

```
sports-prediction-platform/
│
├── README.md
├── pyproject.toml                 # uv/hatch · ruff · mypy · pytest
├── docker-compose.yml             # postgres, redis, api, worker, prefect
├── Makefile                       # setup, test, lint, backfill, backtest, run
├── .env.example
├── .importlinter                  # frontières de modules appliquées en CI
│
├── docs/                          # ce dossier de conception
│   ├── 01-architecture-conceptuelle.md
│   ├── ...
│   └── adr/                       # Architecture Decision Records
│       ├── 0001-raw-append-only.md
│       ├── 0002-bitemporal-core.md
│       └── ...
│
├── sql/
│   ├── schema.sql                 # DDL de référence, exécutable
│   └── analytics/                 # requêtes DuckDB pour les backtests
│
├── spp/                           # ← le paquet Python principal
│   #   (PAS `platform` : c'est un module de la stdlib — voir ADR-0009)
│   │
│   ├── core/                      # domaine pur, ne dépend de rien
│   │   ├── entities.py            # Match, Competitor, Selection…
│   │   ├── enums.py
│   │   ├── sports/                # adaptateurs par sport
│   │   │   ├── base.py            # protocole SportAdapter
│   │   │   ├── football.py
│   │   │   ├── basketball.py
│   │   │   └── tennis.py
│   │   ├── settlement.py          # règles de dénouement (partagées prod/backtest)
│   │   └── time.py                # as_of_ts, fenêtres, fuseaux
│   │
│   ├── db/
│   │   ├── models.py              # SQLAlchemy
│   │   ├── session.py
│   │   ├── repositories/
│   │   │   ├── point_in_time.py   # ← LE point de contrôle anti-fuite
│   │   │   ├── matches.py
│   │   │   ├── odds.py
│   │   │   └── features.py
│   │   └── migrations/            # Alembic
│   │
│   ├── ingestion/
│   │   ├── base.py                # Connector, retry, circuit breaker
│   │   ├── providers/
│   │   │   ├── fixtures_x.py
│   │   │   ├── odds_y.py
│   │   │   ├── stats_z.py
│   │   │   └── weather_open_meteo.py
│   │   ├── entity_resolution.py   # matching en 3 passes
│   │   └── validation.py          # schémas attendus, quarantaine
│   │
│   ├── canonical/
│   │   ├── mappers/               # raw → core, par provider
│   │   ├── conflicts.py           # résolution + traçage
│   │   └── quality.py             # contrôles sémantiques
│   │
│   ├── features/
│   │   ├── registry.py            # chargement du YAML, validation
│   │   ├── definitions/
│   │   │   ├── core.yaml
│   │   │   ├── football.yaml
│   │   │   ├── basketball.yaml
│   │   │   └── tennis.yaml
│   │   ├── engine.py              # calcul point-in-time, hash
│   │   ├── computers/
│   │   │   ├── form.py
│   │   │   ├── ratings_elo.py
│   │   │   ├── fatigue.py
│   │   │   ├── stakes.py          # Monte-Carlo d'enjeu
│   │   │   ├── h2h.py
│   │   │   ├── player_impact.py   # PITS
│   │   │   └── market.py
│   │   └── store.py
│   │
│   ├── models/
│   │   ├── base.py                # protocole ProbabilityModel
│   │   ├── statistical/
│   │   │   ├── poisson.py
│   │   │   ├── dixon_coles.py
│   │   │   ├── normal_diff.py     # basketball
│   │   │   └── markov_tennis.py
│   │   ├── ml/
│   │   │   ├── lgbm.py
│   │   │   └── features_prep.py
│   │   ├── rating_model.py
│   │   ├── market_model.py
│   │   ├── ensemble.py            # stacking — reçoit le marché EN ENTRÉE
│   │   ├── calibration.py
│   │   ├── uncertainty.py         # bootstrap, σ_p
│   │   ├── explain.py             # SHAP + décomposition additive
│   │   └── registry.py            # MLflow
│   │
│   ├── market/
│   │   ├── devig.py               # 5 méthodes
│   │   ├── consensus.py
│   │   ├── movements.py           # z-score, steam, RLM
│   │   └── clv.py
│   │
│   ├── valuation/
│   │   ├── ev.py                  # EV, edge, fair odds
│   │   ├── signals.py             # les 7 conditions du doc 06 §4.2
│   │   └── staking.py             # flat, %, Kelly, Kelly incertain
│   │
│   ├── backtest/
│   │   ├── clock.py
│   │   ├── universe.py
│   │   ├── engine.py
│   │   ├── frictions.py
│   │   ├── metrics.py
│   │   ├── report.py
│   │   └── config.py
│   │
│   ├── api/
│   │   ├── main.py
│   │   ├── deps.py
│   │   ├── routers/
│   │   │   ├── matches.py
│   │   │   ├── teams.py
│   │   │   ├── odds.py
│   │   │   ├── predictions.py
│   │   │   ├── value.py
│   │   │   ├── models.py
│   │   │   ├── backtests.py
│   │   │   ├── bets.py
│   │   │   └── health.py
│   │   ├── schemas/
│   │   ├── cache.py
│   │   └── streaming.py           # SSE
│   │
│   ├── orchestration/
│   │   ├── flows/
│   │   │   ├── sync_fixtures.py
│   │   │   ├── sync_odds.py
│   │   │   ├── sync_lineups.py
│   │   │   ├── compute_features.py
│   │   │   ├── run_predictions.py
│   │   │   ├── evaluate.py
│   │   │   └── recalibrate.py
│   │   ├── schedules.py
│   │   └── events.py              # lineup_published, odds_steam…
│   │
│   ├── alerts/
│   │   ├── rules.py
│   │   ├── dedupe.py              # hystérésis, regroupement
│   │   └── channels/              # push, email, slack
│   │
│   └── common/
│       ├── config.py              # Pydantic Settings
│       ├── logging.py             # structlog
│       ├── errors.py
│       └── hashing.py
│
├── frontend/
│   ├── app/                       # Next.js App Router
│   │   ├── matches/[id]/page.tsx
│   │   ├── teams/[id]/page.tsx
│   │   ├── model/page.tsx         # performance & calibration
│   │   └── backtests/[id]/page.tsx
│   ├── components/
│   │   ├── charts/                # specs du doc 11 §2
│   │   ├── probability-bar.tsx
│   │   ├── dumbbell.tsx
│   │   ├── meter.tsx
│   │   ├── markets-table.tsx
│   │   └── explanation-panel.tsx
│   ├── lib/
│   │   ├── api.ts
│   │   ├── palette.ts             # palette validée par script
│   │   └── format.ts              # cotes, probas, EV — un seul formateur
│   └── package.json
│
├── notebooks/                     # exploration UNIQUEMENT, jamais en prod
│   └── README.md                  # "aucun notebook n'est importé par spp/"
│
├── tests/
│   ├── unit/
│   ├── properties/                # Hypothesis : invariants mathématiques
│   ├── integration/
│   ├── leakage/                   # un test par fuite du doc 07 §2
│   ├── contract/                  # par provider + API
│   ├── regression/                # probabilités figées sur 200 matchs
│   └── fixtures/
│
├── scripts/
│   ├── backfill.py
│   ├── create_partitions.py
│   ├── validate_palette.js
│   └── check_feature_drift.py
│
├── docker/
│   ├── Dockerfile                 # multi-étapes, image unique api+worker
│   └── Dockerfile.frontend
│
└── .github/workflows/
    ├── ci.yml                     # lint, types, tests, import-linter
    ├── migrations.yml             # dry-run sur copie de staging
    └── deploy.yml
```

---

## 2. Les décisions de structure qui comptent

> **Correction apportée en phase 1.** Ce document proposait initialement un
> paquet nommé `platform/`. C'est un **module de la bibliothèque standard
> Python** : un paquet de premier niveau portant ce nom le masque pour tout le
> processus, y compris pour les dépendances qui l'importent. Le paquet
> s'appelle donc `spp`. Voir [ADR-0009](adr/0009-nom-du-paquet-spp.md).

### 2.1 Un seul paquet `spp/`, pas un mono-repo de services

Les imports sont directs, le typage traverse tout le système, et le
refactoring est mécanique. Les frontières sont appliquées par
**import-linter** en CI :

```ini
[importlinter:contract:layers]
name = Couches de la plateforme
type = layers
layers =
    spp.api
    spp.backtest
    spp.valuation
    spp.models
    spp.market
    spp.features
    spp.canonical
    spp.ingestion
    spp.db
    spp.core

[importlinter:contract:features-independent-of-models]
name = Les features ne connaissent pas les modèles
type = forbidden
source_modules = spp.features
forbidden_modules = spp.models

[importlinter:contract:models-independent-of-market]
name = Les modèles ne lisent pas le marché directement
type = forbidden
source_modules = spp.models.statistical, spp.models.ml
forbidden_modules = spp.market
```

Un quatrième contrat garde le domaine pur : `spp.core` ne peut importer ni
SQLAlchemy, ni FastAPI, ni Redis, ni httpx.

Le troisième contrat est le plus important : il rend **impossible** qu'un
modèle aille chercher les cotes en douce. Le marché n'entre que par
`spp.models.ensemble`, où il est un argument explicite de fonction.
C'est le double comptage rendu visible par la structure du code.

**Vérifié, pas supposé** : une violation délibérée a été introduite
(`spp/models/statistical/_violation_probe.py` important `spp.market`) puis
retirée. `lint-imports` la signale et sort en code 1, ce qui casse la CI. Un
contrat qui n'a jamais échoué n'est pas un contrat.

### 2.2 `notebooks/` est une impasse volontaire

Aucun module de `spp/` n'importe quoi que ce soit de `notebooks/`, et
la CI le vérifie. Les notebooks servent à explorer ; dès qu'une idée est
retenue, elle est réimplémentée dans `spp/` avec des tests. C'est la
seule façon d'éviter le classique « le modèle de production est un notebook
exporté ».

### 2.3 `core/settlement.py` est partagé

La règle qui décide si un pari est gagné est **la même fonction** en backtest
et en production. C'est non négociable : deux implémentations divergeraient
sur les cas limites (handicaps en quarts, matchs abandonnés, abandons au
tennis) et produiraient un backtest faussement positif.

### 2.4 `frontend/lib/format.ts` centralise l'affichage

Un seul formateur pour les cotes, les probabilités et les EV. Sans cela, on
voit apparaître `48.2%`, `0.482` et `48,24 %` sur trois écrans différents —
un défaut de crédibilité disproportionné par rapport à sa cause.

---

## 3. Conventions

| Sujet | Convention |
| --- | --- |
| Langue du code | **Anglais** (identifiants, docstrings, messages de log) |
| Langue de la documentation | **Français** (ce dossier) |
| Commits | Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`) |
| Branches | `main` protégée · `feat/*`, `fix/*` · PR obligatoire |
| Formatage | `ruff format` · `ruff check` · `mypy` strict sur `spp.core`, `spp.common`, `spp.valuation` et `spp.market` |
| Typage | Annotations obligatoires sur toute fonction publique |
| Tests | Couverture > 85 % sur `core`, `valuation`, `market`, `features` |
| Secrets | Jamais en dépôt · `.env.example` documente chaque variable |
| Versions de modèles | Semver dans MLflow, référencées par `ml.model_versions` |
| ADR | Une par décision structurante, numérotée, jamais supprimée |

---

## 4. Le Makefile comme documentation exécutable

```makefile
setup:        ## installe les dépendances, démarre les services, migre, seed
test:         ## tous les tests
test-leakage: ## uniquement les tests anti-fuite (à exécuter avant tout backtest)
lint:         ## ruff + mypy + import-linter
backfill:     ## charge l'historique (SEASONS=5 LEAGUES=FR1,EN1,...)
features:     ## recalcule le feature store
train:        ## entraîne et enregistre le modèle champion
backtest:     ## exécute un backtest (CONFIG=configs/pessimistic.yaml)
predict:      ## run de prédiction sur les matchs à venir
api:          ## démarre l'API
web:          ## démarre le frontend
```

La commande `make test-leakage` est isolée délibérément : elle doit pouvoir
être lancée seule, rapidement, avant chaque backtest. Un backtest lancé sur
un pipeline qui fuit est pire qu'inutile — il est convaincant.
