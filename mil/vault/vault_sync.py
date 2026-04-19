"""
vault_sync.py -- MIL Vault -> HDFS 9871 anchor script.

Reads enriched signal files from mil/data/historical/enriched/
Pushes each file to /user/mil/enriched/ on MIL HDFS (Port 9871).
Marks records as VAULTED once HDFS write succeeds.

Vault chain (per handover ARCH-001):
  1. Polars transformation        ← done during harvest/enrichment
  2. Refuel-8B enrichment         ← done in qwen_enrichment.py (Refuel model)
  3. DuckDB analytical cache      ← mil_vault.db
  4. HDFS Port 9871 anchoring     ← THIS SCRIPT (clears UNANCHORED status)

MIL Import Rule: no imports from pulse/, poc/, app/, dags/
Zero Entanglement: connects to Port 9871 only.
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

# Only MIL-internal import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from mil.vault.backends import get_backend  # MIL-36 — backend-agnostic anchoring

logger = logging.getLogger(__name__)

MIL_ROOT = Path(__file__).parent.parent
ENRICHED_DIR = MIL_ROOT / "data" / "historical" / "enriched"
VAULT_DB = Path(__file__).parent / "mil_vault.db"

ANCHOR_STATUS_TABLE = "vault_anchor_log"


def _ensure_anchor_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {ANCHOR_STATUS_TABLE} (
            file_name   VARCHAR PRIMARY KEY,
            source      VARCHAR,
            competitor  VARCHAR,
            record_count INTEGER,
            model       VARCHAR,
            hdfs_path   VARCHAR,
            anchored_at TIMESTAMP,
            status      VARCHAR   -- VAULTED | UNANCHORED | FAILED
        )
    """)


def _needs_vault(
    con: duckdb.DuckDBPyConnection,
    file_name: str,
    current_record_count: int,
    current_model: str,
) -> bool:
    """
    Returns True if the file needs vaulting:
    - Never vaulted before
    - Previously failed
    - Record count changed since last vault (new records added)
    - Model changed since last vault (e.g. Refuel -> Haiku v3)
    """
    row = con.execute(
        f"SELECT status, record_count, model FROM {ANCHOR_STATUS_TABLE} WHERE file_name = ?",
        [file_name],
    ).fetchone()
    if row is None:
        return True  # never seen
    status, vaulted_count, vaulted_model = row
    if status != "VAULTED":
        return True  # previous attempt failed
    if vaulted_count != current_record_count:
        return True  # new records appended
    if vaulted_model != current_model:
        return True  # enrichment model upgraded
    return False  # already vaulted and unchanged


def _upsert_status(
    con: duckdb.DuckDBPyConnection,
    file_name: str,
    source: str,
    competitor: str,
    record_count: int,
    model: str,
    hdfs_path: str,
    status: str,
) -> None:
    con.execute(f"""
        INSERT OR REPLACE INTO {ANCHOR_STATUS_TABLE}
            (file_name, source, competitor, record_count, model, hdfs_path, anchored_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [file_name, source, competitor, record_count, model, hdfs_path,
          datetime.now(timezone.utc), status])


def sync_to_hdfs(dry_run: bool = False) -> dict:
    """
    Push all enriched files to HDFS /user/mil/enriched/.
    Returns summary: {file_name: "VAULTED" | "SKIPPED" | "FAILED" | "DRY_RUN"}.

    dry_run=True: check HDFS availability and log what would be synced, no writes.
    """
    client = get_backend()  # MIL-36 — selected by mil/config/vault_config.yaml
    if not client.is_available():
        logger.error(
            "[VaultSync] Vault backend unavailable (backend=%s). "
            "For HDFS: ensure mil-namenode is running (docker compose up -d mil-namenode mil-datanode). "
            "For local: check root_dir exists in vault_config.yaml.",
            type(client).__name__,
        )
        return {"error": f"Vault backend unavailable ({type(client).__name__})"}

    con = duckdb.connect(str(VAULT_DB))
    _ensure_anchor_table(con)

    enriched_files = sorted(ENRICHED_DIR.glob("*.json"))
    if not enriched_files:
        logger.warning("[VaultSync] No enriched files found in %s", ENRICHED_DIR)
        return {"warning": "No enriched files found"}

    summary = {}
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    for enriched_file in enriched_files:
        fname = enriched_file.name

        try:
            payload = json.loads(enriched_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("[VaultSync] %s --read failed: %s", fname, exc)
            summary[fname] = "FAILED"
            continue

        source = payload.get("source", "unknown")
        competitor = payload.get("competitor", "unknown")
        record_count = payload.get("enriched_count", len(payload.get("records", [])))
        model = payload.get("model", "unknown")

        # Skip decommissioned qwen2.5 model files only
        # qwen3:14b is approved for YouTube enrichment (ARCH-002)
        if "qwen2.5" in model.lower():
            logger.warning(
                "[VaultSync] %s --enriched with DECOMMISSIONED model '%s'. Skipping.",
                fname, model,
            )
            summary[fname] = "SKIPPED_WRONG_MODEL"
            continue

        if not _needs_vault(con, fname, record_count, model):
            logger.info("[VaultSync] %s --already VAULTED and unchanged, skipping", fname)
            summary[fname] = "SKIPPED"
            continue

        hdfs_path = f"/user/mil/enriched/{source}_{competitor}_{timestamp}.json"

        if dry_run:
            logger.info("[VaultSync] DRY RUN -- would write %s -> %s (%d records, %s)",
                        fname, hdfs_path, record_count, model)
            summary[fname] = "DRY_RUN"
            continue

        ok = client.write_json(hdfs_path, payload)
        if ok:
            _upsert_status(con, fname, source, competitor, record_count, model, hdfs_path, "VAULTED")
            logger.info("[VaultSync] %s --VAULTED ->%s", fname, hdfs_path)
            summary[fname] = "VAULTED"
        else:
            _upsert_status(con, fname, source, competitor, record_count, model, hdfs_path, "FAILED")
            logger.error("[VaultSync] %s --HDFS write FAILED", fname)
            summary[fname] = "FAILED"

    con.close()
    return summary


def report_anchor_status() -> None:
    """Print current anchor status from DuckDB log."""
    if not VAULT_DB.exists():
        print("Vault DB not initialised.")
        return
    con = duckdb.connect(str(VAULT_DB), read_only=True)
    try:
        rows = con.execute(
            f"SELECT file_name, status, record_count, model, anchored_at FROM {ANCHOR_STATUS_TABLE} ORDER BY anchored_at"
        ).fetchall()
    except Exception:
        print("Anchor log table not yet created.")
        con.close()
        return
    con.close()

    if not rows:
        print("No anchor records. Run vault_sync.py to anchor records.")
        return

    print(f"\n{'FILE':<45} {'STATUS':<22} {'RECORDS':>7} {'MODEL':<30} {'ANCHORED_AT'}")
    print("-" * 130)
    for file_name, status, record_count, model, anchored_at in rows:
        print(f"{file_name:<45} {status:<22} {record_count:>7} {model:<30} {anchored_at}")
    print()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    import argparse
    parser = argparse.ArgumentParser(description="MIL Vault ->HDFS 9871 anchor sync")
    parser.add_argument("--dry-run", action="store_true", help="Check availability and log without writing")
    parser.add_argument("--status", action="store_true", help="Show current anchor status and exit")
    args = parser.parse_args()

    if args.status:
        report_anchor_status()
        sys.exit(0)

    logger.info("MIL Vault Sync --%s", "DRY RUN" if args.dry_run else "LIVE")
    result = sync_to_hdfs(dry_run=args.dry_run)

    if "error" in result:
        print(f"\nFATAL: {result['error']}")
        sys.exit(1)

    print("\n=== VAULT SYNC RESULTS ===")
    counts = {}
    for fname, status in result.items():
        counts[status] = counts.get(status, 0) + 1
        print(f"  {status:<22} {fname}")

    print("\nSummary:")
    for status, n in sorted(counts.items()):
        print(f"  {status}: {n}")
    print()
