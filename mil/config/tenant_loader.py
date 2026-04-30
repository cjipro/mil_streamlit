"""mil/config/tenant_loader.py — typed accessors for tenant.yaml.

A "tenant" is one CJI deployment. tenant.yaml carries everything that
would change between deployments: locale, organisation identity, domains,
URL templates, git committer, harvester contact. Read once per process
via @lru_cache; clear via _load.cache_clear() in tests.

Public API:
    # Locale (MIL-148, schema v1)
    lang()                          -> str
    compliance_notices()            -> tuple[str, ...]
    compliance_notices_html()       -> str

    # Organisation (MIL-119, schema v2)
    organisation_name()             -> str
    organisation_display_name()     -> str
    organisation_contact_email()    -> str

    # Domains (MIL-119, schema v2)
    domain_apex()                   -> str
    domain_app()                    -> str
    domain_login()                  -> str
    domain_admin()                  -> str
    apex_url()                      -> str   # https://<apex>
    app_url()                       -> str
    login_url()                     -> str
    admin_url()                     -> str

    # URL templates (MIL-119, schema v2)
    sonar_briefing_url(slug)        -> str
    fonts_base_url()                -> str

    # Git committer (MIL-119, schema v2)
    git_committer_name()            -> str
    git_committer_email()           -> str

    # Harvester (MIL-119, schema v2)
    harvester_contact_email()       -> str

    # Subjects (MIL-116, schema v2)
    subject_default()               -> str
    subject_default_label()         -> str
    briefing_subject_label()        -> str
    peer_slugs()                    -> tuple[str, ...]
    peer_labels()                   -> tuple[str, ...]
    subject_label_map()             -> dict[str, str]
    all_subject_slugs()             -> tuple[str, ...]    # default + peers

A tenant.yaml at schema_version:1 (locale-only) still loads — every v2
accessor falls back to cjipro.com reference defaults so the engine
behaves identically to pre-MIL-119 if the new sections are absent.
"""
from __future__ import annotations

import html as _html
import logging
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "tenant.yaml"

# ── Defaults ──────────────────────────────────────────────────────────────────
# Every default below is the live cjipro.com value as of MIL-119. They exist
# so a tenant.yaml missing the v2 sections continues to behave identically
# to today. A fork operator should set every one of these in tenant.yaml.

_DEFAULT_LANG = "en-GB"

_DEFAULT_ORG_NAME = "CJI"
_DEFAULT_ORG_DISPLAY_NAME = "CJI Briefing"
_DEFAULT_ORG_CONTACT_EMAIL = "hello@cjipro.com"

_DEFAULT_APEX = "cjipro.com"
_DEFAULT_APP = "app.cjipro.com"
_DEFAULT_LOGIN = "login.cjipro.com"
_DEFAULT_ADMIN = "admin.cjipro.com"

_DEFAULT_SONAR_URL_TEMPLATE = "https://app.cjipro.com/sonar/{slug}/"
_DEFAULT_FONTS_BASE_URL = "https://cjipro.com/fonts"

_DEFAULT_COMMITTER_NAME = "MIL Sonar Publisher"
_DEFAULT_COMMITTER_EMAIL = "sonar-publish@cjipro.com"

_DEFAULT_HARVESTER_CONTACT = "mil@cjipro.com"

_DEFAULT_SUBJECT_SLUG = "barclays"
_DEFAULT_SUBJECT_LABEL = "Barclays"
_DEFAULT_BRIEFING_SUBJECT_LABEL = "Barclays App Experience"
_DEFAULT_PEERS: tuple[tuple[str, str], ...] = (
    ("natwest", "NatWest"),
    ("lloyds",  "Lloyds"),
    ("hsbc",    "HSBC"),
    ("monzo",   "Monzo"),
    ("revolut", "Revolut"),
)


# ── Loading ───────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load() -> dict:
    if not _CONFIG_PATH.exists():
        logger.warning("tenant.yaml not found at %s — falling back to defaults", _CONFIG_PATH)
        return {}
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return raw


def _require_str(val, *, field: str, default: str) -> str:
    """Validate a string field with a default fallback.

    Returns the value, stripped. Falls back to default when val is None or
    an empty string. Raises ValueError when val is the wrong type.
    """
    if val is None:
        return default
    if not isinstance(val, str):
        raise ValueError(f"tenant.yaml {field} must be a string, got {type(val).__name__}")
    s = val.strip()
    return s if s else default


def _require_nonempty_str(val, *, field: str) -> str:
    """Validate a string field that has no fallback — must be non-empty."""
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"tenant.yaml {field} must be a non-empty string")
    return val.strip()


# ── Locale (MIL-148, schema v1) ──────────────────────────────────────────────

def lang() -> str:
    raw = _load()
    val = raw.get("lang") or _DEFAULT_LANG
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"tenant.yaml lang must be a non-empty string, got {val!r}")
    val = val.strip()
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
    notices = compliance_notices()
    if not notices:
        return ""
    parts = [
        f'<p class="compliance-notice-line">{_html.escape(n)}</p>'
        for n in notices
    ]
    return "\n".join(parts)


# ── Organisation (MIL-119, schema v2) ────────────────────────────────────────

def _organisation() -> dict:
    raw = _load()
    org = raw.get("organisation") or {}
    if not isinstance(org, dict):
        raise ValueError(f"tenant.yaml organisation must be a mapping, got {type(org).__name__}")
    return org


def organisation_name() -> str:
    return _require_str(_organisation().get("name"), field="organisation.name", default=_DEFAULT_ORG_NAME)


def organisation_display_name() -> str:
    return _require_str(_organisation().get("display_name"), field="organisation.display_name", default=_DEFAULT_ORG_DISPLAY_NAME)


def organisation_contact_email() -> str:
    return _require_str(_organisation().get("contact_email"), field="organisation.contact_email", default=_DEFAULT_ORG_CONTACT_EMAIL)


# ── Domains (MIL-119, schema v2) ─────────────────────────────────────────────

def _domains() -> dict:
    raw = _load()
    d = raw.get("domains") or {}
    if not isinstance(d, dict):
        raise ValueError(f"tenant.yaml domains must be a mapping, got {type(d).__name__}")
    return d


def _validate_domain(val: str, field: str) -> str:
    """Reject schemes — these fields are bare hostnames, not URLs."""
    if "://" in val:
        raise ValueError(f"tenant.yaml {field} must be a bare hostname (no scheme), got {val!r}")
    if "/" in val:
        raise ValueError(f"tenant.yaml {field} must be a bare hostname (no path), got {val!r}")
    return val


def domain_apex() -> str:
    val = _require_str(_domains().get("apex"), field="domains.apex", default=_DEFAULT_APEX)
    return _validate_domain(val, "domains.apex")


def domain_app() -> str:
    val = _require_str(_domains().get("app"), field="domains.app", default=_DEFAULT_APP)
    return _validate_domain(val, "domains.app")


def domain_login() -> str:
    val = _require_str(_domains().get("login"), field="domains.login", default=_DEFAULT_LOGIN)
    return _validate_domain(val, "domains.login")


def domain_admin() -> str:
    val = _require_str(_domains().get("admin"), field="domains.admin", default=_DEFAULT_ADMIN)
    return _validate_domain(val, "domains.admin")


def apex_url() -> str:
    return f"https://{domain_apex()}"


def app_url() -> str:
    return f"https://{domain_app()}"


def login_url() -> str:
    return f"https://{domain_login()}"


def admin_url() -> str:
    return f"https://{domain_admin()}"


# ── URL templates (MIL-119, schema v2) ───────────────────────────────────────

def sonar_briefing_url(slug: str) -> str:
    """Per-firm Sonar PDB URL. {slug} placeholder is substituted with the
    recipient firm's slug from clients.yaml at send time."""
    if not isinstance(slug, str) or not slug.strip():
        raise ValueError(f"sonar_briefing_url requires a non-empty slug, got {slug!r}")
    template = _require_str(
        _load().get("sonar_briefing_url_template"),
        field="sonar_briefing_url_template",
        default=_DEFAULT_SONAR_URL_TEMPLATE,
    )
    if "{slug}" not in template:
        raise ValueError(f"sonar_briefing_url_template must contain {{slug}}, got {template!r}")
    return template.replace("{slug}", slug.strip())


def fonts_base_url() -> str:
    """Absolute URL prefix for the static fonts host. Used by the fonts
    pipeline to generate Worker-side TS modules with absolute @font-face
    URLs (Workers on app./login./admin. cannot resolve relative /fonts/)."""
    val = _require_str(
        _load().get("fonts_base_url"),
        field="fonts_base_url",
        default=_DEFAULT_FONTS_BASE_URL,
    )
    if not val.startswith(("http://", "https://")):
        raise ValueError(f"tenant.yaml fonts_base_url must be an absolute URL, got {val!r}")
    return val.rstrip("/")


# ── Git committer (MIL-119, schema v2) ───────────────────────────────────────

def _git_committer() -> dict:
    raw = _load()
    c = raw.get("git_committer") or {}
    if not isinstance(c, dict):
        raise ValueError(f"tenant.yaml git_committer must be a mapping, got {type(c).__name__}")
    return c


def git_committer_name() -> str:
    return _require_str(_git_committer().get("name"), field="git_committer.name", default=_DEFAULT_COMMITTER_NAME)


def git_committer_email() -> str:
    return _require_str(_git_committer().get("email"), field="git_committer.email", default=_DEFAULT_COMMITTER_EMAIL)


# ── Harvester (MIL-119, schema v2) ───────────────────────────────────────────

def harvester_contact_email() -> str:
    return _require_str(
        _load().get("harvester_contact_email"),
        field="harvester_contact_email",
        default=_DEFAULT_HARVESTER_CONTACT,
    )


# ── Subjects + peers (MIL-116, schema v2) ────────────────────────────────────

_VALID_SLUG_RE = __import__("re").compile(r"^[a-z0-9][a-z0-9-]*$")


def _subjects() -> dict:
    raw = _load()
    s = raw.get("subjects") or {}
    if not isinstance(s, dict):
        raise ValueError(f"tenant.yaml subjects must be a mapping, got {type(s).__name__}")
    return s


def _validate_slug(val: str, *, field: str) -> str:
    """Slugs are lowercase a-z0-9- only, must start with alphanumeric."""
    if not _VALID_SLUG_RE.match(val):
        raise ValueError(f"tenant.yaml {field} must match [a-z0-9][a-z0-9-]*, got {val!r}")
    return val


def subject_default() -> str:
    val = _require_str(_subjects().get("default"), field="subjects.default", default=_DEFAULT_SUBJECT_SLUG)
    return _validate_slug(val, field="subjects.default")


def subject_default_label() -> str:
    return _require_str(_subjects().get("default_label"), field="subjects.default_label", default=_DEFAULT_SUBJECT_LABEL)


def briefing_subject_label() -> str:
    return _require_str(
        _subjects().get("briefing_subject_label"),
        field="subjects.briefing_subject_label",
        default=_DEFAULT_BRIEFING_SUBJECT_LABEL,
    )


def _peer_records() -> tuple[tuple[str, str], ...]:
    """Resolve peer list. Returns tuple of (slug, label) pairs."""
    s = _subjects()
    raw_peers = s.get("peers")
    if raw_peers is None:
        return _DEFAULT_PEERS
    if not isinstance(raw_peers, list):
        raise ValueError(f"tenant.yaml subjects.peers must be a list, got {type(raw_peers).__name__}")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw_peers):
        if not isinstance(entry, dict):
            raise ValueError(f"tenant.yaml subjects.peers[{i}] must be a mapping with slug+label, got {type(entry).__name__}")
        slug = _require_nonempty_str(entry.get("slug"), field=f"subjects.peers[{i}].slug")
        slug = _validate_slug(slug, field=f"subjects.peers[{i}].slug")
        label = _require_nonempty_str(entry.get("label"), field=f"subjects.peers[{i}].label")
        if slug in seen:
            raise ValueError(f"tenant.yaml subjects.peers[{i}] duplicates slug {slug!r}")
        seen.add(slug)
        out.append((slug, label))
    return tuple(out)


def peer_slugs() -> tuple[str, ...]:
    return tuple(slug for slug, _ in _peer_records())


def peer_labels() -> tuple[str, ...]:
    return tuple(label for _, label in _peer_records())


def subject_label_map() -> dict[str, str]:
    """Combined slug→label map covering subject + all peers. Useful when
    building cohort label dicts (replaces per-file COMP_LABELS literals)."""
    out = {subject_default(): subject_default_label()}
    out.update(dict(_peer_records()))
    return out


def all_subject_slugs() -> tuple[str, ...]:
    """Subject default first, then peers in declared order."""
    return (subject_default(),) + peer_slugs()


# ── CLI smoke ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    print("=== Locale ===")
    print(f"  lang:                {lang()!r}")
    print(f"  notices:             {compliance_notices()}")
    print()
    print("=== Organisation ===")
    print(f"  name:                {organisation_name()!r}")
    print(f"  display_name:        {organisation_display_name()!r}")
    print(f"  contact_email:       {organisation_contact_email()!r}")
    print()
    print("=== Domains ===")
    print(f"  apex_url:            {apex_url()}")
    print(f"  app_url:             {app_url()}")
    print(f"  login_url:           {login_url()}")
    print(f"  admin_url:           {admin_url()}")
    print()
    print("=== URLs ===")
    print(f"  sonar (barclays):    {sonar_briefing_url('barclays')}")
    print(f"  fonts_base_url:      {fonts_base_url()}")
    print()
    print("=== Git + harvester ===")
    print(f"  committer:           {git_committer_name()!r} <{git_committer_email()}>")
    print(f"  harvester contact:   {harvester_contact_email()!r}")
    print()
    print("=== Subjects + peers ===")
    print(f"  default:             {subject_default()!r} ({subject_default_label()!r})")
    print(f"  briefing label:      {briefing_subject_label()!r}")
    print(f"  peer slugs:          {peer_slugs()}")
    print(f"  label map:           {subject_label_map()}")
