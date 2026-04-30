# Makefile — MIL-122 fork-friendly entry points.
#
# Thin wrapper around bootstrap.sh — same behaviour, named targets for muscle
# memory. The shell script is the source of truth; run it directly if you
# prefer (./bootstrap.sh setup|sample|run|demo|clean).

SHELL := /bin/bash
.DEFAULT_GOAL := help

.PHONY: help demo setup sample run clean test drift-check

help:
	@echo "while-sleeping / CJI engine — make targets"
	@echo ""
	@echo "  make demo         Full bootstrap: venv + deps + sample corpus + pipeline run"
	@echo "  make setup        Just create venv and install requirements"
	@echo "  make sample       Just copy frozen sample corpus → mil/data/historical/enriched"
	@echo "  make run          Just run the pipeline (--skip-fetch — assumes enriched data is staged)"
	@echo "  make clean        Remove venv + rendered briefings + mil_findings.json"
	@echo ""
	@echo "  make test         Run the pytest suite (config + publish + chat scope)"
	@echo "  make drift-check  Run the WorkOS config drift checker (MIL-120)"
	@echo ""
	@echo "First-time fork: run \`make demo\` and open mil/publish/output/index_v4.html"

demo:
	@./bootstrap.sh demo

setup:
	@./bootstrap.sh setup

sample:
	@./bootstrap.sh sample

run:
	@./bootstrap.sh run

clean:
	@./bootstrap.sh clean

test:
	@./bootstrap.sh setup
	@. .venv/Scripts/activate 2>/dev/null || . .venv/bin/activate; \
		py -m pytest mil/tests/test_tenant_loader.py mil/tests/test_workos_loader.py mil/tests/test_workos_drift.py mil/tests/test_publish_deny_list.py mil/tests/test_box3_selection.py -q

drift-check:
	@. .venv/Scripts/activate 2>/dev/null || . .venv/bin/activate || true; \
		py mil/auth/scripts/check_workos_drift.py
