# Enterprise Customer Support Agent - lab build
#   make setup && make seed && make run      -> http://localhost:8000
PYTHON ?= python3
VENV   ?= .venv
PY     ?= $(VENV)/bin/python
HOST   ?= 127.0.0.1
PORT   ?= 8000

.PHONY: setup setup-lite seed run run-mock test clean

$(VENV)/bin/python:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip

## Full install: core + ChromaDB + sentence-transformers
setup: $(VENV)/bin/python
	$(PY) -m pip install -r requirements.txt -r requirements-rag.txt
	@test -f .env || cp .env.example .env

## Core only (TF-IDF retriever instead of Chroma; much smaller download)
setup-lite: $(VENV)/bin/python
	$(PY) -m pip install -r requirements.txt
	@test -f .env || cp .env.example .env

## Reset the database + vector store and load synthetic data
seed:
	$(PY) -m app.seed

## Start the API + UI (uses Claude if ANTHROPIC_API_KEY is set and MOCK_LLM is not 1)
run:
	$(PY) -m app.main --host $(HOST) --port $(PORT)

## Start with the deterministic mock LLM (no API key needed)
run-mock:
	$(PY) -m app.main --mock-llm --host $(HOST) --port $(PORT)

## Guardrail test suite (always mock LLM + TF-IDF, isolated temp DBs)
test:
	RAG_BACKEND=tfidf MOCK_LLM=1 $(PY) -m pytest -q

clean:
	rm -rf var .pytest_cache
