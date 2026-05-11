.PHONY: help install install-local run run-remote test lint format docker-up docker-down clean

PY ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
PYBIN := $(VENV)/bin/python

help:
	@echo "OpenCR developer targets:"
	@echo "  make install        # venv + base deps + local-backend deps (Mac/CPU friendly)"
	@echo "  make run            # start dev server on http://localhost:39672 with the local backend"
	@echo "  make run-remote     # start dev server pointing at MODEL_SERVER_URL"
	@echo "  make test           # run pytest suite"
	@echo "  make lint           # ruff check"
	@echo "  make format         # ruff format"
	@echo "  make docker-up      # docker compose up (NVIDIA GPU profile)"
	@echo "  make docker-down    # docker compose down"

$(VENV):
	$(PY) -m venv $(VENV)
	$(PIP) install -U pip

install: $(VENV)
	$(PIP) install -r ocr_pipeline/requirements.txt -r requirements-local.txt
	$(PIP) install -r requirements-dev.txt

run: $(VENV)
	MODEL_BACKEND=local $(PYBIN) -m uvicorn ocr_pipeline.main:app --host 0.0.0.0 --port 39672 --reload

run-remote: $(VENV)
	MODEL_BACKEND=remote $(PYBIN) -m uvicorn ocr_pipeline.main:app --host 0.0.0.0 --port 39672 --reload

test: $(VENV)
	PYTHONPATH=. $(PYBIN) -m pytest -q

lint: $(VENV)
	$(VENV)/bin/ruff check ocr_pipeline tests scripts

format: $(VENV)
	$(VENV)/bin/ruff format ocr_pipeline tests scripts

docker-up:
	docker compose --profile gpu up -d

docker-down:
	docker compose down

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache **/__pycache__
