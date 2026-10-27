.PHONY: install backend frontend test lint benchmark run

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	cd frontend && npm ci

backend:
	.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	.venv/bin/pytest -q

lint:
	.venv/bin/ruff check backend
	cd frontend && npm run build

benchmark:
	.venv/bin/python scripts/benchmark.py

run:
	docker compose up --build
