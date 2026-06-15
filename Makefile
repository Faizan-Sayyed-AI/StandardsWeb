.PHONY: up down restart logs build migrate revision seed shell lint test ps

# ── Docker ────────────────────────────────────────────────
up:           ## Start all services (build first if needed)
	docker compose up --build -d

down:         ## Stop and remove all containers
	docker compose down

restart:      ## Rebuild and restart a specific service: make restart SVC=web
	docker compose up --build -d $(SVC)

logs:         ## Follow logs for web + worker + beat
	docker compose logs -f web worker beat

build:        ## Force rebuild all images
	docker compose build --no-cache

ps:           ## Show running containers
	docker compose ps

# ── Database ──────────────────────────────────────────────
migrate:      ## Apply all pending Alembic migrations
	docker compose exec web alembic upgrade head

downgrade:    ## Roll back one migration
	docker compose exec web alembic downgrade -1

revision:     ## Generate a new migration: make revision MSG="add foo table"
	docker compose exec web alembic revision --autogenerate -m "$(MSG)"

seed:         ## Insert default admin user into the database
	docker compose exec web python scripts/seed.py

# ── Dev tools ─────────────────────────────────────────────
shell:        ## Open a Python REPL inside the web container
	docker compose exec web python

bash:         ## Open a bash shell inside the web container
	docker compose exec web bash

lint:         ## Run ruff linter on the backend source
	docker compose exec web ruff check app/

format:       ## Auto-format backend source with ruff
	docker compose exec web ruff format app/

typecheck:    ## Run mypy type checker on the backend source
	docker compose exec web mypy app/

test:         ## Run the backend test suite with pytest
	docker compose exec web pytest

# ── Help ──────────────────────────────────────────────────
help:         ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
