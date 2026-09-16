# Le Makefile est de la documentation exécutable : chaque cible correspond à
# une action décrite dans docs/.
.DEFAULT_GOAL := help
SHELL := /bin/bash
VENV := .venv
PY := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest

.PHONY: help
help:  ## affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup:  ## crée l'environnement et installe les dépendances de développement
	uv venv $(VENV) || python3 -m venv $(VENV)
	uv pip install --python $(PY) -e ".[dev]" || $(PY) -m pip install -e ".[dev]"

.PHONY: up
up:  ## démarre Postgres et Redis (le schéma est appliqué au premier démarrage)
	docker compose up -d postgres redis

.PHONY: down
down:  ## arrête les services
	docker compose down

.PHONY: psql
psql:  ## ouvre un shell SQL sur la base locale
	docker compose exec postgres psql -U spp -d spp

.PHONY: test
test:  ## exécute toute la suite de tests
	$(PYTEST)

.PHONY: test-leakage
test-leakage:  ## tests anti-fuite uniquement — à lancer AVANT tout backtest
	$(PYTEST) -m leakage tests/leakage

.PHONY: lint
lint:  ## ruff + mypy + frontières de modules
	$(VENV)/bin/ruff check spp tests
	$(VENV)/bin/ruff format --check spp tests
	$(VENV)/bin/mypy spp
	$(VENV)/bin/lint-imports

.PHONY: format
format:  ## applique le formatage
	$(VENV)/bin/ruff format spp tests
	$(VENV)/bin/ruff check --fix spp tests

.PHONY: api
api:  ## démarre l'API en rechargement à chaud
	$(VENV)/bin/uvicorn spp.api.main:app --reload --port 8000

.PHONY: schema-check
schema-check:  ## applique sql/schema.sql sur une base jetable et le valide
	./scripts/check_schema.sh

# --- cibles des phases suivantes, déclarées pour que la roadmap soit lisible ---
.PHONY: backfill features train backtest predict
backfill:   ## [phase 3] charge l'historique
	@echo "Phase 3 — ingestion non implémentée"
features:   ## [phase 4] recalcule le feature store
	@echo "Phase 4 — feature engineering non implémenté"
train:      ## [phase 5-6] entraîne et enregistre le modèle champion
	@echo "Phase 5-6 — modèles non implémentés"
backtest:   ## [phase 7] exécute un backtest
	@echo "Phase 7 — backtesting non implémenté"
predict:    ## [phase 6] run de prédiction
	@echo "Phase 6 — inférence non implémentée"
