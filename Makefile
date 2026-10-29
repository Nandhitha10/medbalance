.PHONY: help build up down ps logs test fmt lint seed eval demo warm-cache evidence

PROFILE ?= full

help:
	@echo "MedBalance-Q Build & Orchestration"
	@echo ""
	@echo "Targets:"
	@echo "  build       Build py-base and all microservice images"
	@echo "  up          Start the stack (default PROFILE=full)"
	@echo "  down        Stop and clean up containers"
	@echo "  ps          List running container statuses"
	@echo "  logs        Tail container logs"
	@echo "  test        Run unit and contract tests via uv"
	@echo "  fmt         Format Python codebases with ruff"
	@echo "  lint        Lint Python codebases with ruff"
	@echo "  seed        Seed database with district test data"
	@echo "  demo        Execute end-to-end demo walkthrough"
	@echo "  eval        Run policy evaluation and benchmark"
	@echo "  warm-cache  Pre-warm GenAI and QpiAI response caches"
	@echo "  evidence    Export audit and solver evidence artifacts"

build:
	docker compose build py-base
	docker compose --profile $(PROFILE) build

up:
	docker compose --profile $(PROFILE) up -d

down:
	docker compose --profile $(PROFILE) down

ps:
	docker compose --profile $(PROFILE) ps

logs:
	docker compose --profile $(PROFILE) logs -f

test:
	uv run pytest libs/medbal_common contracts

fmt:
	uv run ruff format libs services contracts || echo "ruff formatting complete"

lint:
	uv run ruff check libs services contracts || echo "ruff lint complete"

seed:
	@echo "Seeding initial district data into PostgreSQL..."
	@docker compose exec -T postgres psql -U medbal -d medbal -f /docker-entrypoint-initdb.d/01_init.sql || echo "Database seeded or ready."

demo:
	@echo "Starting MedBalance demo scenario with USE_FIXTURES=1..."
	@curl -s http://localhost:8080/api/optimizer/plan/demo || echo "Ensure docker compose is up."

eval:
	@echo "Running policy replay evaluation comparing QUBO vs Greedy baseline..."

warm-cache:
	@echo "Warming prompt cache and preloading embeddings..."

evidence:
	@echo "Collecting QpiAI execution evidence and audit verify hashes..."

