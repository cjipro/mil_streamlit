#!/usr/bin/env bash
# bootstrap.sh — MIL-122 5-minute demo bootstrap
#
# Brings a fresh checkout to a working pipeline run with rendered briefings.
#
#   ./bootstrap.sh         # full bootstrap: venv + deps + sample corpus + run
#   ./bootstrap.sh setup   # just the venv + deps install
#   ./bootstrap.sh sample  # just the sample-corpus copy
#   ./bootstrap.sh run     # just the pipeline run (--skip-fetch)
#
# The Makefile wraps these as named targets — `make demo`, `make setup`, etc.
# Use whichever fits your workflow.
#
# Compatible: Mac, Linux, Windows-via-Git-Bash. The Windows-native flow uses
# the `py` launcher and would need adapting; document this when a partner
# asks.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# Pick the Python interpreter — Windows ships `py` but no `python`/`python3`.
if command -v py >/dev/null 2>&1; then
    PY="py"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    echo "[bootstrap] ERROR: no python interpreter found on PATH" >&2
    echo "  Install Python 3.11+ from https://python.org/downloads/" >&2
    exit 1
fi

VENV_DIR=".venv"
SAMPLE_DIR="mil/data/sample"
ENRICHED_DIR="mil/data/historical/enriched"

# ── Helpers ───────────────────────────────────────────────────────────────────

step() { printf "\n[bootstrap] %s\n" "$1"; }

check_python_version() {
    local ver
    ver="$($PY --version 2>&1 | awk '{print $2}')"
    local major minor
    major="$(echo "$ver" | cut -d. -f1)"
    minor="$(echo "$ver" | cut -d. -f2)"
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 11 ]; }; then
        echo "[bootstrap] ERROR: Python 3.11+ required, found $ver" >&2
        exit 1
    fi
    step "Python $ver detected"
}

# ── Targets ───────────────────────────────────────────────────────────────────

do_setup() {
    check_python_version

    if [ ! -d "$VENV_DIR" ]; then
        step "Creating venv at $VENV_DIR"
        $PY -m venv "$VENV_DIR"
    else
        step "Reusing existing venv at $VENV_DIR"
    fi

    # Activate. Git Bash on Windows uses Scripts/, Unix uses bin/.
    if [ -f "$VENV_DIR/Scripts/activate" ]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/Scripts/activate"
    elif [ -f "$VENV_DIR/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
    else
        echo "[bootstrap] ERROR: cannot find venv activation script" >&2
        exit 1
    fi

    step "Installing root requirements"
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt

    if [ -f "mil/requirements.txt" ]; then
        step "Installing mil/ requirements (sentence-transformers, scipy, etc.)"
        pip install --quiet -r mil/requirements.txt
    fi

    step "Setup complete"
}

do_sample() {
    if [ ! -d "$SAMPLE_DIR" ]; then
        echo "[bootstrap] ERROR: sample corpus not found at $SAMPLE_DIR" >&2
        echo "  This means MIL-123 hasn't shipped — your tree is older than this script expects." >&2
        exit 1
    fi

    # Refuse to clobber an already-populated enriched dir. The sample is for
    # bootstrapping a FRESH clone; running this on a live pipeline tree would
    # overwrite real harvested data with 14-record synthetic stubs and corrupt
    # the cumulative corpus. Pass FORCE=1 to override (only sensible if you
    # have a known-good HDFS vault to restore from).
    mkdir -p "$ENRICHED_DIR"
    local existing
    existing="$(find "$ENRICHED_DIR" -maxdepth 1 -name "*_enriched.json" 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$existing" -gt 0 ] && [ "${FORCE:-0}" != "1" ]; then
        step "REFUSING to overwrite — $ENRICHED_DIR already contains $existing enriched file(s)"
        echo "  This script is for bootstrapping a fresh clone, not seeding a live pipeline." >&2
        echo "  If you really mean to overwrite (e.g. you've backed up the tree), re-run with:" >&2
        echo "    FORCE=1 ./bootstrap.sh sample" >&2
        echo "  Otherwise inspect mil/data/historical/enriched/ — your real data is there." >&2
        exit 1
    fi

    step "Copying sample corpus → $ENRICHED_DIR"
    cp "$SAMPLE_DIR"/*_enriched.json "$ENRICHED_DIR/"
    local count
    count="$(find "$SAMPLE_DIR" -maxdepth 1 -name "*_enriched.json" | wc -l | tr -d ' ')"
    step "Sample corpus staged: $count files in $ENRICHED_DIR"
}

do_run() {
    # Activate venv if present (no-op when already active)
    if [ -f "$VENV_DIR/Scripts/activate" ]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/Scripts/activate"
    elif [ -f "$VENV_DIR/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
    fi

    if [ ! -f ".env" ]; then
        step "WARNING: no .env found"
        echo "  cp .env.minimal.example .env  and set ANTHROPIC_API_KEY" >&2
        echo "  Pipeline will run but commentary + exec alert may degrade to fallback prose." >&2
    fi

    step "Running daily pipeline (--skip-fetch — using sample/enriched corpus)"
    $PY run_daily.py --skip-fetch || {
        echo "[bootstrap] pipeline exited non-zero — inspect mil/data/daily_run_log.jsonl for failed_steps" >&2
        exit 1
    }

    step "Pipeline complete"
    echo "  Briefings:"
    echo "    file://$REPO_ROOT/mil/publish/output/index.html       (V1)"
    echo "    file://$REPO_ROOT/mil/publish/output/index_v4.html    (V4 — production)"
    echo "  Findings: mil/outputs/mil_findings.json"
    echo "  Run log:  mil/data/daily_run_log.jsonl"
}

do_demo() {
    do_setup
    do_sample
    do_run
}

do_clean() {
    step "Removing build artefacts"
    rm -rf "$VENV_DIR"
    rm -f mil/publish/output/index*.html
    rm -f mil/outputs/mil_findings.json
    step "Clean done — sample corpus and source files preserved"
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

case "${1:-demo}" in
    setup)  do_setup ;;
    sample) do_sample ;;
    run)    do_run ;;
    demo)   do_demo ;;
    clean)  do_clean ;;
    *)
        echo "Usage: $0 [setup|sample|run|demo|clean]" >&2
        echo "  Default (no arg): demo — full bootstrap flow" >&2
        exit 2
        ;;
esac
