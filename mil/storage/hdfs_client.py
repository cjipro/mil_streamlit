"""
hdfs_client.py — MIL WebHDFS client.

Sovereign storage for MIL. Connects to mil-namenode only.
Never connects to CJI Pulse HDFS (namenode:9870 / port 8020).

MIL HDFS:
  NameNode WebHDFS: http://localhost:9871/webhdfs/v1
  Base path:        /user/mil/

Directory layout:
  /user/mil/signals/                    — live harvest output
  /user/mil/historical/
    app_store/[competitor]/
    google_play/[competitor]/
    reddit/[subreddit]/
    youtube/[competitor]/
  /user/mil/chronicle_evidence/
    CHR-001_tsb_2018/
    CHR-002_lloyds_2025/
    CHR-003_hsbc_2025/
  /user/mil/enriched/                   — Qwen-enriched signals
  /user/mil/findings/                   — mil_findings.json permanent copies

Data classification: public market signals only. No PII. No DPIA required.

Zero Entanglement:
  This client imports nothing from CJI Pulse HDFS config.
  Port 9871 is MIL only. Port 9870 is CJI only. They never cross.
  No shared volumes, no shared configuration, no cross-reads.

Dual-write contract:
  Local write always happens first — it is the fast, working copy.
  HDFS write is the permanent record. HDFS failures are logged
  as warnings but never crash the harvest. Local write is the source
  of truth if HDFS is unavailable.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── MIL HDFS connection — sovereign, never shared with CJI ───
MIL_NAMENODE_HOST = "localhost"
MIL_NAMENODE_WEBHDFS_PORT = 9871
MIL_WEBHDFS_BASE = f"http://{MIL_NAMENODE_HOST}:{MIL_NAMENODE_WEBHDFS_PORT}/webhdfs/v1"

MIL_HDFS_BASE_PATH = "/user/mil"

# Canonical directory structure
MIL_HDFS_DIRS = [
    "/user/mil/signals",
    "/user/mil/historical",
    "/user/mil/historical/app_store",
    "/user/mil/historical/google_play",
    "/user/mil/historical/reddit",
    "/user/mil/historical/youtube",
    "/user/mil/chronicle_evidence",
    "/user/mil/chronicle_evidence/CHR-001_tsb_2018",
    "/user/mil/chronicle_evidence/CHR-002_lloyds_2025",
    "/user/mil/chronicle_evidence/CHR-003_hsbc_2025",
    "/user/mil/enriched",
    "/user/mil/findings",
]

HDFS_TIMEOUT = 10  # seconds — fast fail, don't block harvest


class MILHDFSClient:
    """
    WebHDFS client for MIL sovereign storage.
    All operations are graceful — HDFS unavailability never crashes the harvest.
    """

    def __init__(
        self,
        host: str = MIL_NAMENODE_HOST,
        port: int = MIL_NAMENODE_WEBHDFS_PORT,
        user: str = "root",
    ):
        self.base_url = f"http://{host}:{port}/webhdfs/v1"
        self.user = user
        self._available: Optional[bool] = None  # cached after first check

    def _url(self, hdfs_path: str) -> str:
        return f"{self.base_url}{hdfs_path}"

    def _params(self, op: str, **kwargs) -> dict:
        return {"op": op, "user.name": self.user, **kwargs}

    def is_available(self) -> bool:
        """Check if MIL HDFS NameNode is reachable."""
        if self._available is not None:
            return self._available
        try:
            resp = requests.get(
                self._url("/user/mil"),
                params=self._params("GETFILESTATUS"),
                timeout=HDFS_TIMEOUT,
            )
            self._available = resp.status_code in (200, 404)
        except Exception:
            self._available = False
        if not self._available:
            logger.warning(
                "[MIL HDFS] NameNode not reachable at %s. "
                "HDFS writes will be skipped. Local writes continue.",
                self.base_url,
            )
        return self._available

    def mkdir(self, hdfs_path: str) -> bool:
        """Create directory (and parents) on MIL HDFS."""
        if not self.is_available():
            return False
        try:
            resp = requests.put(
                self._url(hdfs_path),
                params=self._params("MKDIRS"),
                timeout=HDFS_TIMEOUT,
            )
            if resp.status_code == 200:
                return True
            logger.warning("[MIL HDFS] mkdir %s failed: HTTP %s", hdfs_path, resp.status_code)
            return False
        except Exception as exc:
            logger.warning("[MIL HDFS] mkdir %s exception: %s", hdfs_path, exc)
            return False

    def write_json(self, hdfs_path: str, data: object, overwrite: bool = True) -> bool:
        """
        Write JSON-serialisable data to MIL HDFS path.
        Two-step WebHDFS PUT: first to NameNode (redirect), then to DataNode.
        """
        if not self.is_available():
            return False
        try:
            payload = json.dumps(data, indent=2, default=str).encode("utf-8")
            overwrite_str = "true" if overwrite else "false"

            # Step 1: initiate PUT — NameNode returns redirect to DataNode
            resp1 = requests.put(
                self._url(hdfs_path),
                params=self._params("CREATE", overwrite=overwrite_str),
                allow_redirects=False,
                timeout=HDFS_TIMEOUT,
            )

            if resp1.status_code == 307:
                # Step 2: follow redirect to DataNode
                datanode_url = resp1.headers.get("Location")
                resp2 = requests.put(
                    datanode_url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=HDFS_TIMEOUT,
                )
                if resp2.status_code == 201:
                    logger.debug("[MIL HDFS] Written: %s (%d bytes)", hdfs_path, len(payload))
                    return True
                logger.warning("[MIL HDFS] DataNode write %s failed: HTTP %s", hdfs_path, resp2.status_code)
                return False
            else:
                logger.warning("[MIL HDFS] NameNode PUT %s returned HTTP %s (expected 307)", hdfs_path, resp1.status_code)
                return False

        except Exception as exc:
            logger.warning("[MIL HDFS] write_json %s exception: %s", hdfs_path, exc)
            return False

    def read_json(self, hdfs_path: str) -> Optional[object]:
        """Read JSON from MIL HDFS path. Returns None on failure."""
        if not self.is_available():
            return None
        try:
            resp = requests.get(
                self._url(hdfs_path),
                params=self._params("OPEN"),
                allow_redirects=True,
                timeout=HDFS_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning("[MIL HDFS] read_json %s failed: HTTP %s", hdfs_path, resp.status_code)
            return None
        except Exception as exc:
            logger.warning("[MIL HDFS] read_json %s exception: %s", hdfs_path, exc)
            return None

    def exists(self, hdfs_path: str) -> bool:
        """Check if a path exists on MIL HDFS."""
        if not self.is_available():
            return False
        try:
            resp = requests.get(
                self._url(hdfs_path),
                params=self._params("GETFILESTATUS"),
                timeout=HDFS_TIMEOUT,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def list_dir(self, hdfs_path: str) -> list[str]:
        """List files in a MIL HDFS directory. Returns [] on failure."""
        if not self.is_available():
            return []
        try:
            resp = requests.get(
                self._url(hdfs_path),
                params=self._params("LISTSTATUS"),
                timeout=HDFS_TIMEOUT,
            )
            if resp.status_code == 200:
                statuses = resp.json().get("FileStatuses", {}).get("FileStatus", [])
                return [s["pathSuffix"] for s in statuses]
            return []
        except Exception:
            return []

    def bootstrap_directories(self) -> None:
        """Create the canonical MIL directory structure on HDFS."""
        if not self.is_available():
            logger.warning("[MIL HDFS] bootstrap_directories skipped — HDFS not available.")
            return
        for path in MIL_HDFS_DIRS:
            result = self.mkdir(path)
            status = "OK" if result else "FAIL"
            logger.info("[MIL HDFS] mkdir %s — %s", path, status)
        logger.info("[MIL HDFS] Bootstrap complete.")


# ── Module-level singleton ────────────────────────────────────
_client: Optional[MILHDFSClient] = None


def get_client() -> MILHDFSClient:
    """Return the module-level MIL HDFS client singleton."""
    global _client
    if _client is None:
        _client = MILHDFSClient()
    return _client


def dual_write_signals(local_path: Path, signals: list, timestamp: str) -> None:
    """
    Dual-write signal batch to local filesystem AND MIL HDFS.
    Local write is assumed already done. This function handles HDFS.
    HDFS failure is logged as WARNING — does not raise.
    """
    client = get_client()
    hdfs_path = f"/user/mil/signals/signals_{timestamp}.json"
    ok = client.write_json(hdfs_path, signals)
    if ok:
        logger.info("[MIL HDFS] signals written: %s", hdfs_path)
    else:
        logger.warning("[MIL HDFS] signals HDFS write skipped (unavailable): %s", hdfs_path)


def dual_write_findings(local_path: Path, findings: dict, timestamp: str) -> None:
    """
    Dual-write mil_findings to local filesystem AND MIL HDFS.
    """
    client = get_client()
    hdfs_path = f"/user/mil/findings/mil_findings_{timestamp}.json"
    ok = client.write_json(hdfs_path, findings)
    if ok:
        logger.info("[MIL HDFS] findings written: %s", hdfs_path)
    else:
        logger.warning("[MIL HDFS] findings HDFS write skipped (unavailable): %s", hdfs_path)


def dual_write_historical(local_path: Path, data: object, source: str, competitor: str, timestamp: str) -> None:
    """
    Dual-write historical backfill data to MIL HDFS.
    Path: /user/mil/historical/{source}/{competitor}/{timestamp}.json
    """
    client = get_client()
    competitor_slug = competitor.lower().replace(" ", "_")
    hdfs_path = f"/user/mil/historical/{source}/{competitor_slug}/{timestamp}.json"
    ok = client.write_json(hdfs_path, data)
    if ok:
        logger.info("[MIL HDFS] historical written: %s", hdfs_path)
    else:
        logger.warning("[MIL HDFS] historical HDFS write skipped: %s", hdfs_path)
