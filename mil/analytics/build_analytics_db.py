"""
build_analytics_db.py — Populate mil_analytics.db with queryable analytics tables.

Tables:
  findings           — all findings from mil_findings.json (one row per finding)
  benchmark_history  — all entries from issue_persistence_log.jsonl
  daily_runs         — all entries from daily_run_log.jsonl

Run: py mil/analytics/build_analytics_db.py
"""
import json
import logging
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH   = REPO_ROOT / "mil_analytics.db"

FINDINGS_FILE    = REPO_ROOT / "mil/outputs/mil_findings.json"
PERSISTENCE_FILE = REPO_ROOT / "mil/data/issue_persistence_log.jsonl"
RUN_LOG_FILE     = REPO_ROOT / "mil/data/daily_run_log.jsonl"


def load_findings():
    with open(FINDINGS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for f in data.get("findings", []):
        rows.append({
            "finding_id":              f.get("finding_id"),
            "generated_at":            f.get("generated_at"),
            "competitor":              f.get("competitor"),
            "source":                  f.get("source"),
            "journey_id":              f.get("journey_id"),
            "signal_severity":         f.get("signal_severity"),
            "finding_tier":            f.get("finding_tier"),
            "confidence_score":        f.get("confidence_score"),
            "cac_vol_sig":             (f.get("cac_components") or {}).get("vol_sig"),
            "cac_sim_hist":            (f.get("cac_components") or {}).get("sim_hist"),
            "cac_delta_tel":           (f.get("cac_components") or {}).get("delta_tel"),
            "designed_ceiling_reached": f.get("designed_ceiling_reached", False),
            "failure_mode":            f.get("failure_mode"),
            "chronicle_id":            (f.get("provenance") or {}).get("chronicle_id"),
            "chronicle_bank":          (f.get("chronicle_match") or {}).get("bank"),
            "sim_hist_score":          (f.get("chronicle_match") or {}).get("sim_hist_score"),
            "signal_total":            (f.get("signal_counts") or {}).get("total"),
            "signal_p0":               (f.get("signal_counts") or {}).get("P0"),
            "signal_p1":               (f.get("signal_counts") or {}).get("P1"),
            "signal_p2":               (f.get("signal_counts") or {}).get("P2"),
            "human_countersign_status": f.get("human_countersign_status"),
            "is_unanchored":           f.get("is_unanchored", False),
            "finding_summary":         f.get("finding_summary"),
        })
    return rows


def load_benchmark_history():
    rows = []
    with open(PERSISTENCE_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows.append({
                "date":             r.get("date"),
                "issue_type":       r.get("issue_type"),
                "category":         r.get("category"),
                "barclays_rate":    r.get("barclays_rate"),
                "peer_avg_rate":    r.get("peer_avg_rate"),
                "gap_pp":           r.get("gap_pp"),
                "over_indexed":     r.get("over_indexed", False),
                "dominant_severity": r.get("dominant_severity"),
                "days_active":      r.get("days_active"),
                "first_seen":       r.get("first_seen") or None,
            })
    return rows


def load_daily_runs():
    rows = []
    with open(RUN_LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows.append({
                "run":              r.get("run"),
                "date":             r.get("date"),
                "timestamp":        r.get("timestamp"),
                "status":           r.get("status"),
                "new_records":      r.get("new_records"),
                "findings":         r.get("findings"),
                "m1_streak":        r.get("m1_streak"),
                "m1_target":        r.get("m1_target"),
                "m1_done":          r.get("m1_done", False),
                "churn_risk_score": r.get("churn_risk_score"),
                "churn_risk_trend": r.get("churn_risk_trend"),
            })
    return rows


def build(con: duckdb.DuckDBPyConnection):
    con.execute("""
        CREATE OR REPLACE TABLE findings (
            finding_id               VARCHAR PRIMARY KEY,
            generated_at             TIMESTAMPTZ,
            competitor               VARCHAR,
            source                   VARCHAR,
            journey_id               VARCHAR,
            signal_severity          VARCHAR,
            finding_tier             VARCHAR,
            confidence_score         DOUBLE,
            cac_vol_sig              DOUBLE,
            cac_sim_hist             DOUBLE,
            cac_delta_tel            DOUBLE,
            designed_ceiling_reached BOOLEAN,
            failure_mode             VARCHAR,
            chronicle_id             VARCHAR,
            chronicle_bank           VARCHAR,
            sim_hist_score           DOUBLE,
            signal_total             INTEGER,
            signal_p0                INTEGER,
            signal_p1                INTEGER,
            signal_p2                INTEGER,
            human_countersign_status VARCHAR,
            is_unanchored            BOOLEAN,
            finding_summary          VARCHAR
        )
    """)

    con.execute("""
        CREATE OR REPLACE TABLE benchmark_history (
            date             DATE,
            issue_type       VARCHAR,
            category         VARCHAR,
            barclays_rate    DOUBLE,
            peer_avg_rate    DOUBLE,
            gap_pp           DOUBLE,
            over_indexed     BOOLEAN,
            dominant_severity VARCHAR,
            days_active      INTEGER,
            first_seen       DATE,
            PRIMARY KEY (date, issue_type)
        )
    """)

    con.execute("""
        CREATE OR REPLACE TABLE daily_runs (
            run              INTEGER PRIMARY KEY,
            date             DATE,
            timestamp        TIMESTAMPTZ,
            status           VARCHAR,
            new_records      INTEGER,
            findings         INTEGER,
            m1_streak        INTEGER,
            m1_target        INTEGER,
            m1_done          BOOLEAN,
            churn_risk_score DOUBLE,
            churn_risk_trend VARCHAR
        )
    """)

    findings = load_findings()
    con.executemany("""
        INSERT OR REPLACE INTO findings VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, [list(r.values()) for r in findings])
    log.info("findings: %d rows", len(findings))

    benchmark = load_benchmark_history()
    con.executemany("""
        INSERT OR REPLACE INTO benchmark_history VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, [list(r.values()) for r in benchmark])
    log.info("benchmark_history: %d rows", len(benchmark))

    runs = load_daily_runs()
    con.executemany("""
        INSERT OR REPLACE INTO daily_runs VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, [list(r.values()) for r in runs])
    log.info("daily_runs: %d rows", len(runs))


def main():
    log.info("Building mil_analytics.db -> %s", DB_PATH)
    con = duckdb.connect(str(DB_PATH))
    build(con)
    con.close()
    log.info("Done.")

    # Quick verification
    con = duckdb.connect(str(DB_PATH), read_only=True)
    for table in ["findings", "benchmark_history", "daily_runs"]:
        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        log.info("  %s: %d rows", table, count)
    con.close()


if __name__ == "__main__":
    main()
