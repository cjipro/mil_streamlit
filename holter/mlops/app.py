"""MLOps Console — Surface 4 of Holter (the face of Pulse).

The procurement-gate surface — mandatory before any live bank deployment.
Four panes via Streamlit tabs:

1. **Drift monitors** — per FrictionBench signature × screen cell.
   v0: structure + Designed Ceiling (no analytics layer / live FrictionBench
   runs yet — gated on PULSE-93).

2. **Fairness re-check registry** — real read of
   ``pulse/convergence/methods.yaml``. Shows statistical-power + fairness-aware
   methods + per-question-class fairness method mapping. v0: live
   re-checks gated on PULSE-93.

3. **Lineage verifier** — paste lineage rows as JSON, calls
   ``pulse.lineage.verifier.verify_chain``. Fully functional today.

4. **Synthesis-mode governance** — table of every registered pack with
   synthesis_mode, attestation framework, status, last reviewed. Real.

**Critical alert-fatigue mitigation per HOL-6 ticket:** every drift /
fairness alert in v1 ships with a deterministic narrative paragraph
generated via ``pulse.synthesis.TemplateSynthesisProvider``
(*"what changed, for whom, with what evidence, recommended response"*).
v0 declares the gap honestly — synthesis is a skeleton (PULSE-93). The
console eats its own dogfood once PULSE-93 lands.

**v0 stack note:** Streamlit-only for v0. The HOL-6 ticket scopes
Streamlit + FastAPI; FastAPI backing becomes relevant in v1 when MLOps
needs persisted drift data + scheduled re-checks. Until then, direct
``pulse/`` reads via in-process Python are simpler + adequate.

Run locally::

    py -m pip install -e .[ui]
    streamlit run holter/mlops/app.py
"""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import streamlit as st
import yaml

from pulse.lineage.verifier import verify_chain
from pulse.synthesis.base import SynthesisMode

PULSE_ROOT = Path(__file__).resolve().parents[2] / "pulse"
PACKS_DIR = PULSE_ROOT / "decision_packs"
METHODS_PATH = PULSE_ROOT / "convergence" / "methods.yaml"


# ---------------------------------------------------------------------- Helpers

def _pulse_version() -> str:
    try:
        return importlib.metadata.version("pulse")
    except importlib.metadata.PackageNotFoundError:
        return "(not installed)"


def _load_methods() -> dict:
    if not METHODS_PATH.exists():
        return {}
    return yaml.safe_load(METHODS_PATH.read_text(encoding="utf-8"))


def _load_packs() -> list[dict]:
    if not PACKS_DIR.exists():
        return []
    rows: list[dict] = []
    for pack_dir in sorted(PACKS_DIR.iterdir()):
        if not pack_dir.is_dir():
            continue
        metadata_path = pack_dir / "metadata.yaml"
        if not metadata_path.exists():
            continue
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        for attestation in metadata.get("compliance_attestations", []) or [{}]:
            rows.append(
                {
                    "pack_name": metadata.get("pack_name", pack_dir.name),
                    "pack_version": metadata.get("pack_version", "?"),
                    "synthesis_mode": metadata.get("synthesis_mode", "?"),
                    "fairness_required": metadata.get("fairness_methods_required", False),
                    "framework": attestation.get("name", "—"),
                    "attestation_status": attestation.get("status", "—"),
                    "last_reviewed": attestation.get("last_reviewed", "—"),
                }
            )
    return rows


def _designed_ceiling(message: str) -> None:
    st.info(
        f":warning: **Designed Ceiling.** {message}  \n\n"
        "_Per Article Zero, this pane declares its own incompleteness "
        "rather than fabricating MLOps data._"
    )


# ----------------------------------------------------------- Pane 1: Drift

def render_drift() -> None:
    st.subheader("Drift monitors")
    st.markdown(
        "When live, this pane shows time-series of detection rate, "
        "false-positive rate, and accuracy gap **per FrictionBench cell** "
        "(signature × screen) across recent runs. Cells outside their declared "
        "confidence band fire a drift alert."
    )
    _designed_ceiling(
        "No analytics layer ships in v1; FrictionBench has not yet been run "
        "against live data. Drift data appears once **PULSE-93** lands and "
        "FrictionBench begins emitting per-cell scoring runs on a schedule. "
        "12 cells today: 3 signatures × 4 friction-target screens."
    )

    st.markdown("**Signatures (v1):**")
    st.markdown(
        "- `dwell_after_error`\n"
        "- `multi_back_press`\n"
        "- `abandon_before_submit`"
    )
    st.markdown("**Friction-target screens (v1):**")
    st.markdown(
        "- `loans.apply.step3`\n"
        "- `international.beneficiary.setup`\n"
        "- `cards.credit.apply.eligibility`\n"
        "- `investments.premier.portfolio.overview`"
    )


# ---------------------------------------------------- Pane 2: Fairness re-check

def render_fairness() -> None:
    st.subheader("Fairness re-check registry")
    methods = _load_methods()
    if not methods:
        st.error(f"Could not load convergence registry at {METHODS_PATH}.")
        return

    st.caption(
        "Registry version: "
        f"`{methods.get('version', '?')}` "
        f"(source: `pulse/convergence/methods.yaml`)"
    )

    st.markdown("#### Statistical-power methods")
    stat = methods.get("categories", {}).get("statistical_power", {})
    st.caption(stat.get("description", ""))
    for name, body in stat.get("methods", {}).items():
        with st.container(border=True):
            st.markdown(f"**`{name}`**")
            st.markdown(f"_Applies to:_ {', '.join(body.get('applies_to', []))}")
            st.markdown(f"_Notes:_ {body.get('notes', '').strip()}")

    st.markdown("#### Fairness-aware methods")
    fair = methods.get("categories", {}).get("fairness_aware", {})
    st.caption(fair.get("description", ""))
    for name, body in fair.get("methods", {}).items():
        with st.container(border=True):
            st.markdown(f"**`{name}`**")
            st.markdown(f"_Applies to:_ {', '.join(body.get('applies_to', []))}")
            st.markdown(f"_Notes:_ {body.get('notes', '').strip()}")

    st.markdown("#### Per-question-class fairness method (v1)")
    mapping = methods.get("example_fairness_method_per_question_class", {})
    st.table(
        [
            {"question_class": k, "fairness_method": v}
            for k, v in mapping.items()
        ]
    )

    _designed_ceiling(
        "Live re-checks (running each registered fairness method over recent "
        "investigation outputs and surfacing deviations) require the analytics "
        "layer + a stream of investigation results. Blocked on **PULSE-93**."
    )


# -------------------------------------------------- Pane 3: Lineage verifier

LINEAGE_EXAMPLE = """\
[
  {
    "lineage_id": "L0001",
    "prev_row_hash": "0" * 64,
    "operation": "ingest",
    "inputs": ["taq:batch:2026-05-17"],
    "artifact_hash": "<sha256 of artefact>"
  }
]
"""


def render_lineage() -> None:
    st.subheader("Lineage verifier")
    st.markdown(
        "Paste lineage rows as JSON (array of objects). Calls "
        "`pulse.lineage.verifier.verify_chain` on the input — same code "
        "path as the Platform API's `POST /lineage/verify`."
    )
    rows_json = st.text_area(
        "Lineage rows (JSON array)",
        value="[]",
        height=200,
        help="Paste an array of lineage row objects in chain order.",
    )
    if st.button("Verify"):
        try:
            rows = json.loads(rows_json)
            if not isinstance(rows, list):
                raise ValueError("Top-level JSON must be an array of objects.")
        except (json.JSONDecodeError, ValueError) as exc:
            st.error(f"Invalid JSON: {exc}")
            return

        report = verify_chain(rows)
        if report.ok:
            st.success(
                f"Chain OK. {report.total_rows} rows verified. "
                f"Last lineage_id: `{report.last_lineage_id or '—'}`."
            )
        else:
            st.error(
                f"Chain has {len(report.violations)} violation(s) "
                f"across {report.total_rows} rows."
            )
            st.table(
                [
                    {
                        "kind": v.kind,
                        "lineage_id": v.lineage_id,
                        "expected": v.expected,
                        "actual": v.actual,
                    }
                    for v in report.violations
                ]
            )

    with st.expander("Example row shape"):
        st.code(LINEAGE_EXAMPLE, language="json")


# --------------------------------- Pane 4: Synthesis-mode governance

def render_governance() -> None:
    st.subheader("Synthesis-mode governance")
    rows = _load_packs()
    if not rows:
        st.warning("No packs registered.")
    else:
        st.table(rows)

    st.markdown("**Declared synthesis modes (engine-side):**")
    st.markdown(", ".join(f"`{m.value}`" for m in SynthesisMode))
    st.caption(
        "Only `deterministic` has a registered provider in v1. Packs "
        "declaring `llm_augmented` fail to resolve at engine startup. "
        "Enabling LLM augmentation is a deliberate ship + governance "
        "review, not a config toggle. See `pulse/synthesis/SYNTHESIS_DESIGN.md`."
    )

    _designed_ceiling(
        "Every drift alert + fairness deviation in v1 ships with a "
        "deterministic **narrative paragraph** "
        "(*\"what changed, for whom, with what evidence, recommended "
        "response\"*) generated via `TemplateSynthesisProvider`. This is "
        "the alert-fatigue mitigation from the HOL-6 panel. Pending "
        "PULSE-93 — synthesis layer is interface-only today."
    )


# ----------------------------------------------------------------- Entry

def main() -> None:
    st.set_page_config(page_title="Pulse MLOps Console", layout="wide")
    st.title("Pulse — MLOps Console")
    st.caption(
        f"Engine: `{_pulse_version()}` · Procurement-gate surface for live "
        "bank deployment · Read-only at v0."
    )

    drift, fairness, lineage, governance = st.tabs(
        ["Drift", "Fairness re-check", "Lineage verifier", "Synthesis-mode governance"]
    )

    with drift:
        render_drift()
    with fairness:
        render_fairness()
    with lineage:
        render_lineage()
    with governance:
        render_governance()


if __name__ == "__main__":
    main()
