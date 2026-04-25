"""mil/tests/test_publish_deny_list.py — MIL-110 deny-list guard.

Verifies the sensitive-content deny-list in mil/publish/adapters.py:
- Every legitimate publish path used today MUST pass.
- Every sensitive path pattern MUST raise ValueError.

Run: py -m pytest mil/tests/test_publish_deny_list.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make sibling import work whether tests run from repo root or mil/.
_HERE = Path(__file__).resolve().parent
_MIL  = _HERE.parent
sys.path.insert(0, str(_MIL / "publish"))

from adapters import assert_publishable, SENSITIVE_PATH_PATTERNS  # noqa: E402


# ── Paths the publish chain writes today (MUST pass) ─────────────────────────
LEGITIMATE_PATHS = [
    # V1/V2/V3/V4 briefings (publish.py / publish_v2.py / publish_v3.py / publish_v4.py)
    "briefing/index.html",
    "briefing-v2/index.html",
    "briefing-v3/index.html",
    "briefing-v4/index.html",
    # MIL-86 Sonar URLs (publish_v4.py --target-path)
    "sonar/barclays/index.html",
    "sonar/barclays/2026-04-26/index.html",
    "sonar/hsbc/2026-05-01/index.html",     # forward-compat
    # Public site (publish_site.py)
    "index.html",
    "privacy/index.html",
    "robots.txt",
    "sitemap.xml",
    ".well-known/security.txt",
    "security/index.html",
    "security/architecture/index.html",
    "security/standards/index.html",
    "products/reckoner/index.html",
    "products/reckoner/trial/index.html",
    "products/sonar/index.html",
    "products/pulse/index.html",
    "products/lever/index.html",
    "solutions/index.html",
    "research/index.html",
    "research/methodology/index.html",
    "insights/index.html",
    "press/index.html",
    "thank-you/index.html",
    "trust/index.html",
    # MIL-59 login.cjipro.com placeholder (publish_login_site.py)
    "login/index.html",
    "login/wrangler.toml",                  # auto-excluded by wrangler from served assets
    # GitHub Pages bookkeeping
    ".nojekyll",
    "CNAME",
]


# ── Paths that MUST be refused ───────────────────────────────────────────────
SENSITIVE_PATHS = [
    # Auth code and Worker source
    "mil/auth/edge_bouncer/src/index.ts",
    "mil/auth/magic_link/src/callback.ts",
    "mil/auth/app_cjipro/wrangler.toml",
    "mil/auth/COOKIE_SPEC.md",
    # Runbooks
    "ops/runbooks/mil-60_workos_setup.md",
    "ops/runbooks/mil-62_corp_proxy_matrix.md",
    "mil/auth/MIL67_PASSKEYS.md",
    "mil/auth/MIL69_RATE_LIMITING.md",
    "mil/auth/MIL70_SAML.md",
    "mil/auth/MIL71_SCIM.md",
    "mil/auth/MIL72_AUDIT_EXPORT.md",
    # Top-level docs
    "CLAUDE.md",
    "MEMORY.md",
    # Secrets
    ".env",
    ".env.local",
    ".env.publish",
    "secrets.yaml",
    "secrets.json",
    # Pipeline source
    "mil/inference/mil_agent.py",
    "mil/harvester/enrich_sonnet.py",
    "mil/chat/pipeline.py",
    "scripts/check_public_repo_hygiene.py",
    "run_daily.py",
]


@pytest.mark.parametrize("path", LEGITIMATE_PATHS)
def test_legitimate_path_passes(path: str):
    """Every path the publish chain writes today must NOT raise."""
    assert_publishable(path)  # raises on rejection — no assertion needed


@pytest.mark.parametrize("path", SENSITIVE_PATHS)
def test_sensitive_path_rejected(path: str):
    """Every sensitive path must raise ValueError with a descriptive message."""
    with pytest.raises(ValueError) as exc:
        assert_publishable(path)
    assert "refusing to publish sensitive path" in str(exc.value)
    assert path in str(exc.value)


def test_pattern_list_is_non_empty():
    """Sanity: deny-list isn't accidentally emptied by a future edit."""
    assert len(SENSITIVE_PATH_PATTERNS) >= 10


def test_error_message_names_the_module():
    """Error must point operators at the right file for adding new patterns."""
    with pytest.raises(ValueError) as exc:
        assert_publishable("CLAUDE.md")
    assert "mil/publish/adapters.py" in str(exc.value)
