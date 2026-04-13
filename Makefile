UV := uv

.PHONY: sync format lint typecheck test smoke integration load load-validate precommit compose-up compose-down

sync:
	$(UV) sync --all-groups

format:
	$(UV) run ruff format .

lint:
	$(UV) run ruff check .

typecheck:
	$(UV) run ty check

test:
	uv run pytest --cov=shared --cov=services --cov-report=term-missing

smoke:
	uv run pytest tests/smoke -q --cov=shared --cov=services --cov-report=term-missing

integration:
	$(UV) run pytest tests/integration -q

load:
	$(UV) run locust -f tests/load/locustfile.py

load-validate:
	$(UV) run python scripts/run_load_validation.py

precommit:
	$(UV) run pre-commit run --all-files

compose-up:
	docker compose up --build -d

compose-down:
	docker compose down -v
