"""
mil/monitoring/drift_monitor.py — MIL-48

Daily drift detection. Reads enriched review corpus, emits alerts for drift
patterns that autonomy needs to see. Runs as run_daily.py Step 4f.

Detectors implemented:
  Silent Wall — spike in 1-star reviews with <20 chars of review text.
                Non-vocal regression signal: customers angry enough to
                1-star but not angry enough to type. App breaking in a
                way that makes typing pointless is the canonical cause.

Thresholds live in mil/config/drift_thresholds.yaml. Alerts append to
mil/data/drift_log.jsonl. HIGH-severity alerts escalate via notifier.

MIL Zero Entanglement: no imports from pulse/, poc/, app/, dags/.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_MIL_ROOT    = Path(__file__).parent.parent
_ENRICHED    = _MIL_ROOT / "data" / "historical" / "enriched"
_DRIFT_LOG   = _MIL_ROOT / "data" / "drift_log.jsonl"
_CONFIG_PATH = _MIL_ROOT / "config" / "drift_thresholds.yaml"


# ── Alert record ─────────────────────────────────────────────────────────────

@dataclass
class DriftAlert:
    ts:        str
    check:     str                 # "silent_wall"
    severity:  str                 # "INFO" | "WARN" | "HIGH"
    entity:    str                 # e.g. "app_store barclays"
    metric:    float               # observed value (ratio, count, etc.)
    threshold: float               # configured threshold that was crossed
    detail:    str                 # human-readable explanation
    context:   dict = field(default_factory=dict)  # extra fields per detector


# ── Config ────────────────────────────────────────────────────────────────────

def _load_thresholds() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    loaded = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


# ── Silent Wall detector ─────────────────────────────────────────────────────

def _date_key(iso_str: str) -> str:
    """Take the 'YYYY-MM-DD' prefix of an ISO date. Robust to varying formats."""
    return (iso_str or "")[:10]


def _is_silent(r: dict, min_chars: int) -> bool:
    return len((r.get("review") or "").strip()) < min_chars


def _silent_stats_per_entity(min_chars: int, window_days: int,
                             baseline_days: int, today: datetime.date) -> list[dict]:
    """
    Walk every enriched file and compute current-window + baseline silent
    ratios per source+competitor entity. Returned even when ratios are low —
    the caller decides alert severity. Used by both detect_silent_wall and
    the --baseline-report CLI.
    """
    window_start   = today - timedelta(days=window_days)
    baseline_start = today - timedelta(days=baseline_days + window_days)
    stats: list[dict] = []

    for enriched in sorted(_ENRICHED.glob("*_enriched.json")):
        try:
            payload = json.loads(enriched.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[drift] skip %s — unreadable: %s", enriched.name, exc)
            continue

        source     = payload.get("source", "?")
        competitor = payload.get("competitor", "?")
        records    = payload.get("records", [])
        onestar    = [r for r in records if r.get("rating") == 1]
        if not onestar:
            continue

        def _between(lo, hi):
            lo_s, hi_s = lo.isoformat(), hi.isoformat()
            return [r for r in onestar if lo_s <= _date_key(r.get("date", "")) < hi_s]

        current  = [r for r in onestar if _date_key(r.get("date", "")) >= window_start.isoformat()]
        baseline = _between(baseline_start, window_start)

        def _pack(pool):
            silent = sum(1 for r in pool if _is_silent(r, min_chars))
            total  = len(pool)
            return silent, total, (silent / total if total else 0.0)

        cur_silent, cur_total, cur_ratio = _pack(current)
        base_silent, base_total, base_ratio = _pack(baseline)

        stats.append({
            "source":          source,
            "competitor":      competitor,
            "current_silent":  cur_silent,
            "current_total":   cur_total,
            "current_ratio":   cur_ratio,
            "baseline_silent": base_silent,
            "baseline_total":  base_total,
            "baseline_ratio":  base_ratio,
        })

    return stats


def detect_silent_wall(thresholds: dict, today_override: str | None = None) -> list[DriftAlert]:
    """
    Detect non-vocal regression spikes per source+competitor.

    Compares the current window (last `window_days`, default 14) against a
    30-day baseline preceding it. Alerts when today's silent ratio is
    `spike_multiplier_warn`x / `spike_multiplier_high`x the baseline.

    Cold-start fallback: if the baseline pool has fewer than
    `min_baseline_1star` reviews, fall back to absolute-ratio thresholds
    (`fallback_ratio_warn` / `fallback_ratio_high`) so a fresh deployment
    still gets coverage.

    Sample-size guard: skip entities with fewer than `min_silent_count`
    silent reviews in the current window.
    """
    cfg = (thresholds.get("silent_wall") or {})
    min_chars             = int(cfg.get("min_chars", 20))
    window_days           = int(cfg.get("window_days", 14))
    baseline_days         = int(cfg.get("baseline_days", 30))
    min_silent_count      = int(cfg.get("min_silent_count", 3))
    spike_mult_warn       = float(cfg.get("spike_multiplier_warn", 2.0))
    spike_mult_high       = float(cfg.get("spike_multiplier_high", 3.0))
    fallback_ratio_warn   = float(cfg.get("fallback_ratio_warn", 0.5))
    fallback_ratio_high   = float(cfg.get("fallback_ratio_high", 0.75))
    min_baseline_1star    = int(cfg.get("min_baseline_1star", 10))
    baseline_floor        = float(cfg.get("baseline_ratio_floor", 0.02))  # avoid div-by-zero inflation

    today = datetime.now(timezone.utc).date() if today_override is None else \
            datetime.fromisoformat(today_override).date()
    stats = _silent_stats_per_entity(min_chars, window_days, baseline_days, today)

    alerts: list[DriftAlert] = []
    for s in stats:
        cur_silent = s["current_silent"]
        if cur_silent < min_silent_count:
            continue

        cur_ratio  = s["current_ratio"]
        base_total = s["baseline_total"]
        base_ratio = s["baseline_ratio"]
        entity     = f"{s['source']} {s['competitor']}"

        # Primary path: baseline-relative spike detection
        if base_total >= min_baseline_1star:
            effective_baseline = max(base_ratio, baseline_floor)
            spike = cur_ratio / effective_baseline
            if spike >= spike_mult_high:
                severity, threshold_val = "HIGH", spike_mult_high
            elif spike >= spike_mult_warn:
                severity, threshold_val = "WARN", spike_mult_warn
            else:
                continue
            detail = (
                f"{cur_silent}/{s['current_total']} 1-star reviews in last {window_days}d "
                f"are silent (<{min_chars} chars): {cur_ratio:.1%}. "
                f"Baseline ({base_total} reviews over prior {baseline_days}d): {base_ratio:.1%}. "
                f"Spike: {spike:.1f}× baseline — investigate {s['competitor']} {s['source']}."
            )
            metric = round(spike, 2)
            mode = "spike"
        # Fallback: absolute-ratio thresholds (cold-start or tiny baseline)
        else:
            if cur_ratio >= fallback_ratio_high:
                severity, threshold_val = "HIGH", fallback_ratio_high
            elif cur_ratio >= fallback_ratio_warn:
                severity, threshold_val = "WARN", fallback_ratio_warn
            else:
                continue
            detail = (
                f"{cur_silent}/{s['current_total']} 1-star reviews in last {window_days}d "
                f"are silent (<{min_chars} chars): {cur_ratio:.1%}. "
                f"Baseline insufficient ({base_total} reviews < {min_baseline_1star}); "
                f"using absolute-ratio fallback — investigate {s['competitor']} {s['source']}."
            )
            metric = round(cur_ratio, 3)
            mode = "absolute_fallback"

        alerts.append(DriftAlert(
            ts        = datetime.now(timezone.utc).isoformat(),
            check     = "silent_wall",
            severity  = severity,
            entity    = entity,
            metric    = metric,
            threshold = threshold_val,
            detail    = detail,
            context   = {
                "mode":            mode,
                "window_days":     window_days,
                "baseline_days":   baseline_days,
                "current_silent":  cur_silent,
                "current_total":   s["current_total"],
                "current_ratio":   round(cur_ratio, 4),
                "baseline_silent": s["baseline_silent"],
                "baseline_total":  base_total,
                "baseline_ratio":  round(base_ratio, 4),
                "min_chars":       min_chars,
            },
        ))

    return alerts


def baseline_report(thresholds: dict | None = None) -> str:
    """Print-ready calibration table — current vs baseline silent ratio per entity."""
    cfg = ((thresholds or _load_thresholds()).get("silent_wall") or {})
    stats = _silent_stats_per_entity(
        min_chars     = int(cfg.get("min_chars", 20)),
        window_days   = int(cfg.get("window_days", 14)),
        baseline_days = int(cfg.get("baseline_days", 30)),
        today         = datetime.now(timezone.utc).date(),
    )
    if not stats:
        return "[drift] no 1-star data found in any enriched file"

    lines = [
        f"{'SOURCE':<13} {'COMPETITOR':<10} "
        f"{'CUR_SILENT/TOTAL':<18} {'CUR_RATIO':<10} "
        f"{'BASE_SILENT/TOTAL':<18} {'BASE_RATIO':<10} {'SPIKE'}",
        "-" * 96,
    ]
    for s in sorted(stats, key=lambda x: (x["source"], x["competitor"])):
        cur = f"{s['current_silent']}/{s['current_total']}"
        base = f"{s['baseline_silent']}/{s['baseline_total']}"
        spike = (s["current_ratio"] / max(s["baseline_ratio"], 0.02)
                 if s["baseline_total"] else float("nan"))
        spike_s = f"{spike:.2f}x" if s["baseline_total"] else "n/a"
        lines.append(
            f"{s['source']:<13} {s['competitor']:<10} "
            f"{cur:<18} {s['current_ratio']:<10.1%} "
            f"{base:<18} {s['baseline_ratio']:<10.1%} {spike_s}"
        )
    return "\n".join(lines)


# ── Orchestrator ─────────────────────────────────────────────────────────────

def run_drift_checks(escalate_to_slack: bool = True) -> list[DriftAlert]:
    """Run every detector, append to drift_log.jsonl, escalate HIGH to Slack."""
    thresholds = _load_thresholds()
    alerts: list[DriftAlert] = []
    alerts.extend(detect_silent_wall(thresholds))

    if alerts:
        _DRIFT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _DRIFT_LOG.open("a", encoding="utf-8") as fh:
            for a in alerts:
                fh.write(json.dumps(asdict(a)) + "\n")

    # Escalate HIGH severity to Slack (non-fatal on send failure).
    if escalate_to_slack:
        high = [a for a in alerts if a.severity == "HIGH"]
        if high:
            try:
                from mil.notify.notifier import get_notifier
                notifier = get_notifier()
                for a in high:
                    subj = f"MIL DRIFT {a.severity} — {a.check} on {a.entity}"
                    body = f"{a.detail}\n\nMetric: {a.metric}  (threshold: {a.threshold})"
                    notifier._safe_send(subj, body)
            except Exception as exc:
                logger.warning("[drift] slack escalation failed (non-fatal): %s", exc)

    return alerts


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    args = sys.argv[1:]

    if "--baseline-report" in args:
        # Calibration helper — shows current-window vs baseline silent ratios
        # per entity so thresholds can be set against real numbers.
        print(baseline_report())
        return 0

    escalate = "--no-escalate" not in args

    alerts = run_drift_checks(escalate_to_slack=escalate)
    by_sev: dict[str, int] = {}
    for a in alerts:
        by_sev[a.severity] = by_sev.get(a.severity, 0) + 1

    if not alerts:
        logger.info("[drift] no alerts — corpus within thresholds")
        return 0

    logger.info("[drift] %d alert(s): %s", len(alerts), by_sev)
    for a in alerts:
        logger.info("  [%s] %s on %s — %s", a.severity, a.check, a.entity, a.detail)
    # exit 1 if any HIGH severity; WARN/INFO do not fail the step
    return 1 if any(a.severity == "HIGH" for a in alerts) else 0


if __name__ == "__main__":
    sys.exit(main())
