"""
habib_bank_ingestion_dag.py — CJI Pulse Sealing Pipeline v2 (Parquet)
======================================================================
Three-task chain: generate relational Parquet → seal to HDFS (partitioned) → dbt audit.

    generate_batch >> ingest_to_hdfs >> dbt_audit

Task 1 — generate_batch
    Runs generate_relational_parquet.py — 1M rows, parent-child schema.
    Output: /usr/local/airflow/include/batch_TIMESTAMP.parquet (Snappy)
    Governance: P4/P5 checked in-memory before write.

Task 2 — ingest_to_hdfs
    Uploads Parquet to partitioned HDFS path:
    /user/twin/staged/habib_bank/date=YYYY-MM-DD/batch_TIMESTAMP.parquet
    Mirrors S3/Data Lake partition convention.

Task 3 — dbt_audit
    Loads HDFS → PostgreSQL via load_hdfs_to_pg.py.
    Runs dbt run + dbt test (P4/P5 acceptance gates).

Identity Shield: org_name='Habib Bank' through all tasks.
Hash Shield:     hmac_ref='HASH_PENDING_ORIGINAL' through all tasks.
"""

from pendulum import datetime as pendulum_datetime

try:
    from airflow.providers.standard.operators.bash import BashOperator
except ImportError:
    from airflow.operators.bash import BashOperator  # type: ignore[no-redef]

from airflow.sdk import dag

INCLUDE = "/usr/local/airflow/include"
TWIN_REFINERY = f"{INCLUDE}/twin_refinery"
HDFS_PARQUET_BASE = "hdfs://namenode:8020/user/twin/staged/habib_bank"

# ── Task 1: Generate Parquet ──────────────────────────────────────────────────
GENERATE_CMD = f"""
set -euo pipefail
RUN_DATE=$(date +%Y-%m-%d)
echo "[generate_batch] Run date: $RUN_DATE"
cd {INCLUDE}
export OUTPUT_DIR={INCLUDE}
python generate_relational_parquet.py 2>&1 | tee /tmp/generate_output.txt
# Capture parquet filename from last PARQUET_FILE= line
PARQUET_FILE=$(grep '^PARQUET_FILE=' /tmp/generate_output.txt | tail -1 | cut -d= -f2)
echo "$PARQUET_FILE" > /tmp/parquet_filename.txt
echo "[generate_batch] Parquet file: $PARQUET_FILE"
"""

# ── Task 2: Seal to partitioned HDFS ─────────────────────────────────────────
INGEST_CMD = f"""
set -euo pipefail
RUN_DATE=$(date +%Y-%m-%d)
PARQUET_FILE=$(cat /tmp/parquet_filename.txt)
SRC="{INCLUDE}/$PARQUET_FILE"
HDFS_PARTITION="user/twin/staged/habib_bank/date=$RUN_DATE"
HDFS_DEST="$HDFS_PARTITION/$PARQUET_FILE"

echo "[ingest_to_hdfs] Date partition : $RUN_DATE"
echo "[ingest_to_hdfs] Source         : $SRC"
echo "[ingest_to_hdfs] HDFS dest      : $HDFS_DEST"

python - <<PYEOF
from hdfs import InsecureClient
import os

client = InsecureClient("http://namenode:9870", user="root")
run_date = os.popen("date +%Y-%m-%d").read().strip()
parquet_file = open("/tmp/parquet_filename.txt").read().strip()

hdfs_dir  = f"/user/twin/staged/habib_bank/date={{run_date}}"
hdfs_dest = f"{{hdfs_dir}}/{{parquet_file}}"
src       = f"{INCLUDE}/{{parquet_file}}"

try:
    client.makedirs(hdfs_dir)
except Exception:
    pass

client.upload(hdfs_dest, src, overwrite=True)
status = client.status(hdfs_dest)
size_mb = status["length"] / (1024 * 1024)
print(f"[ingest_to_hdfs] Sealed  : {{hdfs_dest}}")
print(f"[ingest_to_hdfs] Size    : {{size_mb:.1f}} MB")
PYEOF
echo "[ingest_to_hdfs] Done"
"""

# ── Task 3: Load → PG → dbt run + test ───────────────────────────────────────
DBT_AUDIT_CMD = f"""
set -euo pipefail
echo "[dbt_audit] Step 1 — Loading HDFS → PostgreSQL..."
python {TWIN_REFINERY}/scripts/load_hdfs_to_pg.py

echo "[dbt_audit] Step 2 — Running dbt models..."
cd {TWIN_REFINERY}
dbt run --profiles-dir .

echo "[dbt_audit] Step 3 — Running dbt governance tests (P4 + P5)..."
dbt test --profiles-dir .

echo "[dbt_audit] PASS — P4 SEALED, P5 SEALED, staging view materialised"
"""


@dag(
    dag_id="habib_bank_ingestion",
    start_date=pendulum_datetime(2026, 3, 1),
    schedule=None,
    catchup=False,
    tags=["sealing-pipeline", "maer", "parquet", "governance"],
    default_args={"owner": "cji-pulse", "retries": 1},
    doc_md=__doc__,
)
def habib_bank_ingestion():
    generate_batch = BashOperator(
        task_id="generate_batch",
        bash_command=GENERATE_CMD,
    )

    ingest_to_hdfs = BashOperator(
        task_id="ingest_to_hdfs",
        bash_command=INGEST_CMD,
    )

    dbt_audit = BashOperator(
        task_id="dbt_audit",
        bash_command=DBT_AUDIT_CMD,
    )

    generate_batch >> ingest_to_hdfs >> dbt_audit


habib_bank_ingestion()
