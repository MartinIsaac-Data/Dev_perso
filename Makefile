.PHONY: help install setup migrate seed demo reset test lint fmt run graph status docker \
        web web-install web-build web-check check

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install the backend and its development dependencies
	pip install -e ".[dev,postgres,analytics]"

setup: install migrate seed  ## Fresh install: dependencies, schema, seeds
	@echo "Ready. Run 'make run' then open http://localhost:8000/docs"

migrate:  ## Apply migrations
	python -m alembic upgrade head

seed:  ## Load the reference taxonomy, the demo profile and an empty owner profile
	python -m app.cli seed all

demo:  ## Rebuild the demonstration profile only
	python -m app.cli seed demo

reset:  ## Delete the local database and rebuild it from scratch
	rm -f data/transformation_os.db
	$(MAKE) migrate seed

test:  ## Run the test suite
	python -m pytest -q

test-cov:  ## Run the test suite with a coverage report
	python -m pytest --cov=app --cov-report=term-missing

lint:  ## Check formatting and lint rules
	python -m ruff check .

fmt:  ## Apply automatic fixes
	python -m ruff check . --fix
	python -m ruff format .

run:  ## Start the API with reload
	python -m uvicorn app.main:app --reload --app-dir backend

web-install:  ## Install front-end dependencies
	cd frontend && npm install

web:  ## Start the front end (expects `make run` in another terminal)
	cd frontend && npm run dev

web-build:  ## Type-check and build the front end
	cd frontend && npm run build

web-check:  ## Type-check the front end without building
	cd frontend && npm run typecheck

check: lint test web-check  ## Everything CI would run

graph:  ## Verify the skill graph and show its critical path
	python -m app.cli graph check
	@echo ""
	@echo "Skills gating the most others:"
	@python -m app.cli graph critical

status:  ## Show what is currently in the database
	python -m app.cli status

docker:  ## Build and start the stack
	docker compose up --build
