"""
mil/chat/retrievers/status.py — coverage / freshness / system-state retriever.

Fires for `status` intent. Runs a small fixed set of DuckDB queries against
mil_analytics.db and returns each fact as its own Evidence item so the
synthesiser can cite data-freshness claims the same way it cites findings.
"""
from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from mil.chat.retrievers.base import Evidence, EvidenceBundle, Retriever

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_DB_PATH   = _REPO_ROOT / "mil_analytics.db"


@contextmanager
def _conn():
    """Short-lived read-only connection. Released before the daily analytics
    rebuild runs so there's no write-lock collision on Windows."""
    import duckdb
    if not _DB_PATH.exists():
        logger.warning("[status] analytics db missing: %s", _DB_PATH)
        yield None
        return
    conn = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        yield conn
    finally:
        conn.close()


def _id(key: str) -> str:
    return "status_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


class StatusRetriever(Retriever):
    name = "status"

    def retrieve(
        self,
        query: str,
        entities: Optional[dict[str, Any]] = None,
        k: int = 20,
    ) -> EvidenceBundle:
        bundle = EvidenceBundle(query=query, retriever_chain=[self.name])

        with _conn() as conn:
            if conn is None:
                return bundle
            self._populate(conn, bundle)
        bundle.total_candidates = len(bundle.items)
        return bundle

    def _populate(self, conn, bundle) -> None:
        # 1. Review-corpus coverage (dates + totals) per competitor.
        try:
            rows = conn.execute("""
                SELECT lower(competitor)                                   AS competitor,
                       COUNT(*)                                            AS total,
                       MIN(try_cast(date AS DATE))                         AS first_date,
                       MAX(try_cast(date AS DATE))                         AS last_date,
                       COUNT(DISTINCT try_cast(date AS DATE))              AS distinct_days
                FROM reviews
                GROUP BY lower(competitor)
                ORDER BY total DESC
            """).fetchall()
            for comp, total, first_date, last_date, distinct_days in rows:
                text = (
                    f"{comp}: {total} reviews, spanning {first_date} to {last_date} "
                    f"({distinct_days} distinct days with data)"
                )
                bundle.add(Evidence(
                    source="status",
                    id=_id(f"reviews:{comp}"),
                    text=text,
                    score=0.95,
                    metadata={
                        "kind":           "coverage_per_competitor",
                        "competitor":     comp,
                        "total_reviews":  total,
                        "first_date":     str(first_date),
                        "last_date":      str(last_date),
                        "distinct_days":  distinct_days,
                    },
                ))
        except Exception as exc:
            logger.warning("[status] reviews coverage query failed: %s", exc)

        # 2. Source breakdown.
        try:
            src_rows = conn.execute("""
                SELECT source, COUNT(*) AS n
                FROM reviews
                GROUP BY source
                ORDER BY n DESC
            """).fetchall()
            if src_rows:
                parts = [f"{s}={n}" for s, n in src_rows]
                bundle.add(Evidence(
                    source="status",
                    id=_id("sources"),
                    text="Source breakdown: " + ", ".join(parts),
                    score=0.9,
                    metadata={"kind": "source_breakdown",
                              "sources": {s: n for s, n in src_rows}},
                ))
        except Exception as exc:
            logger.warning("[status] sources query failed: %s", exc)

        # 3. Overall window + corpus totals.
        try:
            total, min_d, max_d, days, n_comp, n_src = conn.execute("""
                SELECT COUNT(*),
                       MIN(try_cast(date AS DATE)),
                       MAX(try_cast(date AS DATE)),
                       COUNT(DISTINCT try_cast(date AS DATE)),
                       COUNT(DISTINCT lower(competitor)),
                       COUNT(DISTINCT source)
                FROM reviews
            """).fetchone()
            window = f"{min_d} to {max_d}"
            text = (
                f"Overall corpus: {total} reviews across {n_comp} competitors and "
                f"{n_src} sources, spanning {window} ({days} distinct data days)."
            )
            bundle.add(Evidence(
                source="status",
                id=_id("corpus_total"),
                text=text,
                score=1.0,
                metadata={
                    "kind":              "corpus_total",
                    "total_reviews":     total,
                    "window_start":      str(min_d),
                    "window_end":        str(max_d),
                    "distinct_days":     days,
                    "competitor_count":  n_comp,
                    "source_count":      n_src,
                },
            ))
        except Exception as exc:
            logger.warning("[status] corpus total query failed: %s", exc)

        # 4. Latest daily pipeline run (when was the last update).
        try:
            row = conn.execute("""
                SELECT run, date, status, new_records, findings, m1_streak,
                       churn_risk_score, churn_risk_trend
                FROM daily_runs
                ORDER BY run DESC
                LIMIT 1
            """).fetchone()
            if row:
                run, date, status, new_rec, findings, streak, churn, trend = row
                text = (
                    f"Most recent pipeline run: #{run} on {date}, status={status}, "
                    f"new records ingested={new_rec}, active findings={findings}, "
                    f"M1 streak={streak}, churn risk score={churn} ({trend})."
                )
                bundle.add(Evidence(
                    source="status",
                    id=_id("last_run"),
                    text=text,
                    score=1.0,
                    metadata={
                        "kind":           "last_pipeline_run",
                        "run":            run,
                        "date":           str(date),
                        "status":         status,
                        "new_records":    new_rec,
                        "findings":       findings,
                        "m1_streak":      streak,
                        "churn_risk":     churn,
                        "churn_trend":    trend,
                    },
                ))
        except Exception as exc:
            logger.warning("[status] daily_runs query failed: %s", exc)

        # 5. CHRONICLE size.
        try:
            chr_count = conn.execute("SELECT COUNT(*) FROM chr_entries").fetchone()[0]
            bundle.add(Evidence(
                source="status",
                id=_id("chronicle_size"),
                text=f"CHRONICLE ledger contains {chr_count} inference-approved entries.",
                score=0.85,
                metadata={"kind": "chronicle_size", "count": chr_count},
            ))
        except Exception as exc:
            logger.warning("[status] chronicle size query failed: %s", exc)
