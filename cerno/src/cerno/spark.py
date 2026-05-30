"""SparkSession factory.

The bank edge node runs PySpark 2.4.0 — design any Spark code for that
vintage. `arg_min` / `arg_max` are not present; use struct min/max
patterns instead.

PySpark is loaded lazily so importing cerno.spark does not pull in the
JVM unless a session is actually requested.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from pyspark.sql import SparkSession


def get_spark(app_name: str = "cerno", master: str = "local[*]") -> "SparkSession":
    """Return a SparkSession configured for CPU-only single-node use.

    `app_name` — surfaces in the Spark UI / driver logs.
    `master`   — defaults to `local[*]`; override for cluster runs.

    Lazy: pyspark is imported here so a missing pyspark on a dev box
    does not break unrelated tests.
    """
    from pyspark.sql import SparkSession  # noqa: E402

    return (
        SparkSession.builder.appName(app_name)
        .master(master)
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )


def stop(session: Any) -> None:
    """Stop a Spark session cleanly; safe to call on a stopped session."""
    try:
        session.stop()
    except Exception:  # noqa: BLE001
        pass
