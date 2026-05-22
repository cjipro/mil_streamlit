"""Pulse Home — Surface 1 of Holter (the face of Pulse).

**v0 (HOL-4):** three honest cards backed by real engine state.

1. Registered investigation packs — live scan of `pulse/decision_packs/`.
2. Engine status — live read of `pulse.synthesis.SynthesisMode` + installed
   pulse version.
3. Designed Ceiling notice — declares what the feed *will* contain when
   PULSE-93 (engine synthesis impl + content packs) and HOL-5..7 (the
   downstream surfaces) land. No fake cards, no placeholder KPIs.

**v1 (gated on PULSE-93 + Surfaces 4/5):** the real feed
- Flagged signals with recommended investigation templates → Workspace
- Recently completed investigations awaiting review → Workspace
- MLOps alerts → MLOps Console

Negative scope (per HOL-1 lock; verify by absence):
- No navigation menu
- No KPI tiles
- No "your metrics" personalisation
- No trend charts on the home page itself

Run locally with:

    streamlit run holter/home/app.py
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

import streamlit as st
import yaml

from pulse.synthesis.base import SynthesisMode

PACKS_DIR = Path(__file__).resolve().parents[2] / "pulse" / "decision_packs"


def list_registered_packs() -> list[dict]:
    """Scan decision_packs/ for entries with a metadata.yaml."""
    packs: list[dict] = []
    if not PACKS_DIR.exists():
        return packs
    for pack_dir in sorted(PACKS_DIR.iterdir()):
        if not pack_dir.is_dir():
            continue
        metadata_path = pack_dir / "metadata.yaml"
        if not metadata_path.exists():
            continue
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        first_attestation = (metadata.get("compliance_attestations") or [{}])[0]
        packs.append(
            {
                "name": metadata.get("pack_name", pack_dir.name),
                "version": metadata.get("pack_version", "?"),
                "synthesis_mode": metadata.get("synthesis_mode", "?"),
                "attestation_status": first_attestation.get("status", "—"),
                "attestation_framework": first_attestation.get("name", "—"),
            }
        )
    return packs


def pulse_version() -> str:
    """Read installed pulse package version."""
    try:
        return importlib.metadata.version("pulse")
    except importlib.metadata.PackageNotFoundError:
        return "(not installed — run `pip install -e .`)"


def main() -> None:
    st.set_page_config(
        page_title="Pulse Home",
        layout="wide",
    )

    st.title("Pulse")
    st.caption(
        "Evidentiary investigation engine for regulated decisions. "
        "What changed, and what should you look at next."
    )

    # --- Card 1: Registered packs -----------------------------------------
    with st.container(border=True):
        st.subheader("Registered investigation packs")
        packs = list_registered_packs()
        if not packs:
            st.warning("No packs registered.")
        else:
            for pack in packs:
                st.markdown(
                    f"**{pack['name']}** v{pack['version']} — "
                    f"synthesis `{pack['synthesis_mode']}`, "
                    f"attestation: _{pack['attestation_status']}_ "
                    f"({pack['attestation_framework']})"
                )
            st.caption(
                "Open in Workspace: "
                "`panel serve holter/workspace/app.py --show`"
            )

    # --- Card 2: Engine status --------------------------------------------
    with st.container(border=True):
        st.subheader("Engine status")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Pulse version:** `{pulse_version()}`")
        with col2:
            modes = ", ".join(f"`{m.value}`" for m in SynthesisMode)
            st.markdown(f"**Synthesis modes (declared):** {modes}")
        st.caption(
            "Only `deterministic` has a registered provider in v1. Packs "
            "declaring `llm_augmented` fail to resolve by design "
            "(see `pulse/synthesis/SYNTHESIS_DESIGN.md`)."
        )

    # --- Card 3: Designed Ceiling -----------------------------------------
    with st.container(border=True):
        st.subheader("Designed Ceiling")
        st.markdown(
            "The full Pulse Home feed will show:\n\n"
            "1. **Flagged signals** with recommended investigation "
            "templates → Workspace\n"
            "2. **Recently completed investigations** awaiting review "
            "→ Workspace\n"
            "3. **MLOps alerts** → MLOps Console (Surface 4 / HOL-6)\n\n"
            "None of these are live at v0. Signal state, investigation "
            "runner, and MLOps surfaces are blocked on **PULSE-93** plus "
            "the downstream Holter surfaces **HOL-5..7**.\n\n"
            "_Per Article Zero, this surface declares its own "
            "incompleteness rather than fabricating feed content._"
        )


if __name__ == "__main__":
    main()
