PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup format lint test security qa build local-api-init up down logs

setup:
	python3 -m venv .venv
	$(PIP) install -e '.[dev]'

format:
	.venv/bin/ruff format .
	.venv/bin/ruff check --fix .

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

test:
	$(PYTHON) -m pytest

security:
	.venv/bin/bandit -c pyproject.toml -r app
	.venv/bin/pip-audit

qa: lint test security
	docker compose config --quiet

build:
	docker compose build

local-api-init:
	docker compose run --rm --no-deps bot python -m app.bot.local_api_setup

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200
