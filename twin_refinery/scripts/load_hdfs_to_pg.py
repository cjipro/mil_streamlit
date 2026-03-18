"""
load_hdfs_to_pg.py — HDFS → PostgreSQL loader
Reads batch_01_habib_bank.csv from HDFS WebHDFS API and loads into
PostgreSQL raw.maer_batch_01 for dbt consumption.
"""

import io
import os
import sys

import pandas as pd
import psycopg2
from hdfs import InsecureClient

HDFS_URL = os.getenv("HDFS_URL", "http://namenode:9870")
HDFS_PATH = "/user/twin/staged/batch_01_habib_bank.csv"

PG_HOST = os.getenv("PG_HOST", "postgresql")
PG_PORT = int(os.getenv("PG_PORT", 5432))
PG_DB = os.getenv("PG_DB", "cjipulse")
PG_USER = os.getenv("PG_USER", "cjipulse_user")
PG_PASS = os.getenv("PG_PASS", "cjipulse_pass")


def load():
    print(f"[loader] Connecting to HDFS at {HDFS_URL}")
    client = InsecureClient(HDFS_URL, user="root")

    print(f"[loader] Reading {HDFS_PATH}")
    with client.read(HDFS_PATH, encoding="utf-8") as reader:
        df = pd.read_csv(reader)

    print(f"[loader] Loaded {len(df):,} rows from HDFS")

    # Governance check before insert
    p5_violations = (df["org_name"] != "Habib Bank").sum()
    p4_violations = (df["hmac_ref"] != "HASH_PENDING_ORIGINAL").sum()
    if p5_violations + p4_violations > 0:
        print(f"[loader] WARN — P5 violations: {p5_violations}, P4 violations: {p4_violations}")
        sys.exit(1)

    print(f"[loader] Governance check PASS — writing to PostgreSQL")
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS
    )
    cur = conn.cursor()

    cur.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    cur.execute("DROP TABLE IF EXISTS raw.maer_batch_01;")
    cur.execute("""
        CREATE TABLE raw.maer_batch_01 (
            session_id     TEXT,
            org_name       TEXT,
            channel        TEXT,
            journey_step   TEXT,
            event_ts       TEXT,
            step_duration_s INTEGER,
            outcome        TEXT,
            hmac_ref       TEXT
        );
    """)

    buffer = io.StringIO()
    df.to_csv(buffer, index=False, header=False)
    buffer.seek(0)
    cur.copy_from(buffer, "raw.maer_batch_01", sep=",", null="")

    conn.commit()
    cur.close()
    conn.close()
    print(f"[loader] Done — {len(df):,} rows in raw.maer_batch_01")


if __name__ == "__main__":
    load()
