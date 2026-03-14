# CJI Global Bank — Operational Chronicle

## Purpose
This document is the primary source of operational lessons learned for CJI Pulse / Habib Bank digital twin. It is machine-readable and human-auditable. All agents must consult it before making infrastructure changes.

## Operational History

### Lesson 001 — Port Conflict: Astro Metadata DB vs Dev Stack PostgreSQL
- **Problem:** astro dev start tried to bind its metadata postgres to host port 5432, already occupied by the dev-stack postgresql container.
- **Fix:** `astro config set postgres.port 5433` remapped Astro metadata DB to host port 5433. Dev-stack postgresql stays on 5432.
- **Rule:** Astro metadata DB always uses port 5433 on this machine.

### Lesson 002 — HDFS Resilience: bde2020 Images
- **Problem:** Original Apache Hadoop images had unstable Python and WebHDFS support, causing connection failures from application containers.
- **Fix:** Replaced with bde2020/hadoop-namenode and bde2020/hadoop-datanode (2.0.0-hadoop3.2.1-java8). WebHDFS REST API reliably exposed on port 9870.
- **Rule:** Always use bde2020 Hadoop images. Never switch to official Apache images without explicit testing.

### Lesson 003 — Path Integrity: Windows/Linux Scheme C Conflict
- **Problem:** Running `hdfs dfs` commands inside containers from Git Bash (MINGW64) caused the error: `No FileSystem for scheme C`. Git Bash mangled the absolute path `/user/...` into `C:/user/...`
- **Fix:** Always use the full HDFS URI inside docker exec commands. Wrap in `docker exec namenode bash -c "..."` with `hdfs://namenode:8020` prefix. Never use bare `/user/...` paths from Git Bash.
- **Rule:** All docker exec hdfs commands must use full `hdfs://namenode:8020/...` URIs.

### Lesson 004 — Docker Compose Override: Airflow 3.x Service Names
- **Problem:** docker-compose.override.yml referenced service `webserver` which does not exist in Airflow 3.x. In Airflow 3.x the webserver is replaced by `api-server`. Docker Compose v2+ also ignores the `version:` field and emits warnings.
- **Fix:** Removed `webserver` and `triggerer` from override. Only `scheduler` needs dev-network access under LocalExecutor. Removed the `version:` field.
- **Rule:** Airflow 3.x services are: `scheduler`, `api-server`, `triggerer`, `dag-processor`, `postgres`. Never reference `webserver`.

### Lesson 005 — Scale-Up Optimisation: CSV → Parquet Migration
- **Problem:** CSV format at 284k rows = 35.4 MB. Projecting to 1M rows = ~125 MB CSV. At 10M rows = ~1.25 GB — WebHDFS reads become slow and Streamlit load times exceed acceptable thresholds.
- **Fix:** Migrated to Snappy-compressed Parquet. `generate_relational_parquet.py` produces ~1M rows in columnar format. HDFS path partitioned by date: `/user/twin/staged/habib_bank/date=YYYY-MM-DD/batch_TIMESTAMP.parquet` — mirrors S3/Data Lake production convention.
- **Schema upgrade:** Added `customer_id` field — relational parent-child model (Customer → Session → Journey Steps) replaces flat session-only model.
- **Streamlit:** HDFS Live page now attempts Parquet first (with Latency Monitor showing load time in ms), falls back to CSV if no Parquet partition exists.
- **Rule:** All new batches must be written as Snappy Parquet. CSV generation retained only for legacy compatibility.

## Defined Limit Governance

### AI Agent Autonomy Boundary
AI Agents have full autonomy over the Habib Bank simulation up to the Defined Limit of **10 million rows**.

Within this limit, agents may:
- Generate synthetic MAER batch data
- Run dbt audits and staging model refreshes
- Manage HDFS file uploads and directory structure
- Trigger Airflow DAG runs
- Update governance logs and telemetry

### Escalation Protocol — Defined Limit Reached
When total row count in HDFS vault reaches or exceeds 10,000,000 rows:
1. Agent must **STOP** all batch generation immediately
2. Agent must **NOT** write additional rows to HDFS
3. Agent must draft a **Migration Proposal** containing:
   - Current row count and storage size
   - Recommended targets: ClickHouse (OLAP queries) and Databricks (ML pipeline)
   - Estimated migration effort
   - Data governance continuity plan (P4/P5 controls must survive migration)
4. Agent must present the Migration Proposal to Hussain and **await instruction**

## Separation of Concerns

### Human-Only (Hussain)
| Responsibility | Reason |
|---|---|
| Final P4/P5 Security Policy changes | Constitutional governance — no agent overrides |
| Cloud credentials management | Keys never handled by agents |
| Defined Limit increases | Requires human risk assessment |
| Production deployment approvals | Human-in-the-loop mandatory |
| Regulatory sign-off (REG-001 to REG-004) | DPIA and compliance require human accountability |

### AI-Managed (Agents)
| Responsibility | Tooling |
|---|---|
| Routine batch generation | generate_batch_01.py / Airflow DAG |
| dbt audits and staging model runs | twin_refinery / dbt-postgres |
| HDFS maintenance | hdfs.InsecureClient / WebHDFS |
| Governance log updates | audit_findings.yaml / telemetry_spec.yaml |
| DAG health monitoring | Airflow API v2 |
| Principle violation logging | validate_principles.py |

## Row Count Tracker
| Date | Batch | Rows Added | Cumulative Total | Storage (HDFS) | Status |
|---|---|---|---|---|---|
| 2026-03-13 | batch_01_habib_bank.csv | ~284,000 | ~284,000 | 35.4 MB | ACTIVE |

*Defined Limit: 10,000,000 rows. Current utilisation: ~2.8%*
