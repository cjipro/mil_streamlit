"""scripts/clone_doctor.py — MIL-117 fork-clone preflight checker.

Runs a battery of independent checks on a CJI engine clone and prints a
tabular OK / WARN / FAIL report with a remediation hint per failure.

Use it:
    py scripts/clone_doctor.py        # human-readable report
    make doctor                       # same, via the Makefile target

Exit code:
    0 — all checks passed (OK / WARN only)
    1 — at least one FAIL — pipeline will not run cleanly until fixed

Each check is intentionally small and isolated. A failed check does not
block subsequent ones; the doctor reports as much as it can in a single
pass so a fork operator can fix everything at once.
"""
from __future__ import annotations

import importlib
import os
import socket
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

# ── Plumbing ──────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
MIL_ROOT = REPO_ROOT / "mil"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(MIL_ROOT))

LEVEL_OK = "OK"
LEVEL_WARN = "WARN"
LEVEL_FAIL = "FAIL"


@dataclass
class Result:
    level: str
    name: str
    detail: str
    remediation: str = ""


def _ok(name: str, detail: str = "") -> Result:
    return Result(LEVEL_OK, name, detail)


def _warn(name: str, detail: str, remediation: str = "") -> Result:
    return Result(LEVEL_WARN, name, detail, remediation)


def _fail(name: str, detail: str, remediation: str = "") -> Result:
    return Result(LEVEL_FAIL, name, detail, remediation)


# ── Checks ────────────────────────────────────────────────────────────────────

def check_python_version() -> Result:
    major, minor = sys.version_info.major, sys.version_info.minor
    if (major, minor) < (3, 11):
        return _fail(
            "python_version",
            f"Python {major}.{minor} found, 3.11+ required",
            "Install Python 3.11+ from https://python.org/downloads/",
        )
    return _ok("python_version", f"Python {major}.{minor}.{sys.version_info.micro}")


def check_venv_active() -> Result:
    if os.environ.get("VIRTUAL_ENV"):
        return _ok("venv_active", os.environ["VIRTUAL_ENV"])
    return _warn(
        "venv_active",
        "no VIRTUAL_ENV in environment",
        "Run `./bootstrap.sh setup` then `source .venv/Scripts/activate` (Win) or "
        "`source .venv/bin/activate` (Unix). The pipeline will run in system python "
        "but you risk leaking deps across projects.",
    )


def check_required_deps() -> Result:
    """A sample of load-bearing imports — fails fast if a fork forgot pip install."""
    required = {
        "yaml": "pyyaml",
        "anthropic": "anthropic",
        "jinja2": "jinja2",
        "duckdb": "duckdb",
        "plotly": "plotly",
        "json_repair": "json-repair",
        "feedparser": "feedparser",
        "sentence_transformers": "sentence-transformers",
    }
    missing: list[str] = []
    for mod, pkg in required.items():
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        return _fail(
            "required_deps",
            f"missing: {', '.join(missing)}",
            "pip install -r requirements.txt && pip install -r mil/requirements.txt",
        )
    return _ok("required_deps", f"all {len(required)} import")


def check_dotenv_present() -> Result:
    p = REPO_ROOT / ".env"
    if not p.exists():
        return _warn(
            "dotenv_present",
            ".env not found at repo root",
            "cp .env.minimal.example .env (Tier 1) or "
            ".env.publish.example / .env.full.example for higher tiers",
        )
    return _ok("dotenv_present", str(p))


def check_anthropic_api_key() -> Result:
    """The single key that, when missing, most often produces the most
    confusing pipeline failures (Box 3 + commentary fallback prose)."""
    # Read .env if dotenv is loaded; also accept os.environ directly.
    val = os.environ.get("ANTHROPIC_API_KEY") or ""
    if not val:
        # Try .env file directly — a clone may have it in .env but not loaded.
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY=") and "REPLACE-ME" not in line:
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not val or "REPLACE-ME" in val.upper() or "REPLACE_ME" in val.upper():
        return _warn(
            "anthropic_api_key",
            "ANTHROPIC_API_KEY not set or placeholder",
            "Set in .env. Pipeline runs without it but Box 3 exec alert + "
            "commentary degrade to fallback prose.",
        )
    if not val.startswith("sk-ant-"):
        return _warn(
            "anthropic_api_key",
            "ANTHROPIC_API_KEY does not start with sk-ant-",
            "Verify the key — Anthropic API keys all start with sk-ant-",
        )
    return _ok("anthropic_api_key", f"set ({val[:10]}...{val[-4:]})")


def check_tenant_loader() -> Result:
    try:
        from mil.config import tenant_loader as tl
        tl._load.cache_clear()
        # Exercise every accessor — any schema error raises.
        _ = tl.lang()
        _ = tl.organisation_name()
        _ = tl.domain_apex()
        _ = tl.subject_default()
        _ = tl.peer_slugs()
        _ = tl.fonts_base_url()
        return _ok("tenant_loader", f"subject={tl.subject_default()}, apex={tl.domain_apex()}")
    except Exception as exc:
        return _fail(
            "tenant_loader",
            f"{type(exc).__name__}: {exc}",
            "Inspect mil/config/tenant.yaml — see ARCHITECTURE.md for schema",
        )


def check_workos_loader() -> Result:
    try:
        from mil.config import workos_loader as wl
        wl._load.cache_clear()
        env = wl.active_env()
        cid = wl.client_id()
        if not cid and env != "production":
            return _warn(
                "workos_loader",
                f"active_env={env}, client_id unset",
                "Populate mil/config/workos.yaml or set active_env: production "
                "if WorkOS is not in scope",
            )
        return _ok("workos_loader", f"active_env={env}, client_id={'set' if cid else 'null (production)'}")
    except Exception as exc:
        return _fail(
            "workos_loader",
            f"{type(exc).__name__}: {exc}",
            "Inspect mil/config/workos.yaml",
        )


def check_workos_drift() -> Result:
    try:
        from mil.auth.scripts import check_workos_drift as cwd
        drifts = cwd.check_drift()
        if drifts:
            return _fail(
                "workos_drift",
                f"{len(drifts)} drift(s) between workos.yaml and wrangler.toml",
                "py mil/auth/scripts/check_workos_drift.py for details",
            )
        return _ok("workos_drift", "workos.yaml matches all 3 wrangler.toml [vars]")
    except Exception as exc:
        return _warn(
            "workos_drift",
            f"checker errored: {type(exc).__name__}: {exc}",
            "Drift checker requires Python 3.11+ tomllib; verify wrangler.toml shape",
        )


def check_taxonomy_loader() -> Result:
    try:
        from mil.config import taxonomy_loader as tax
        # Best-effort cache clear if the loader follows our pattern
        if hasattr(tax, "_load") and hasattr(tax._load, "cache_clear"):
            tax._load.cache_clear()
        issues = tax.issue_types()
        journeys = tax.customer_journeys()
        if not issues or not journeys:
            return _fail(
                "taxonomy_loader",
                "issue_types or customer_journeys empty",
                "mil/config/domain_taxonomy.yaml is the single source of truth — populate it",
            )
        return _ok("taxonomy_loader", f"{len(issues)} issue types, {len(journeys)} journeys")
    except Exception as exc:
        return _fail(
            "taxonomy_loader",
            f"{type(exc).__name__}: {exc}",
            "Inspect mil/config/domain_taxonomy.yaml + taxonomy_loader.py",
        )


def check_chronicle_corpus() -> Result:
    p = MIL_ROOT / "CHRONICLE.md"
    if not p.exists():
        return _fail(
            "chronicle_corpus",
            f"{p} not found",
            "CHRONICLE is constitutional — every CJI inference traces to an entry. "
            "See CHRONICLE_POLICY.md for the schema and append rules.",
        )
    try:
        from mil.inference.chronicle_loader import load_chronicle_entries
        entries = load_chronicle_entries()
        if len(entries) < 1:
            return _fail(
                "chronicle_corpus",
                f"{len(entries)} entries loaded from CHRONICLE.md",
                "CHRONICLE_POLICY.md describes the entry shape — at minimum one "
                "approved entry must load before inference can run",
            )
        return _ok("chronicle_corpus", f"{len(entries)} CHRONICLE entries loaded")
    except Exception as exc:
        return _fail(
            "chronicle_corpus",
            f"loader raised: {type(exc).__name__}: {exc}",
            "mil/inference/chronicle_loader.py asserts >=15 entries by default — "
            "set MIL_CHRONICLE_MIN_EXPECTED=N to relax for a fork pack",
        )


def check_sample_corpus() -> Result:
    sample_dir = MIL_ROOT / "data" / "sample"
    if not sample_dir.exists():
        return _warn(
            "sample_corpus",
            "mil/data/sample/ not found",
            "Run `py mil/data/sample/generate_sample.py` to (re)generate",
        )
    files = list(sample_dir.glob("*_enriched.json"))
    if not files:
        return _warn(
            "sample_corpus",
            "mil/data/sample/ has no *_enriched.json files",
            "Run `py mil/data/sample/generate_sample.py` to populate",
        )
    return _ok("sample_corpus", f"{len(files)} files available")


def check_enriched_corpus() -> Result:
    enr_dir = MIL_ROOT / "data" / "historical" / "enriched"
    if not enr_dir.exists():
        return _warn(
            "enriched_corpus",
            "mil/data/historical/enriched/ not found",
            "Run `./bootstrap.sh sample` for a synthetic corpus, or "
            "`py run_daily.py` to harvest live data",
        )
    files = list(enr_dir.glob("*_enriched.json"))
    if not files:
        return _warn(
            "enriched_corpus",
            "no enriched files staged",
            "Run `./bootstrap.sh sample` (frozen synthetic corpus) or "
            "`py run_daily.py` (live harvest)",
        )
    return _ok("enriched_corpus", f"{len(files)} enriched files staged")


def check_publish_config() -> Result:
    p = MIL_ROOT / "config" / "publish_config.yaml"
    if not p.exists():
        return _warn(
            "publish_config",
            f"{p} not found",
            "Defaults to NullAdapter — briefings render to mil/publish/output/ only",
        )
    try:
        import yaml
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        adapter = cfg.get("adapter", "null")
        return _ok("publish_config", f"adapter={adapter}")
    except Exception as exc:
        return _fail(
            "publish_config",
            f"YAML parse failed: {exc}",
            "Inspect mil/config/publish_config.yaml — see ARCHITECTURE.md",
        )


def check_run_daily_importable() -> Result:
    """Sanity-check that the pipeline entry point is reachable. Catches
    sys.path / dependency / circular-import problems before run-time."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_daily", REPO_ROOT / "run_daily.py")
        if spec is None or spec.loader is None:
            return _fail("run_daily_importable", "spec_from_file_location returned None", "")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return _ok("run_daily_importable", "import + module exec clean")
    except Exception as exc:
        return _fail(
            "run_daily_importable",
            f"{type(exc).__name__}: {str(exc)[:120]}",
            "Run `pip install -r requirements.txt` then re-run the doctor",
        )


def check_hdfs_namenode() -> Result:
    """Vault step is non-critical — engine works without HDFS. WARN only."""
    host, port = "localhost", 9871
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return _ok("hdfs_namenode", f"reachable on {host}:{port}")
    except OSError:
        return _warn(
            "hdfs_namenode",
            f"{host}:{port} not reachable",
            "docker-compose up -d mil-namenode mil-datanode  (skipped silently if unavailable)",
        )


def check_gitlab_token() -> Result:
    """Optional GitLab read-mirror credential. Skipped silently if .env
    doesn't carry GITLAB_TOKEN — fork operators without a GitLab mirror
    don't need this. When set, verifies the token can reach the API."""
    token = (os.environ.get("GITLAB_TOKEN") or "").strip()
    base = (os.environ.get("GITLAB_BASE_URL") or "").strip()
    pid = (os.environ.get("GITLAB_PROJECT_ID") or "").strip()

    if not token:
        # Try .env file directly
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GITLAB_TOKEN=") and "REPLACE" not in line:
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                if line.startswith("GITLAB_BASE_URL="):
                    base = line.split("=", 1)[1].strip().strip('"').strip("'")
                if line.startswith("GITLAB_PROJECT_ID="):
                    pid = line.split("=", 1)[1].strip().strip('"').strip("'")

    if not token:
        return _ok("gitlab_token", "not configured (GitLab mirror disabled)")

    if not base or not pid:
        return _warn(
            "gitlab_token",
            "GITLAB_TOKEN set but GITLAB_BASE_URL or GITLAB_PROJECT_ID missing",
            "Set both in .env — see .env.full.example",
        )

    # Verify the token reaches the API
    import urllib.request
    import urllib.error
    import json as _json
    try:
        req = urllib.request.Request(
            f"{base.rstrip('/')}/api/v4/projects/{pid}",
            headers={"PRIVATE-TOKEN": token},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            body = _json.loads(r.read().decode("utf-8"))
        return _ok(
            "gitlab_token",
            f"reaches project {body.get('path_with_namespace', pid)}",
        )
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return _fail(
                "gitlab_token",
                "401 Unauthorized — token revoked or invalid",
                "See ops/runbooks/gitlab_token_rotation.md",
            )
        if e.code == 403:
            return _fail(
                "gitlab_token",
                "403 Forbidden — token lacks api scope or Maintainer role",
                "Regenerate with api + write_repository scopes (see ops/runbooks/gitlab_token_rotation.md)",
            )
        return _warn(
            "gitlab_token",
            f"HTTP {e.code} from GitLab API",
            "Check GITLAB_BASE_URL + GITLAB_PROJECT_ID values",
        )
    except (urllib.error.URLError, OSError) as e:
        return _warn(
            "gitlab_token",
            f"network error: {e}",
            "GitLab unreachable from this network — token check skipped",
        )


# ── Runner ────────────────────────────────────────────────────────────────────

CHECKS = [
    check_python_version,
    check_venv_active,
    check_required_deps,
    check_dotenv_present,
    check_anthropic_api_key,
    check_tenant_loader,
    check_workos_loader,
    check_workos_drift,
    check_taxonomy_loader,
    check_chronicle_corpus,
    check_sample_corpus,
    check_enriched_corpus,
    check_publish_config,
    check_run_daily_importable,
    check_hdfs_namenode,
    check_gitlab_token,
]


_LEVEL_TAG = {
    LEVEL_OK:   "[ OK ]",
    LEVEL_WARN: "[WARN]",
    LEVEL_FAIL: "[FAIL]",
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print(f"clone_doctor — preflight check on {REPO_ROOT}")
    print()
    results: list[Result] = []
    for check in CHECKS:
        try:
            results.append(check())
        except Exception:
            tb = traceback.format_exc(limit=2).strip().splitlines()[-1]
            results.append(_fail(check.__name__.replace("check_", ""),
                                 f"check raised: {tb}",
                                 "File a bug — clone_doctor itself should never raise"))

    name_w = max(len(r.name) for r in results)
    for r in results:
        print(f"  {_LEVEL_TAG[r.level]}  {r.name.ljust(name_w)}  {r.detail}")
        if r.remediation and r.level != LEVEL_OK:
            print(f"           {''.ljust(name_w)}  -> {r.remediation}")

    n_ok = sum(1 for r in results if r.level == LEVEL_OK)
    n_warn = sum(1 for r in results if r.level == LEVEL_WARN)
    n_fail = sum(1 for r in results if r.level == LEVEL_FAIL)
    print()
    print(f"  Summary: {n_ok} OK, {n_warn} WARN, {n_fail} FAIL")

    if n_fail > 0:
        print(f"\n  {n_fail} hard failure(s) — pipeline will not run cleanly until fixed.")
        return 1
    if n_warn > 0:
        print(f"\n  {n_warn} warning(s) — pipeline will run but some surfaces will degrade.")
    else:
        print("\n  All checks pass — clean to run `./bootstrap.sh run` or `py run_daily.py`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
