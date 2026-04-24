"""
mil/publish/adapters.py — MIL-35 PublishAdapter

Abstracts the mechanics of pushing briefing HTML to its destination.
Clone operators swap adapters by editing mil/config/publish_config.yaml
instead of modifying publisher code.

Adapters:
  GitHubPagesAdapter(repo_url, token, branch, commit_subject_fmt, ...)
  LocalAdapter(root_dir)        — writes to a filesystem path
  NullAdapter                   — no-op, useful for dry runs

Contract:
  adapter.publish(relative_path, content) -> (ok: bool, message: str)
    relative_path  e.g. "briefing-v4/index.html"
    content        full HTML string
    ok=True        push succeeded (or nothing to commit)
    message        commit subject / destination path / error description

Credentials are read from .env (not publish_config.yaml) — we don't want
GITHUB_TOKEN in a committed config file. YAML holds adapter choice +
non-secret settings only.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_MIL_ROOT    = Path(__file__).parent.parent
_REPO_ROOT   = _MIL_ROOT.parent
_CONFIG_PATH = _MIL_ROOT / "config" / "publish_config.yaml"
_DEFAULT_COMMIT_SUBJECT = "publish: {path} {ts}"


# ── LF-safe writes ────────────────────────────────────────────────────────────

def write_text_lf(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text with LF-only line endings — byte-stable across OS.

    Default `Path.write_text` on Windows translates \\n → \\r\\n (platform
    default text mode), producing files whose bytes drift from what GitHub
    Pages actually serves (it normalises to LF). Every publisher that
    writes a local copy of briefing HTML MUST use this helper so
    `sha256sum local == sha256sum remote` holds, which is the only
    reliable audit signal that "what we pushed is what's served."

    Also strips any pre-existing \\r to handle content that was built
    from mixed-newline sources (templates, f-strings concatenating
    external text).
    """
    normalised = content.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(normalised, encoding=encoding, newline="\n")


# ── Base ──────────────────────────────────────────────────────────────────────

class PublishAdapter(ABC):
    @abstractmethod
    def publish(self, relative_path: str, content: str) -> tuple[bool, str]:
        """Publish `content` at `relative_path`. Returns (ok, message)."""


# ── Null (no-op) ──────────────────────────────────────────────────────────────

class NullAdapter(PublishAdapter):
    def publish(self, relative_path: str, content: str) -> tuple[bool, str]:
        logger.info("[publish] NullAdapter — would publish %d bytes to %s",
                    len(content), relative_path)
        return True, f"null: {relative_path} ({len(content)} bytes)"


# ── Local filesystem ──────────────────────────────────────────────────────────

class LocalAdapter(PublishAdapter):
    def __init__(self, root_dir: str | Path):
        self.root = Path(root_dir).expanduser().resolve()

    def publish(self, relative_path: str, content: str) -> tuple[bool, str]:
        dest = self.root / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        write_text_lf(dest, content)
        logger.info("[publish] LocalAdapter wrote %d bytes to %s",
                    len(content), dest)
        return True, f"local: {dest}"


# ── GitHub Pages ──────────────────────────────────────────────────────────────

class GitHubPagesAdapter(PublishAdapter):
    """Clone, write, commit, push. Shallow clone (depth=1) of the target branch."""
    def __init__(self, repo_url: str, token: str,
                 branch: str = "main",
                 commit_subject_fmt: str = _DEFAULT_COMMIT_SUBJECT,
                 committer_email: str = "sonar-publish@cjipro.com",
                 committer_name: str  = "Sonar Publisher"):
        if not repo_url:
            raise ValueError("GitHubPagesAdapter: repo_url is required")
        if not token:
            raise ValueError("GitHubPagesAdapter: token is required")
        self._repo_url = repo_url
        self._token    = token
        self._branch   = branch
        self._msg_fmt  = commit_subject_fmt
        self._email    = committer_email
        self._name     = committer_name

    def _auth_url(self) -> str:
        if self._repo_url.startswith("https://"):
            return self._repo_url.replace("https://", f"https://{self._token}@")
        slug = self._repo_url.rstrip("/")
        if not slug.endswith(".git"):
            slug += ".git"
        return f"https://{self._token}@github.com/{slug}"

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, "***") if text else text

    def publish(self, relative_path: str, content: str) -> tuple[bool, str]:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        commit_msg = self._msg_fmt.format(path=relative_path, ts=ts)

        with tempfile.TemporaryDirectory() as tmpdir:
            clone_dir = Path(tmpdir) / "pages_repo"

            logger.info("[publish] cloning %s (branch=%s)", self._repo_url, self._branch)
            r = subprocess.run(
                ["git", "clone", "--depth=1", "--branch", self._branch,
                 self._auth_url(), str(clone_dir)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode != 0:
                return False, f"git clone failed: {self._scrub(r.stderr.strip())}"

            dest = clone_dir / relative_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            write_text_lf(dest, content)

            for cmd in (
                ["git", "-C", str(clone_dir), "config", "user.email", self._email],
                ["git", "-C", str(clone_dir), "config", "user.name",  self._name],
            ):
                subprocess.run(cmd, capture_output=True)

            r = subprocess.run(
                ["git", "-C", str(clone_dir), "add", relative_path],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                return False, f"git add failed: {r.stderr.strip()}"

            r = subprocess.run(
                ["git", "-C", str(clone_dir), "commit", "-m", commit_msg],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                combined = (r.stderr + r.stdout).strip()
                if "nothing to commit" in combined:
                    return True, f"nothing to commit — {relative_path} up to date"
                return False, f"git commit failed: {combined}"

            r = subprocess.run(
                ["git", "-C", str(clone_dir), "push", "origin", self._branch],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode != 0:
                return False, f"git push failed: {self._scrub(r.stderr.strip())}"

        return True, commit_msg


# ── Config + .env loading ────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {"adapter": "null"}
    loaded = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {"adapter": "null"}


def _load_env() -> dict:
    """Read .env + os.environ (.env loses to os.environ only for keys env sets)."""
    env: dict[str, str] = {}
    env_path = _REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    env.update({k: v for k, v in os.environ.items() if k not in env})
    return env


# ── Factory ───────────────────────────────────────────────────────────────────

def get_adapter(override_config: dict | None = None) -> PublishAdapter:
    """Load publish_config.yaml (or override_config) and construct the adapter."""
    cfg = override_config if override_config is not None else _load_config()
    adapter_type = (cfg.get("adapter") or "null").lower()

    if adapter_type == "github_pages":
        env       = _load_env()
        token     = env.get("GITHUB_TOKEN", "")
        repo_url  = env.get("PUBLISH_REPO", "")
        if not token or not repo_url:
            logger.warning("[publish] github_pages selected but GITHUB_TOKEN/PUBLISH_REPO "
                           "missing in .env — falling back to NullAdapter")
            return NullAdapter()
        gh = cfg.get("github_pages", {}) or {}
        return GitHubPagesAdapter(
            repo_url           = repo_url,
            token              = token,
            branch             = gh.get("branch", "main"),
            commit_subject_fmt = gh.get("commit_subject", _DEFAULT_COMMIT_SUBJECT),
            committer_email    = gh.get("committer_email", "sonar-publish@cjipro.com"),
            committer_name     = gh.get("committer_name", "Sonar Publisher"),
        )

    if adapter_type == "local":
        local = cfg.get("local", {}) or {}
        root  = local.get("root_dir", "./published")
        return LocalAdapter(root)

    return NullAdapter()


# ── CLI: self-test ───────────────────────────────────────────────────────────

def _selftest() -> int:
    """Run NullAdapter + LocalAdapter smoke tests. Skips GitHubPagesAdapter (network)."""
    print("[MIL-35] adapter self-test")
    failures = 0

    # 1. NullAdapter
    ok, msg = NullAdapter().publish("briefing-test/index.html", "<html></html>")
    status = "PASS" if (ok and "null" in msg) else "FAIL"
    print(f"  [{status}] NullAdapter -> ok={ok} msg={msg!r}")
    if status == "FAIL":
        failures += 1

    # 2. LocalAdapter -> tempdir
    with tempfile.TemporaryDirectory() as td:
        la = LocalAdapter(td)
        ok, msg = la.publish("nested/index.html", "<html>hi</html>")
        dest = Path(td) / "nested" / "index.html"
        ok_full = ok and dest.exists() and dest.read_text(encoding="utf-8") == "<html>hi</html>"
        status = "PASS" if ok_full else "FAIL"
        print(f"  [{status}] LocalAdapter -> ok={ok} file={dest}")
        if status == "FAIL":
            failures += 1

    # 3. Factory with override config
    adapter = get_adapter({"adapter": "null"})
    status = "PASS" if isinstance(adapter, NullAdapter) else "FAIL"
    print(f"  [{status}] get_adapter(null) -> {type(adapter).__name__}")
    if status == "FAIL":
        failures += 1

    with tempfile.TemporaryDirectory() as td:
        adapter = get_adapter({"adapter": "local", "local": {"root_dir": td}})
        status = "PASS" if isinstance(adapter, LocalAdapter) else "FAIL"
        print(f"  [{status}] get_adapter(local) -> {type(adapter).__name__}")
        if status == "FAIL":
            failures += 1

    # 4. Factory with missing github creds -> NullAdapter fallback
    adapter = get_adapter({"adapter": "github_pages", "github_pages": {}})
    # only guaranteed to fall back if no GITHUB_TOKEN/PUBLISH_REPO in env
    if not (_load_env().get("GITHUB_TOKEN") and _load_env().get("PUBLISH_REPO")):
        status = "PASS" if isinstance(adapter, NullAdapter) else "FAIL"
        print(f"  [{status}] get_adapter(github_pages, no creds) -> {type(adapter).__name__}")
        if status == "FAIL":
            failures += 1
    else:
        print(f"  [SKIP] github_pages fallback (creds present) -> {type(adapter).__name__}")

    if failures:
        print(f"\n  [FAIL] {failures} test(s) failed")
        return 1
    print("\n  [OK] all self-tests pass")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
