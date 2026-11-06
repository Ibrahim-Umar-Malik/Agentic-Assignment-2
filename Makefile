# GigBid. `make help` lists targets. Offline targets need no API keys.
PY ?= .venv/bin/python
OFFLINE = GIGBID_PROFILE=offline

.PHONY: help install seed dev up down test e2e lint checks eval eval-llm tables report demo zip

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-10s %s\n", $$1, $$2}'

install: ## Python venv + web deps
	uv venv .venv --python 3.12 && uv pip install --python $(PY) -r pyproject.toml --extra dev
	cd apps/web && npm ci

seed: ## regenerate the stand-in personas, GigSim seed data and dev sets (deterministic, SEED=4016)
	$(PY) scripts/generate_standin_data.py

dev: ## run GigSim stand-in + API + built web UI on :8080 (single process, in-process MCP)
	cd apps/web && npm run build
	bash scripts/run_all.sh

up: ## full stack in Docker (Postgres/pgvector, Redis, 3 MCP servers, worker, web) on :8080
	docker compose up --build

down:
	docker compose down

test: ## unit, contract and integration tests (offline profile)
	$(OFFLINE) $(PY) -m pytest

e2e: ## Playwright end-to-end tests (starts its own servers)
	cd apps/web && npm run build && npx playwright test

lint: ## ruff + TypeScript
	$(PY) -m ruff check .
	cd apps/web && npx tsc -b

checks: ## CI guards: secrets, gigsim unchanged, prompts versioned, numbers trace to results
	$(PY) scripts/check_secrets.py
	$(PY) scripts/check_gigsim_unchanged.py
	$(PY) scripts/check_prompts.py
	$(PY) -m evals.make_tables --check

eval: ## every offline eval -> evals/results/*.json, then refresh README/report tables
	$(OFFLINE) $(PY) -m evals.runners.rag_eval
	$(OFFLINE) $(PY) -m evals.runners.ablation
	$(OFFLINE) $(PY) -m evals.runners.decision_eval --sweep
	$(OFFLINE) $(PY) -m evals.runners.gigsim_outcomes
	$(OFFLINE) $(PY) -m evals.runners.judge_calibration score
	$(OFFLINE) $(PY) -m evals.runners.architecture_compare
	$(OFFLINE) $(PY) -m evals.runners.tool_granularity
	$(PY) -m evals.make_tables

eval-llm: ## the same evals with real open-weight models (needs GROQ_API_KEY, or GIGBID_PROFILE=open_local + Ollama)
	GIGBID_PROFILE=$${GIGBID_PROFILE:-open} $(PY) -m evals.runners.decision_eval --sweep
	GIGBID_PROFILE=$${GIGBID_PROFILE:-open} $(PY) -m evals.runners.gigsim_outcomes
	GIGBID_PROFILE=$${GIGBID_PROFILE:-open} $(PY) -m evals.runners.judge_calibration score
	GIGBID_PROFILE=$${GIGBID_PROFILE:-open} $(PY) -m evals.runners.architecture_compare
	GIGBID_PROFILE=$${GIGBID_PROFILE:-open} $(PY) -m evals.runners.tool_granularity
	$(PY) -m evals.make_tables

tables: ## re-render README / report tables from evals/results
	$(PY) -m evals.make_tables

report: ## build docs/report/GigBid_RnD_Report.pdf from docs/report/report.md
	$(PY) scripts/build_report.py

demo: ## advance GigSim time so clients view and reply (for the demo video)
	curl -s -X POST localhost:8001/v1/admin/tick

zip: ## submission ZIP (source without node_modules, .venv, var)
	$(PY) scripts/make_submission_zip.py
