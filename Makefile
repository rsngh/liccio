.PHONY: help sync test test-unit test-integration test-e2e lint type fmt check coverage \
        soak-6h eval-bakeoff-overnight bandit-monte-carlo retriever-stress chaos security-redteam

UV ?= uv

help:
	@echo "Targets:"
	@echo "  sync                       uv sync --all-extras"
	@echo "  check                      lint + type + fast tests"
	@echo "  test                       unit + integration + lint + type"
	@echo "  test-e2e                   end-to-end tests"
	@echo "  coverage                   coverage report (core >= 85%)"
	@echo "  soak-6h                    long soak of fake-agent workflows"
	@echo "  eval-bakeoff-overnight     adapter bakeoff -> evals/reports"
	@echo "  bandit-monte-carlo         bandit vs random simulation"
	@echo "  retriever-stress           synthetic large-repo retrieval stress"
	@echo "  chaos                      kill/resume workflow test"
	@echo "  security-redteam           malicious-task safety suite"

sync:
	$(UV) sync --all-extras

test-unit:
	$(UV) run pytest tests/unit -q

test-integration:
	$(UV) run pytest tests/integration -q

test:
	$(UV) run pytest tests/unit tests/integration -q
	$(UV) run ruff check .
	$(UV) run mypy src

test-e2e:
	$(UV) run pytest tests/e2e -q --timeout=600

lint:
	$(UV) run ruff check .

fmt:
	$(UV) run ruff format .
	$(UV) run ruff check . --fix

type:
	$(UV) run mypy src

check: lint type test-unit

coverage:
	$(UV) run pytest tests/unit tests/integration \
		--cov=acp --cov-report=term-missing --cov-report=xml

soak-6h:
	$(UV) run python evals/scripts/run_soak.py --hours 6

eval-bakeoff-overnight:
	$(UV) run python evals/scripts/run_bakeoff.py --overnight

bandit-monte-carlo:
	$(UV) run python evals/scripts/run_bandit_sim.py --seeds 100

retriever-stress:
	$(UV) run pytest tests/long/test_retriever_stress.py -q

chaos:
	$(UV) run pytest tests/long/test_command_runner_chaos.py -q

security-redteam:
	$(UV) run pytest tests/long -q -k redteam
