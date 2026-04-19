"""
mil/vault/backends.py — MIL-36 VaultBackend

Abstracts MIL's anchoring storage so Clone operators can vault to their own
sovereign backend (local filesystem, S3, WebHDFS on a different host)
without modifying vault_sync.py. Mirrors the MIL-35 PublishAdapter pattern.

Backends:
  HDFSBackend(host, port, user)   — wraps existing MILHDFSClient (WebHDFS)
  LocalBackend(root_dir)          — writes to a filesystem path
  NullBackend                     — no-op, returns ok; useful for dry runs

Contract (minimal surface matching what vault_sync.py calls):
  backend.is_available() -> bool
  backend.write_json(path, data, overwrite=True) -> bool

Credentials / host info come from mil/config/vault_config.yaml.
Zero Entanglement: no imports from pulse/, poc/, app/, dags/.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_MIL_ROOT    = Path(__file__).parent.parent
_CONFIG_PATH = _MIL_ROOT / "config" / "vault_config.yaml"


# ── Base ──────────────────────────────────────────────────────────────────────

class VaultBackend(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the backend is reachable and ready to accept writes."""

    @abstractmethod
    def write_json(self, path: str, data: object, overwrite: bool = True) -> bool:
        """Write JSON-serialisable `data` to `path`. Returns True on success."""


# ── HDFS (current production) ────────────────────────────────────────────────

class HDFSBackend(VaultBackend):
    """Thin wrapper around MILHDFSClient — preserves today's wire behaviour."""
    def __init__(self, host: str = "mil-namenode", port: int = 9871, user: str = "root"):
        # Import lazily so LocalBackend-only deploys don't pull in the HDFS client.
        from mil.storage.hdfs_client import MILHDFSClient
        self._client = MILHDFSClient(host=host, port=port, user=user)

    def is_available(self) -> bool:
        return self._client.is_available()

    def write_json(self, path: str, data: object, overwrite: bool = True) -> bool:
        return self._client.write_json(path, data, overwrite=overwrite)


# ── Local filesystem ─────────────────────────────────────────────────────────

class LocalBackend(VaultBackend):
    """
    Writes to root_dir/<stripped-path>.
    HDFS-style absolute paths like '/user/mil/enriched/x.json' map to
    root_dir/user/mil/enriched/x.json, so Clone operators can move from
    HDFS to Local without rewriting the paths their pipeline already uses.
    """
    def __init__(self, root_dir: str | Path):
        self.root = Path(root_dir).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def is_available(self) -> bool:
        return self.root.is_dir()

    def write_json(self, path: str, data: object, overwrite: bool = True) -> bool:
        dest = self.root / path.lstrip("/")
        if dest.exists() and not overwrite:
            return False
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            logger.info("[vault] LocalBackend wrote %d bytes to %s",
                        dest.stat().st_size, dest)
            return True
        except Exception as exc:
            logger.warning("[vault] LocalBackend write %s failed: %s", dest, exc)
            return False


# ── Null ─────────────────────────────────────────────────────────────────────

class NullBackend(VaultBackend):
    def is_available(self) -> bool:
        return True

    def write_json(self, path: str, data: object, overwrite: bool = True) -> bool:
        size = len(json.dumps(data, default=str))
        logger.info("[vault] NullBackend — would write %d bytes to %s", size, path)
        return True


# ── Config + factory ─────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {"adapter": "hdfs"}  # preserve pre-MIL-36 default
    loaded = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {"adapter": "hdfs"}


def get_backend(override_config: dict | None = None) -> VaultBackend:
    """Load vault_config.yaml (or override_config) and construct the backend."""
    cfg = override_config if override_config is not None else _load_config()
    backend_type = (cfg.get("adapter") or "hdfs").lower()

    if backend_type == "hdfs":
        h = cfg.get("hdfs", {}) or {}
        return HDFSBackend(
            host = h.get("host", "mil-namenode"),
            port = int(h.get("port", 9871)),
            user = h.get("user", "root"),
        )

    if backend_type == "local":
        l = cfg.get("local", {}) or {}
        root = l.get("root_dir", "./vault")
        return LocalBackend(root)

    return NullBackend()


# ── CLI: self-test ───────────────────────────────────────────────────────────

def _selftest() -> int:
    """Smoke-test NullBackend + LocalBackend + factory. HDFSBackend skipped (needs running NameNode)."""
    import tempfile
    print("[MIL-36] vault backend self-test")
    failures = 0

    # 1. NullBackend
    nb = NullBackend()
    ok_a = nb.is_available()
    ok_w = nb.write_json("/user/mil/test.json", {"x": 1})
    status = "PASS" if (ok_a and ok_w) else "FAIL"
    print(f"  [{status}] NullBackend           is_available={ok_a} write_json={ok_w}")
    if status == "FAIL":
        failures += 1

    # 2. LocalBackend round-trip
    with tempfile.TemporaryDirectory() as td:
        lb = LocalBackend(td)
        ok_a = lb.is_available()
        ok_w = lb.write_json("/user/mil/enriched/sample.json", {"records": [1, 2, 3]})
        dest = Path(td) / "user" / "mil" / "enriched" / "sample.json"
        ok_full = ok_a and ok_w and dest.exists() and json.loads(dest.read_text(encoding="utf-8"))["records"] == [1, 2, 3]
        status = "PASS" if ok_full else "FAIL"
        print(f"  [{status}] LocalBackend          wrote+roundtrip to {dest}")
        if status == "FAIL":
            failures += 1

    # 3. Factory selections
    for cfg, expected_cls in (
        ({"adapter": "null"},                                        NullBackend),
        ({"adapter": "hdfs", "hdfs": {"host": "x", "port": 1}},     HDFSBackend),
    ):
        b = get_backend(cfg)
        status = "PASS" if isinstance(b, expected_cls) else "FAIL"
        print(f"  [{status}] get_backend({cfg['adapter']:6}) -> {type(b).__name__}")
        if status == "FAIL":
            failures += 1

    with tempfile.TemporaryDirectory() as td:
        b = get_backend({"adapter": "local", "local": {"root_dir": td}})
        status = "PASS" if isinstance(b, LocalBackend) else "FAIL"
        print(f"  [{status}] get_backend(local ) -> {type(b).__name__}")
        if status == "FAIL":
            failures += 1

    if failures:
        print(f"\n  [FAIL] {failures} test(s) failed")
        return 1
    print("\n  [OK] all self-tests pass")
    return 0


if __name__ == "__main__":
    import sys
    # Running as a script — put repo root on sys.path so `from mil.storage...`
    # inside HDFSBackend resolves. When imported normally from vault_sync.py,
    # the caller has already set up the path.
    sys.path.insert(0, str(_MIL_ROOT.parent))
    sys.exit(_selftest())
