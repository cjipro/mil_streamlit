"""
mil/chat/retrievers/sql.py — MIL-41.

Structured DuckDB retriever over mil_analytics.db.
Answers aggregate-shaped questions: trend, compare, peer_rank.

The orchestrator passes the classified intent through entities['_intent'].
Each intent maps to a query template that returns rows — one Evidence per row.
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
    """Open a short-lived read-only DuckDB connection. Closes on exit so the
    daily analytics rebuild (write mode) isn't blocked by a long-held handle."""
    import duckdb
    if not _DB_PATH.exists():
        logger.warning("[sql] analytics db missing: %s", _DB_PATH)
        yield None
        return
    conn = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        yield conn
    finally:
        conn.close()


def _row_id(payload: str) -> str:
    return "sql_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _competitors_from_entities(entities: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if entities.get("competitor"):
        out.append(str(entities["competitor"]).lower())
    for c in entities.get("competitors") or []:
        if isinstance(c, str):
            out.append(c.lower())
    return list(dict.fromkeys(out))


class SQLRetriever(Retriever):
    name = "sql"

    def retrieve(
        self,
        query: str,
        entities: Optional[dict[str, Any]] = None,
        k: int = 10,
    ) -> EvidenceBundle:
        entities = entities or {}
        bundle = EvidenceBundle(query=query, retriever_chain=[self.name])

        with _conn() as conn:
            if conn is None:
                return bundle
            intent = entities.get("_intent", "trend")
            if intent == "compare":
                self._query_compare(conn, entities, bundle, k)
            elif intent == "peer_rank":
                self._query_peer_rank(conn, entities, bundle, k)
            else:
                self._query_trend(conn, entities, bundle, k)

        bundle.total_candidates = len(bundle.items)
        return bundle

    # ── Trend ─────────────────────────────────────────────────────────────
    def _query_trend(self, conn, entities, bundle, k):
        competitors = _competitors_from_entities(entities) or ["barclays"]
        issue_type = entities.get("issue_type")
        days = max(7, int(entities.get("timeframe_days") or 30))

        sql = """
            SELECT date, COUNT(*) AS volume, AVG(rating) AS avg_rating,
                   SUM(CASE WHEN severity_class='P0' THEN 1 ELSE 0 END) AS p0
            FROM reviews
            WHERE lower(competitor) = ?
              AND try_cast(date AS DATE) >= current_date - ?
              {issue_clause}
            GROUP BY date
            ORDER BY date DESC
            LIMIT ?
        """
        for comp in competitors:
            params: list[Any] = [comp, days]
            clause = ""
            if issue_type:
                clause = "AND issue_type = ?"
                params.append(issue_type)
            params.append(k)
            try:
                rows = conn.execute(sql.format(issue_clause=clause), params).fetchall()
            except Exception as exc:
                logger.warning("[sql:trend] failed: %s", exc)
                continue
            cols = ["date", "volume", "avg_rating", "p0"]
            for row in rows:
                payload = dict(zip(cols, row))
                text = (
                    f"{comp} {payload['date']}: volume={payload['volume']}, "
                    f"avg_rating={payload['avg_rating']:.2f}, P0={payload['p0']}"
                )
                bundle.add(Evidence(
                    source="benchmark",
                    id=_row_id(f"trend:{comp}:{payload['date']}:{issue_type}"),
                    text=text,
                    score=0.9,
                    metadata={"intent": "trend", "competitor": comp,
                              "issue_type": issue_type, **payload},
                ))

    # ── Compare ───────────────────────────────────────────────────────────
    def _query_compare(self, conn, entities, bundle, k):
        competitors = _competitors_from_entities(entities)
        if len(competitors) < 2:
            logger.info("[sql:compare] need >=2 competitors, got %s", competitors)
            return
        issue_type = entities.get("issue_type")
        days = max(7, int(entities.get("timeframe_days") or 30))

        placeholders = ",".join(["?"] * len(competitors))
        sql = f"""
            SELECT lower(competitor) AS competitor,
                   COUNT(*) AS volume,
                   AVG(rating) AS avg_rating,
                   SUM(CASE WHEN severity_class='P0' THEN 1 ELSE 0 END) AS p0,
                   SUM(CASE WHEN severity_class='P1' THEN 1 ELSE 0 END) AS p1
            FROM reviews
            WHERE lower(competitor) IN ({placeholders})
              AND try_cast(date AS DATE) >= current_date - ?
              {'AND issue_type = ?' if issue_type else ''}
            GROUP BY lower(competitor)
            ORDER BY avg_rating ASC
        """
        params: list[Any] = list(competitors) + [days]
        if issue_type:
            params.append(issue_type)
        try:
            rows = conn.execute(sql, params).fetchall()
        except Exception as exc:
            logger.warning("[sql:compare] failed: %s", exc)
            return

        cols = ["competitor", "volume", "avg_rating", "p0", "p1"]
        for row in rows[:k]:
            payload = dict(zip(cols, row))
            text = (
                f"{payload['competitor']} on {issue_type or 'all issues'} "
                f"(last {days}d): vol={payload['volume']}, "
                f"rating={payload['avg_rating']:.2f}, P0={payload['p0']}, P1={payload['p1']}"
            )
            bundle.add(Evidence(
                source="benchmark",
                id=_row_id(f"compare:{payload['competitor']}:{issue_type}:{days}"),
                text=text,
                score=0.9,
                metadata={"intent": "compare", **payload,
                          "issue_type": issue_type, "timeframe_days": days},
            ))

    # ── Peer rank ─────────────────────────────────────────────────────────
    def _query_peer_rank(self, conn, entities, bundle, k):
        issue_type = entities.get("issue_type")
        days = max(7, int(entities.get("timeframe_days") or 30))
        # If the user asked for a specific competitor subset, honour it;
        # otherwise rank all six monitored peers.
        competitors = _competitors_from_entities(entities)

        clauses = ["try_cast(date AS DATE) >= current_date - ?"]
        params: list[Any] = [days]
        if issue_type:
            clauses.append("issue_type = ?")
            params.append(issue_type)
        if competitors:
            clauses.append(f"lower(competitor) IN ({','.join(['?']*len(competitors))})")
            params.extend(competitors)

        sql = f"""
            SELECT lower(competitor) AS competitor,
                   COUNT(*) AS volume,
                   AVG(rating) AS avg_rating,
                   SUM(CASE WHEN severity_class='P0' THEN 1 ELSE 0 END) AS p0
            FROM reviews
            WHERE {' AND '.join(clauses)}
            GROUP BY lower(competitor)
            ORDER BY avg_rating ASC
            LIMIT ?
        """
        params.append(k)
        try:
            rows = conn.execute(sql, params).fetchall()
        except Exception as exc:
            logger.warning("[sql:peer_rank] failed: %s", exc)
            return

        cols = ["competitor", "volume", "avg_rating", "p0"]
        for rank, row in enumerate(rows, start=1):
            payload = dict(zip(cols, row))
            text = (
                f"#{rank} {payload['competitor']} on {issue_type or 'all issues'} "
                f"(last {days}d): rating={payload['avg_rating']:.2f}, "
                f"vol={payload['volume']}, P0={payload['p0']}"
            )
            bundle.add(Evidence(
                source="benchmark",
                id=_row_id(f"rank:{payload['competitor']}:{issue_type}:{days}"),
                text=text,
                score=1.0 - (rank - 1) * 0.05,
                metadata={"intent": "peer_rank", "rank": rank,
                          "issue_type": issue_type, "timeframe_days": days, **payload},
            ))
