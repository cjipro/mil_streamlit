"""mil/config/tenant_loader.py — typed accessors for tenant.yaml (MIL-148).

Locale + jurisdiction scaffolding. Read once per process via @lru_cache.

Public API:
    lang()                    -> str            (BCP-47 tag, default "en-GB")
    compliance_notices()      -> tuple[str, ...] (plain text per notice)
    compliance_notices_html() -> str            (rendered <p> block, escaped)
"""
from __future__ import annotations

import html as _html
import logging
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "tenant.yaml"

_DEFAULT_LANG = "en-GB"


@lru_cache(maxsize=1)
def _load() -> dict:
    if not _CONFIG_PATH.exists():
        logger.warning("tenant.yaml not found at %s — falling back to defaults", _CONFIG_PATH)
        return {}
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return raw


def lang() -> str:
    raw = _load()
    val = raw.get("lang") or _DEFAULT_LANG
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"tenant.yaml lang must be a non-empty string, got {val!r}")
    val = val.strip()
    # BCP-47 is permissive but a reasonable shape check stops typos like
    # "en GB" or trailing whitespace from making it through to <html lang>.
    if " " in val:
        raise ValueError(f"tenant.yaml lang must not contain whitespace: {val!r}")
    return val


def compliance_notices() -> tuple[str, ...]:
    raw = _load()
    notices = raw.get("compliance_notices") or []
    if not isinstance(notices, list):
        raise ValueError(f"tenant.yaml compliance_notices must be a list, got {type(notices).__name__}")
    out: list[str] = []
    for n in notices:
        if not isinstance(n, str) or not n.strip():
            raise ValueError("tenant.yaml compliance_notices entries must be non-empty strings")
        out.append(n.strip())
    return tuple(out)


def compliance_notices_html() -> str:
    """Rendered HTML for the .compliance-notice footer slot.

    Returns empty string when no notices configured (slot stays present
    but invisible — zero visual drift). Each notice is escaped via
    html.escape to neutralise tags/quotes; storing raw HTML in the YAML
    is forbidden (see schema doc).
    """
    notices = compliance_notices()
    if not notices:
        return ""
    parts = [
        f'<p class="compliance-notice-line">{_html.escape(n)}</p>'
        for n in notices
    ]
    return "\n".join(parts)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    print(f"lang:     {lang()!r}")
    print(f"notices:  {compliance_notices()}")
    print(f"notices_html:")
    print(compliance_notices_html() or "  (empty)")
