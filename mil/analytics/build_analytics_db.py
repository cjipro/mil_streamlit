"""
build_analytics_db.py — Build complete mil_analytics.db.

Tables:
  reviews           — 7,000+ enriched records across all sources / competitors
  findings          — 144 CAC findings with CHR anchor, clark tier, ceiling flag
  chronicle         — CHR-001 to CHR-019 reference entries from CHRONICLE.md
  benchmark_history — issue persistence log (gap_pp, days_active, over_indexed)
  daily_runs        — pipeline run log (streak, churn, new records)
  clark_log         — full escalation / downgrade history
  vault_log         — mirror of mil_vault.db anchor log

Run: py mil/analytics/build_analytics_db.py
"""
import json
import logging
import re
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH   = REPO_ROOT / "mil_analytics.db"

ENRICHED_DIR     = REPO_ROOT / "mil/data/historical/enriched"
FINDINGS_FILE    = REPO_ROOT / "mil/outputs/mil_findings.json"
CHRONICLE_FILE   = REPO_ROOT / "mil/CHRONICLE.md"
PERSISTENCE_FILE = REPO_ROOT / "mil/data/issue_persistence_log.jsonl"
RUN_LOG_FILE     = REPO_ROOT / "mil/data/daily_run_log.jsonl"
CLARK_LOG_FILE   = REPO_ROOT / "mil/data/clark_log.jsonl"
VAULT_DB_FILE    = REPO_ROOT / "mil/vault/mil_vault.db"
COMMENTARY_LOG   = REPO_ROOT / "mil/data/commentary_log.jsonl"
RESEARCH_QUEUE   = REPO_ROOT / "mil/data/research_queue.jsonl"


# ---------------------------------------------------------------------------
# reviews
# ---------------------------------------------------------------------------

def _content(r: dict) -> str:
    return r.get("review") or r.get("content") or r.get("body") or ""


def _rating(r: dict):
    v = r.get("rating") or r.get("score")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _source_id(r: dict, source: str) -> str | None:
    if source == "reddit":
        return r.get("post_id")
    if source == "youtube":
        return r.get("comment_id")
    if source == "downdetector":
        return r.get("report_id")
    return None


def load_reviews() -> list[dict]:
    rows = []
    for fp in sorted(ENRICHED_DIR.glob("*.json")):
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        source     = data.get("source", fp.stem.rsplit("_enriched", 1)[0].rsplit("_", 1)[0])
        competitor = data.get("competitor", fp.stem.rsplit("_enriched", 1)[0].rsplit("_", 1)[-1])
        model      = data.get("model", "")
        schema_ver = data.get("schema_version", "")

        for r in data.get("records", []):
            rows.append({
                "source":            source,
                "competitor":        competitor,
                "date":              r.get("date") or r.get("video_published_at") or None,
                "content":           _content(r),
                "rating":            _rating(r),
                "author":            r.get("author") or r.get("userName") or None,
                "issue_type":        r.get("issue_type"),
                "customer_journey":  r.get("customer_journey"),
                "sentiment_score":   r.get("sentiment_score"),
                "severity_class":    r.get("severity_class"),
                "reasoning":         r.get("reasoning"),
                "source_record_id":  _source_id(r, source),
                "model":             model,
                "schema_version":    schema_ver,
            })
    return rows


# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------

def load_findings() -> list[dict]:
    with open(FINDINGS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for f in data.get("findings", []):
        rows.append({
            "finding_id":               f.get("finding_id"),
            "generated_at":             f.get("generated_at"),
            "competitor":               f.get("competitor"),
            "source":                   f.get("source"),
            "journey_id":               f.get("journey_id"),
            "signal_severity":          f.get("signal_severity"),
            "finding_tier":             f.get("finding_tier"),
            "confidence_score":         f.get("confidence_score"),
            "cac_vol_sig":              (f.get("cac_components") or {}).get("vol_sig"),
            "cac_sim_hist":             (f.get("cac_components") or {}).get("sim_hist"),
            "cac_delta_tel":            (f.get("cac_components") or {}).get("delta_tel"),
            "designed_ceiling_reached": f.get("designed_ceiling_reached", False),
            "failure_mode":             f.get("failure_mode"),
            "chronicle_id":             (f.get("provenance") or {}).get("chronicle_id"),
            "chronicle_bank":           (f.get("chronicle_match") or {}).get("bank"),
            "sim_hist_score":           (f.get("chronicle_match") or {}).get("sim_hist_score"),
            "signal_total":             (f.get("signal_counts") or {}).get("total"),
            "signal_p0":                (f.get("signal_counts") or {}).get("P0"),
            "signal_p1":                (f.get("signal_counts") or {}).get("P1"),
            "signal_p2":                (f.get("signal_counts") or {}).get("P2"),
            "human_countersign_status": f.get("human_countersign_status"),
            "is_unanchored":            f.get("is_unanchored", False),
            "finding_summary":          f.get("finding_summary"),
        })
    return rows


# ---------------------------------------------------------------------------
# chronicle — parse CHRONICLE.md YAML blocks
# ---------------------------------------------------------------------------

def load_chronicle() -> list[dict]:
    with open(CHRONICLE_FILE, encoding="utf-8") as f:
        content = f.read()

    ids        = re.findall(r'chronicle_id:\s*(CHR-\d+)', content)
    banks      = re.findall(r'\bbank:\s*"([^"]+)"', content)
    inc_types  = re.findall(r'incident_type:\s*"([^"]+)"', content)
    dates      = re.findall(r'^date:\s*"([^"]+)"', content, re.MULTILINE)
    approved   = re.findall(r'inference_approved:\s*(true|false)', content)
    scores     = re.findall(r'confidence_score:\s*([\d.]+)', content)

    # incident_type repeats less than ids — pad with None
    def pad(lst, n):
        return lst + [None] * (n - len(lst))

    n = len(ids)
    rows = []
    for i in range(n):
        rows.append({
            "chronicle_id":       ids[i] if i < len(ids) else None,
            "bank":               banks[i] if i < len(banks) else None,
            "incident_type":      inc_types[i] if i < len(inc_types) else None,
            "incident_date":      dates[i] if i < len(dates) else None,
            "inference_approved": approved[i] == "true" if i < len(approved) else None,
            "confidence_score":   float(scores[i]) if i < len(scores) else None,
        })
    return rows


# ---------------------------------------------------------------------------
# benchmark_history
# ---------------------------------------------------------------------------

def load_benchmark_history() -> list[dict]:
    rows = []
    with open(PERSISTENCE_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows.append({
                "date":              r.get("date"),
                "issue_type":        r.get("issue_type"),
                "category":          r.get("category"),
                "barclays_rate":     r.get("barclays_rate"),
                "peer_avg_rate":     r.get("peer_avg_rate"),
                "gap_pp":            r.get("gap_pp"),
                "over_indexed":      r.get("over_indexed", False),
                "dominant_severity": r.get("dominant_severity"),
                "days_active":       r.get("days_active"),
                "first_seen":        r.get("first_seen") or None,
            })
    return rows


# ---------------------------------------------------------------------------
# daily_runs
# ---------------------------------------------------------------------------

def load_daily_runs() -> list[dict]:
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


# ---------------------------------------------------------------------------
# clark_log
# ---------------------------------------------------------------------------

def load_clark_log() -> list[dict]:
    rows = []
    with open(CLARK_LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows.append({
                "ts":         r.get("ts"),
                "event":      r.get("event"),
                "finding_id": r.get("finding_id"),
                "competitor": r.get("competitor"),
                "clark_tier": r.get("clark_tier"),
                "from_tier":  r.get("from_tier"),
                "cac_score":  r.get("cac_score"),
                "finding_tier": r.get("finding_tier"),
                "reason":     r.get("reason"),
                "synthesis":  r.get("synthesis"),
            })
    return rows


# ---------------------------------------------------------------------------
# vault_log — mirror from mil_vault.db
# ---------------------------------------------------------------------------

def load_commentary() -> list[dict]:
    if not COMMENTARY_LOG.exists():
        return []
    rows = []
    seen = set()
    with open(COMMENTARY_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            key = (r.get("date"), r.get("issue_type"), r.get("type"))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "date":              r.get("date"),
                "type":              r.get("type"),
                "issue_type":        r.get("issue_type"),
                "category":          r.get("category"),
                "barclays_rate":     r.get("barclays_rate"),
                "peer_avg_rate":     r.get("peer_avg_rate"),
                "gap_pp":            r.get("gap_pp"),
                "dominant_severity": r.get("dominant_severity"),
                "days_active":       r.get("days_active"),
                "prose":             r.get("prose"),
                "chr_resonance":     r.get("chr_resonance") or "",
            })
    return rows


def load_unanchored_signals() -> list[dict]:
    if not RESEARCH_QUEUE.exists():
        return []
    rows = []
    with open(RESEARCH_QUEUE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows.append({
                "finding_id":       r.get("finding_id"),
                "competitor":       r.get("competitor"),
                "journey_id":       r.get("journey_id"),
                "signal_severity":  r.get("signal_severity"),
                "cac_score":        r.get("cac_score"),
                "sim_hist_score":   r.get("sim_hist_score"),
                "chronicle_id":     r.get("chronicle_id"),
                "is_unanchored":    r.get("is_unanchored", False),
                "status":           r.get("status"),
                "triggered_at":     r.get("triggered_at"),
                "resolved_at":      r.get("resolved_at"),
                "resolution_note":  r.get("resolution_note"),
            })
    return rows


def load_vault_log() -> list[dict]:
    src = duckdb.connect(str(VAULT_DB_FILE), read_only=True)
    df = src.execute("SELECT * FROM vault_anchor_log").fetchdf()
    src.close()
    return df.to_dict(orient="records")


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(con: duckdb.DuckDBPyConnection):

    con.execute("""
        CREATE OR REPLACE TABLE reviews (
            source           VARCHAR,
            competitor       VARCHAR,
            date             VARCHAR,
            content          VARCHAR,
            rating           DOUBLE,
            author           VARCHAR,
            issue_type       VARCHAR,
            customer_journey VARCHAR,
            sentiment_score  DOUBLE,
            severity_class   VARCHAR,
            reasoning        VARCHAR,
            source_record_id VARCHAR,
            model            VARCHAR,
            schema_version   VARCHAR
        )
    """)

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
        CREATE OR REPLACE TABLE chr_entries (
            chronicle_id       VARCHAR PRIMARY KEY,
            bank               VARCHAR,
            incident_type      VARCHAR,
            incident_date      VARCHAR,
            inference_approved BOOLEAN,
            confidence_score   DOUBLE
        )
    """)

    con.execute("""
        CREATE OR REPLACE TABLE benchmark_history (
            date              DATE,
            issue_type        VARCHAR,
            category          VARCHAR,
            barclays_rate     DOUBLE,
            peer_avg_rate     DOUBLE,
            gap_pp            DOUBLE,
            over_indexed      BOOLEAN,
            dominant_severity VARCHAR,
            days_active       INTEGER,
            first_seen        DATE,
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

    con.execute("""
        CREATE OR REPLACE TABLE clark_log (
            ts           TIMESTAMPTZ,
            event        VARCHAR,
            finding_id   VARCHAR,
            competitor   VARCHAR,
            clark_tier   VARCHAR,
            from_tier    VARCHAR,
            cac_score    DOUBLE,
            finding_tier VARCHAR,
            reason       VARCHAR,
            synthesis    VARCHAR
        )
    """)

    con.execute("""
        CREATE OR REPLACE TABLE vault_log (
            file_name    VARCHAR,
            source       VARCHAR,
            competitor   VARCHAR,
            record_count INTEGER,
            model        VARCHAR,
            hdfs_path    VARCHAR,
            anchored_at  TIMESTAMPTZ,
            status       VARCHAR
        )
    """)

    con.execute("""
        CREATE OR REPLACE TABLE commentary (
            date              DATE,
            type              VARCHAR,
            issue_type        VARCHAR,
            category          VARCHAR,
            barclays_rate     DOUBLE,
            peer_avg_rate     DOUBLE,
            gap_pp            DOUBLE,
            dominant_severity VARCHAR,
            days_active       INTEGER,
            prose             VARCHAR,
            chr_resonance     VARCHAR,
            PRIMARY KEY (date, issue_type, type)
        )
    """)

    con.execute("""
        CREATE OR REPLACE TABLE unanchored_signals (
            finding_id      VARCHAR PRIMARY KEY,
            competitor      VARCHAR,
            journey_id      VARCHAR,
            signal_severity VARCHAR,
            cac_score       DOUBLE,
            sim_hist_score  DOUBLE,
            chronicle_id    VARCHAR,
            is_unanchored   BOOLEAN,
            status          VARCHAR,
            triggered_at    TIMESTAMPTZ,
            resolved_at     TIMESTAMPTZ,
            resolution_note VARCHAR
        )
    """)

    reviews = load_reviews()
    con.executemany(
        "INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [list(r.values()) for r in reviews],
    )
    log.info("reviews: %d rows", len(reviews))

    findings = load_findings()
    con.executemany(
        "INSERT OR REPLACE INTO findings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [list(r.values()) for r in findings],
    )
    log.info("findings: %d rows", len(findings))

    chronicle = load_chronicle()
    con.executemany(
        "INSERT OR REPLACE INTO chr_entries VALUES (?,?,?,?,?,?)",
        [list(r.values()) for r in chronicle],
    )
    log.info("chronicle: %d rows", len(chronicle))

    benchmark = load_benchmark_history()
    con.executemany(
        "INSERT OR REPLACE INTO benchmark_history VALUES (?,?,?,?,?,?,?,?,?,?)",
        [list(r.values()) for r in benchmark],
    )
    log.info("benchmark_history: %d rows", len(benchmark))

    runs = load_daily_runs()
    con.executemany(
        "INSERT OR REPLACE INTO daily_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [list(r.values()) for r in runs],
    )
    log.info("daily_runs: %d rows", len(runs))

    clark = load_clark_log()
    con.executemany(
        "INSERT INTO clark_log VALUES (?,?,?,?,?,?,?,?,?,?)",
        [list(r.values()) for r in clark],
    )
    log.info("clark_log: %d rows", len(clark))

    vault = load_vault_log()
    con.executemany(
        "INSERT INTO vault_log VALUES (?,?,?,?,?,?,?,?)",
        [list(r.values()) for r in vault],
    )
    log.info("vault_log: %d rows", len(vault))

    commentary = load_commentary()
    if commentary:
        con.executemany(
            "INSERT OR REPLACE INTO commentary VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [list(r.values()) for r in commentary],
        )
    log.info("commentary: %d rows", len(commentary))

    unanchored = load_unanchored_signals()
    if unanchored:
        con.executemany(
            "INSERT OR REPLACE INTO unanchored_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [list(r.values()) for r in unanchored],
        )
    log.info("unanchored_signals: %d rows", len(unanchored))


def main():
    log.info("Building mil_analytics.db -> %s", DB_PATH)
    con = duckdb.connect(str(DB_PATH))
    build(con)
    con.close()
    log.info("Done.")

    con = duckdb.connect(str(DB_PATH), read_only=True)
    for table in ["reviews", "findings", "chr_entries", "benchmark_history", "daily_runs", "clark_log", "vault_log", "commentary", "unanchored_signals"]:
        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        log.info("  %-20s %d rows", table, count)
    con.close()


if __name__ == "__main__":
    main()
