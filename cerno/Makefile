.PHONY: doctor setup test lint safety clean help

PYTHON ?= python

help:
	@echo "Cerno scaffolding targets:"
	@echo "  make doctor   - preflight env check (versions, paths)"
	@echo "  make setup    - create data/ manifests/ findings/ directories"
	@echo "  make test     - run pytest"
	@echo "  make lint     - byte-compile all package modules"
	@echo "  make safety   - confirm import-time safety gate fires clean"
	@echo "  make clean    - remove data outputs + __pycache__"

doctor:
	$(PYTHON) scripts/doctor.py

setup:
	mkdir -p data/extract data/ma_d data/ma_s data/marts manifests findings

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m py_compile src/cerno/*.py

safety:
	$(PYTHON) -c "from cerno.safety import assert_safe; assert_safe(); print('safety: OK')"

clean:
	rm -rf data/ manifests/ findings/ .pytest_cache/
	find . -name __pycache__ -type d -exec rm -rf {} +
	find . -name "*.pyc" -delete
