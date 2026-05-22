"""Investigation Workspace — Surface 2 of Holter (the face of Pulse).

**v0 (HOL-3):** renders the example pack's metadata at three altitudes
(Bank / Journey / Signal) with a real lineage anchor (SHA-256 of the pack
metadata file) and an Article-Zero-honest Designed Ceiling notice. No fake
investigation content.

**v1 (gated on PULSE-93):** renders full investigation content once
`pulse/synthesis/base.py::TemplateSynthesisProvider` ships its real Jinja2
implementation and `example_pack/` is populated with analytic outputs +
templates.

Run locally with:

    panel serve holter/workspace/app.py --show
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import panel as pn
import yaml

from holter.shared.altitudes import Altitude

# Pack lives in the sibling pulse/ tree at the repo root.
PACK_PATH = (
    Path(__file__).resolve().parents[2]
    / "pulse"
    / "decision_packs"
    / "example_pack"
    / "metadata.yaml"
)

ENGINE_GAP_NOTICE = """\
**Designed Ceiling.** Investigation content is not yet shipped at v1.
The engine synthesis layer (`pulse/synthesis/base.py`) is interface-only —
`TemplateSynthesisProvider.synthesise` raises `NotImplementedError`. This
surface renders pack metadata + lineage anchor only. Full investigation
rendering ships when **PULSE-93** lands.

Per Article Zero, this surface declares its own incompleteness rather than
fabricating content.
"""


def load_pack(path: Path = PACK_PATH) -> tuple[dict, str, str]:
    """Load pack metadata + compute lineage anchor.

    Returns:
        (metadata_dict, raw_yaml_text, sha256_hex_of_file_bytes)
    """
    raw_bytes = path.read_bytes()
    raw_text = raw_bytes.decode("utf-8")
    metadata = yaml.safe_load(raw_text)
    pack_hash = hashlib.sha256(raw_bytes).hexdigest()
    return metadata, raw_text, pack_hash


def lineage_badge(pack_hash: str) -> pn.pane.Markdown:
    """Render the lineage hash badge — visible on every altitude."""
    short = f"{pack_hash[:12]}…{pack_hash[-4:]}"
    return pn.pane.Markdown(
        f"**Lineage anchor:** `sha256:{short}`  "
        f"_(SHA-256 of pack metadata.yaml; v0 surface — extends to full "
        f"chain when PULSE-93 lands)_",
        styles={
            "background": "#eef",
            "padding": "6px 10px",
            "border-radius": "4px",
            "font-size": "12px",
        },
    )


def render_bank(metadata: dict) -> pn.pane.Markdown:
    """Bank altitude — executive headline, maximum compression."""
    primary = metadata["compliance_attestations"][0]
    return pn.pane.Markdown(
        f"## {metadata['pack_name']} v{metadata['pack_version']}\n\n"
        f"**Status:** {primary['status']} ({primary['name']})  \n"
        f"**Synthesis mode:** `{metadata['synthesis_mode']}`"
    )


def render_journey(metadata: dict) -> pn.pane.Markdown:
    """Journey altitude — full metadata table + description. Default altitude."""
    attestations_rows = "\n".join(
        f"| {a['name']} | {a['status']} | {a['last_reviewed']} |"
        for a in metadata["compliance_attestations"]
    )
    return pn.pane.Markdown(
        f"## {metadata['pack_name']} v{metadata['pack_version']}\n\n"
        f"{metadata.get('description', '').strip()}\n\n"
        f"**Authors:** {', '.join(metadata['authors'])}  \n"
        f"**License:** {metadata['license']}  \n"
        f"**Fairness methods required:** "
        f"`{metadata['fairness_methods_required']}`  \n"
        f"**Required engine:** `{metadata['required_pulse_version']}`  \n"
        f"**Synthesis mode:** `{metadata['synthesis_mode']}`\n\n"
        f"### Compliance attestations\n\n"
        f"| Framework | Status | Last reviewed |\n"
        f"|---|---|---|\n{attestations_rows}\n"
    )


def render_signal(metadata: dict, raw_yaml: str) -> pn.pane.Markdown:
    """Signal altitude — full raw YAML + maintainer notes. Maximum expansion."""
    notes = metadata.get("notes", "_(no notes)_").strip() or "_(no notes)_"
    return pn.pane.Markdown(
        f"## Pack metadata (raw)\n\n"
        f"```yaml\n{raw_yaml.strip()}\n```\n\n"
        f"### Maintainer notes\n\n{notes}"
    )


def build_app() -> pn.template.BootstrapTemplate:
    """Construct the Investigation Workspace template."""
    metadata, raw_yaml, pack_hash = load_pack()

    altitude_radio = pn.widgets.RadioButtonGroup(
        name="Altitude",
        options=[a.value for a in Altitude],
        value=Altitude.JOURNEY.value,
        button_type="default",
    )

    @pn.depends(altitude=altitude_radio)
    def render(altitude: str) -> pn.viewable.Viewable:
        if altitude == Altitude.BANK.value:
            return render_bank(metadata)
        if altitude == Altitude.JOURNEY.value:
            return render_journey(metadata)
        if altitude == Altitude.SIGNAL.value:
            return render_signal(metadata, raw_yaml)
        # Closed enum; should be unreachable.
        raise ValueError(f"Unknown altitude: {altitude}")

    designed_ceiling = pn.pane.Markdown(
        ENGINE_GAP_NOTICE,
        styles={
            "background": "#fff3cd",
            "padding": "10px",
            "border": "1px solid #ffeeba",
            "border-radius": "4px",
        },
    )

    template = pn.template.BootstrapTemplate(
        title="Pulse — Investigation Workspace (HOL-3 v0)",
    )
    template.sidebar.append(pn.pane.Markdown("### Altitude"))
    template.sidebar.append(altitude_radio)
    template.sidebar.append(pn.pane.Markdown("---"))
    template.sidebar.append(
        pn.pane.Markdown(
            "**Same investigation, three renderings.** "
            "Bank = exec headline. Journey = full metadata. Signal = raw."
        )
    )

    template.main.append(designed_ceiling)
    template.main.append(lineage_badge(pack_hash))
    template.main.append(render)

    return template


# `panel serve` imports this module under a `bokeh.*` name. Guard the
# servable() call so `import holter.workspace.app` from tests is side-effect-free.
if __name__.startswith("bokeh"):
    build_app().servable()
