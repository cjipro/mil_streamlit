"""HOL-83 — surface reframe: Decisions / Intelligence / Verification + de-MLOps.

Asserts the nav renames (server.py), that the labels render across all three
surfaces, the Verification surface carries the model-deployment boundary line +
reframed pane headers, and that MLOps-platform vocabulary no longer reaches the
rendered interface (the engine stays real ML — this is a vocabulary boundary,
not an engineering retreat).

Run:  python -m pytest holter/tests/test_surface_reframe.py -q
"""

from __future__ import annotations

import holter.server as S
from holter.server import app

_SURFACE_PATHS = ("/", "/workspace", "/mlops")

# MLOps-platform vocabulary that must not appear in the rendered interface.
_BANNED = [
    "MLOps Console", "Approve for prod", "Request retraining",
    "Route to committee", "procurement gate", "SYNTHESIS GOVERNANCE",
    "Pulse Home — what changed",
]


def test_surfaces_renamed():
    assert [label for _, label in S._SURFACES] == [
        "Decisions", "Intelligence", "Verification"]


def test_routes_unchanged():
    # URLs stay stable so ?theme= / ?pack= deep-links survive the rename.
    assert [r for r, _ in S._SURFACES] == ["/", "/workspace", "/mlops"]


def test_nav_renders_new_labels_on_every_surface():
    c = app.test_client()
    for path in _SURFACE_PATHS:
        body = c.get(path).get_data(as_text=True)
        assert ">Decisions</a>" in body
        assert ">Intelligence</a>" in body
        assert ">Verification</a>" in body


def test_verification_surface_has_boundary_line():
    body = app.test_client().get("/mlops").get_data(as_text=True)
    assert "Model-deployment risk sits with the deploying data-science team" in body
    assert "verifies journey findings" in body


def test_verification_pane_headers_reframed():
    body = app.test_client().get("/mlops").get_data(as_text=True)
    for header in ("FINDING RELIABILITY", "JOURNEY FAIRNESS",
                   "FINDING LINEAGE", "SYNTHESIS PROVENANCE"):
        assert header in body


def test_decisions_surface_reframed_masthead():
    body = app.test_client().get("/").get_data(as_text=True)
    assert "Pulse — decisions to make" in body


def test_no_mlops_vocab_in_rendered_surfaces():
    c = app.test_client()
    for path in _SURFACE_PATHS:
        body = c.get(path).get_data(as_text=True)
        for banned in _BANNED:
            assert banned not in body, f"{banned!r} still rendered on {path}"


# ── HOL-87: marquee belongs on Decisions, not Intelligence ──────────────────--

def test_marquee_on_decisions_not_intelligence():
    c = app.test_client()
    decisions = c.get("/").get_data(as_text=True)
    intelligence = c.get("/workspace").get_data(as_text=True)
    assert 'class="holter-ticker"' in decisions        # marquee markup present
    assert 'class="holter-ticker"' not in intelligence  # gone from Workspace


def test_decisions_ships_ticker_css_and_animation():
    body = app.test_client().get("/").get_data(as_text=True)
    assert "holter-ticker-css" in body            # TICKER_CSS style block injected
    assert "holter-ticker-scroll" in body         # the marquee keyframes animation


# ── HOL-86: Row 2 is global chrome; legacy Workspace filters removed ────────--

def test_row2_on_all_three_surfaces():
    c = app.test_client()
    for path in _SURFACE_PATHS:
        body = c.get(path).get_data(as_text=True)
        assert 'class="cji-row2"' in body            # the Row 2 bar
        assert 'id="cji-r2-journey"' in body         # Journey multi-select
        assert 'class="cji-r2-search"' in body       # searchable
        assert 'data-sort="friction"' in body        # Sort toggle
        assert 'data-sort="opportunity"' in body


def test_row2_journey_list_from_taxonomy():
    body = app.test_client().get("/").get_data(as_text=True)
    # Journey checkboxes keyed by taxonomy id (humanised label shown to the user).
    assert 'value="loans"' in body
    assert 'value="international"' in body


def test_row2_subjourney_gated():
    body = app.test_client().get("/").get_data(as_text=True)
    assert "Sub Journey" in body
    assert "cji-r2-soon" in body          # rendered disabled with a "soon" badge


def test_intelligence_product_owner_filters_removed():
    body = app.test_client().get("/workspace").get_data(as_text=True)
    assert 'id="filter-product"' not in body
    assert 'id="filter-owner"' not in body
    assert 'class="holter-filter-strip"' not in body   # the dead filter strip is gone
