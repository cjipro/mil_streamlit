"""Synthetic MA_D generator (PULSE-28).

Deterministic, self-contained generator of synthetic raw journey telemetry in the
TAQ source-event shape (per `pulse/contracts/taq_contract.yaml`), run through the
TAQ adapter into the canonical Pulse event shape — the **MA_D layer** (one row per
raw event). Output is persisted as Hive-partitioned Parquet for the DuckDB
sessionisation + marts pipeline downstream.

No TAQ-app or real-bank dependency: this emits the `taq` source shape directly,
so it unblocks the whole pipeline without external data access. `source` stays
`taq` (synthetic) per the naming-discipline lock — never a real bank name.

Run:
    py -m pulse.synthetic.generate_ma_d --sessions 2000 --seed 20260522 --out dist/ma_d
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.parquet as pq

from pulse.adapters.taq import TAQAdapter

# ── journey + screen vocabulary ──────────────────────────────────────────────
# journey_id values MUST exist in pulse/contracts/journey_taxonomy.yaml.
# The four friction-target screens (v1 12-cell scope) are the last form-step
# screen of their journey, where signatures are planted.

FRICTION_TARGETS: dict[str, str] = {
    "loans": "loans.apply.step3",
    "international": "international.beneficiary.setup",
    "cards": "cards.credit.apply.eligibility",
    "investments": "investments.premier.portfolio.overview",
}

JOURNEY_SCREENS: dict[str, list[str]] = {
    "loans": ["loans.browse", "loans.apply.step1", "loans.apply.step2",
              "loans.apply.step3", "loans.apply.confirm"],
    "international": ["international.home", "international.beneficiary.setup",
                      "international.amount", "international.review", "international.confirm"],
    "cards": ["cards.home", "cards.credit.apply.eligibility",
              "cards.credit.apply.details", "cards.credit.apply.confirm"],
    "investments": ["investments.home", "investments.premier.portfolio.overview",
                    "investments.premier.holdings", "investments.premier.trade"],
    "payments": ["payments.home", "payments.payee.select", "payments.amount",
                 "payments.review", "payments.confirm"],
    "auth": ["auth.login", "auth.mfa"],
    "dashboard": ["dashboard.home"],
    "accounts": ["accounts.summary", "accounts.detail"],
}

# Journey mix — weighted toward the four friction-target journeys so the corpus
# has signal density on the screens the v1 detectors own.
JOURNEY_WEIGHTS: dict[str, float] = {
    "loans": 3.0, "international": 3.0, "cards": 3.0, "investments": 3.0,
    "payments": 2.0, "auth": 1.5, "dashboard": 1.0, "accounts": 1.0,
}

SIGNATURES = ["dwell_after_error", "multi_back_press", "abandon_before_submit"]
COHORTS = [["over_50"], ["premier"], ["mobile"], ["vulnerable_flag"], []]

_TAQ = TAQAdapter()


@dataclass(frozen=True)
class GeneratorConfig:
    n_sessions: int = 2000
    seed: int = 20260522
    friction_rate: float = 0.35  # P(a friction-target session plants a signature)
    start: str = "2026-05-20T09:00:00Z"


# ── source-event construction ────────────────────────────────────────────────


def _src_event(
    *, event_id: str, session_id: str, subject_id: str, cohort: list[str], journey_id: str,
    screen_id: str, sequence_no: int, event_type: str, ts: str, payload: dict[str, Any],
) -> dict[str, Any]:
    """One TAQ source event, wrapped in the `events` container the contract expects."""
    return {
        "events": {
            "event_id": event_id,
            "session_id": session_id,
            "synthetic_customer_id": subject_id,
            "synthetic_cohort_tags": cohort,
            "journey_id": journey_id,
            "screen_id": screen_id,
            "sequence_no": sequence_no,
            "event_type": event_type,
            "ts": ts,
            "payload": payload,
        }
    }


def _gen_session(rng: random.Random, base_ts: dt.datetime, cfg: GeneratorConfig
                 ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate one synthetic session's source events + a ground-truth label row.

    Returns (source_events, label). Sessions walk their journey's screens in order;
    friction-target journeys plant a signature on the target screen at friction_rate.
    """
    journey_id = rng.choices(list(JOURNEY_WEIGHTS), weights=list(JOURNEY_WEIGHTS.values()))[0]
    screens = JOURNEY_SCREENS[journey_id]
    target = FRICTION_TARGETS.get(journey_id)
    # RNG-derived (not uuid4) so the corpus is fully deterministic for a given seed.
    session_id = f"{rng.getrandbits(128):032x}"
    subject_id = hashlib.sha256(f"subj-{rng.random()}".encode()).hexdigest()[:16]
    cohort = list(rng.choice(COHORTS))

    plant = bool(target) and rng.random() < cfg.friction_rate
    signature = rng.choice(SIGNATURES) if plant else None

    events: list[dict[str, Any]] = []
    seq = 0
    t = base_ts
    abandoned = False

    def emit(screen: str, etype: str, payload: dict[str, Any], gap: int) -> None:
        nonlocal seq, t
        seq += 1
        t = t + dt.timedelta(seconds=gap)
        events.append(_src_event(
            event_id=f"{session_id}-{seq}",
            session_id=session_id, subject_id=subject_id, cohort=cohort,
            journey_id=journey_id, screen_id=screen,
            sequence_no=seq, event_type=etype, ts=_iso(t), payload=payload,
        ))

    for screen in screens:
        emit(screen, "screen_view", {"from": "nav"}, rng.randint(1, 4))

        if screen == target and signature:
            abandoned = _plant_signature(signature, screen, emit, rng)
            if abandoned:
                break  # abandon_before_submit ends the session on the target screen
            continue

        # normal screen: maybe a field interaction, then move on
        if "step" in screen or "setup" in screen or "amount" in screen:
            emit(screen, "field_blur", {"field": "amount", "was_filled": True}, rng.randint(2, 8))
        emit(screen, "dwell", {"duration_seconds": float(rng.randint(3, 25))}, rng.randint(3, 25))
        if screen != screens[-1]:
            emit(screen, "nav_intent", {"action": "forward"}, rng.randint(1, 3))

    completed = (not abandoned) and events[-1]["events"]["screen_id"] == screens[-1]
    label = {
        "session_id": session_id, "journey_id": journey_id,
        "planted_signature": signature or "none",
        "outcome": "abandoned" if abandoned else ("completed" if completed else "dropped"),
    }
    return events, label


def _plant_signature(signature: str, screen: str, emit, rng: random.Random) -> bool:
    """Plant a friction signature on the target screen. Returns True if the session abandons."""
    if signature == "dwell_after_error":
        emit(screen, "error", {"error_type": "validation_error", "field": "income"}, rng.randint(2, 5))
        emit(screen, "dwell", {"duration_seconds": float(rng.randint(55, 120))}, rng.randint(55, 120))
        emit(screen, "retry", {"what": "submit", "attempt_n": 2}, rng.randint(2, 6))
        return False
    if signature == "multi_back_press":
        for _ in range(rng.randint(3, 5)):
            emit(screen, "back_press", {"from_screen": screen}, rng.randint(3, 15))
        return False
    # abandon_before_submit: long dwell then exit without submit
    emit(screen, "dwell", {"duration_seconds": float(rng.randint(90, 240))}, rng.randint(90, 240))
    emit(screen, "hesitation_signal", {"kind": "focus_thrashing", "confidence": 0.8}, rng.randint(2, 6))
    emit(screen, "nav_intent", {"action": "exit"}, rng.randint(1, 3))
    return True


def _iso(t: dt.datetime) -> str:
    """ISO 8601 UTC, second precision with Z — matches the canonical schema regex."""
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── generation + canonicalisation ────────────────────────────────────────────


def generate(cfg: GeneratorConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Generate canonical MA_D events + per-session labels. Deterministic for a given seed."""
    rng = random.Random(cfg.seed)
    base = dt.datetime.fromisoformat(cfg.start.replace("Z", "+00:00"))

    source_events: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    for _ in range(cfg.n_sessions):
        # spread sessions across ~14 days so downstream date partitioning is meaningful
        offset = dt.timedelta(minutes=rng.randint(0, 14 * 24 * 60))
        evs, label = _gen_session(rng, base + offset, cfg)
        source_events.extend(evs)
        labels.append(label)

    batch_hash = hashlib.sha256(
        json.dumps(source_events, sort_keys=True).encode()
    ).hexdigest()

    canonical = [_TAQ.ingest(ev, batch_hash) for ev in source_events]
    return canonical, labels


def _flatten(event: dict[str, Any]) -> dict[str, Any]:
    """Flatten a canonical event into a single MA_D row (payload as JSON string)."""
    env, idn, ctx, evt = event["envelope"], event["identity"], event["context"], event["event"]
    return {
        "pulse_event_id": env["pulse_event_id"],
        "source": env["source"],
        "source_event_id": env["source_event_id"],
        "ingest_ts": env["ingest_ts"],
        "ingest_pipeline_version": env["ingest_pipeline_version"],
        "ingest_batch_hash": env["ingest_batch_hash"],
        "contract_version": env["contract_version"],
        "session_id": idn["session_id"],
        "subject_id": idn["subject_id"],
        "cohort_tags": idn["cohort_tags"],
        "journey_id": ctx["journey_id"],
        "journey_category": ctx["journey_category"],
        "screen_id": ctx["screen_id"],
        "sequence_no": ctx["sequence_no"],
        "event_type": evt["event_type"],
        "event_ts": evt["event_ts"],
        "event_date": evt["event_ts"][:10],
        "payload_json": json.dumps(evt["payload"], sort_keys=True),
    }


def write_ma_d(events: Iterable[dict[str, Any]], out_dir: str | Path) -> dict[str, Any]:
    """Write canonical MA_D events to Hive-partitioned Parquet (partitioned by journey_id).

    Returns a small manifest (row count, partition count, snapshot id)."""
    rows = [_flatten(e) for e in events]
    table = pa.Table.from_pylist(rows)
    out = Path(out_dir)
    # Idempotent: clear any prior dataset so re-runs don't append/double rows.
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    pq.write_to_dataset(table, root_path=str(out), partition_cols=["journey_id"])
    # Key the snapshot on content (deterministic source_event_id), NOT the
    # adapter-stamped pulse_event_id (a fresh uuid4 per ingest, non-deterministic).
    snapshot_id = hashlib.sha256(
        "".join(sorted(r["source_event_id"] for r in rows)).encode()
    ).hexdigest()[:16]
    journeys = sorted({r["journey_id"] for r in rows})
    manifest = {
        "layer": "ma_d",
        "row_count": len(rows),
        "partitions": journeys,
        "snapshot_id": snapshot_id,
        "out_dir": str(out),
    }
    (out / "_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description="Synthetic MA_D generator (PULSE-28)")
    p.add_argument("--sessions", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20260522)
    p.add_argument("--friction-rate", type=float, default=0.35)
    p.add_argument("--out", type=str, default="dist/ma_d")
    args = p.parse_args()

    cfg = GeneratorConfig(n_sessions=args.sessions, seed=args.seed, friction_rate=args.friction_rate)
    events, labels = generate(cfg)
    manifest = write_ma_d(events, args.out)
    n_abandoned = sum(1 for x in labels if x["outcome"] == "abandoned")
    print(json.dumps({
        **manifest,
        "sessions": len(labels),
        "abandoned_sessions": n_abandoned,
        "events_per_session": round(manifest["row_count"] / max(len(labels), 1), 1),
    }, indent=2))


if __name__ == "__main__":
    main()
