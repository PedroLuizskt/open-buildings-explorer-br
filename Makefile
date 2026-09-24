# Makefile — atalhos de desenvolvimento para Unix/Mac.
# Equivalente Windows/PowerShell está em tasks.ps1.

.PHONY: help setup test test-network lint format notebook clean

# Nome do venv (customizável via env var VENV)
VENV ?= .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

help:
	@echo "Comandos disponiveis:"
	@echo "  setup         - Cria venv, instala pacote em modo editavel com extras dev+notebook"
	@echo "  test          - Roda suite pytest offline com cobertura"
	@echo "  test-network  - Roda testes que dependem de acesso ao S3 publico"
	@echo "  lint          - Executa ruff check sobre o codigo"
	@echo "  format        - Aplica ruff format"
	@echo "  notebook      - Sobe Jupyter Lab na pasta notebooks/"
	@echo "  clean         - Remove artefatos de build, cache e cobertura"

setup:
	@echo "[SETUP] Criando ambiente virtual em $(VENV)/"
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev,notebook]"
	@echo "[OK] Setup concluido. Ative com: source $(VENV)/bin/activate"
	@echo "[OK] Rodando suite inicial para confirmar instalacao..."
	$(PYTHON) -m pytest tests/ -q

test:
	$(PYTHON) -m pytest tests/

test-network:
	$(PYTHON) -m pytest tests/ -m network

lint:
	$(PYTHON) -m ruff check src/ tests/

format:
	$(PYTHON) -m ruff format src/ tests/

notebook:
	$(PYTHON) -m jupyter lab --notebook-dir=notebooks/

clean:
	@echo "[CLEAN] Removendo artefatos de build e cache..."
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	rm -rf .pytest_cache/ .ruff_cache/ .coverage htmlcov/
	rm -rf reports/coverage/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ipynb_checkpoints -exec rm -rf {} + 2>/dev/null || true
	@echo "[OK] Limpeza concluida."
