"""Run the full Pulse data pipeline end-to-end.

One command to stand up the local data spine the serving API reads:
synthetic MA_D generator -> MA_S sessionisation -> daily_journey_mart.
DuckDB + PyArrow throughout. Output is the gitignored ``dist/`` tree.

Run:
    py -m pulse.pipeline.run --sessions 2000 --seed 20260522
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pulse.decision import build_decisions
from pulse.pipeline.detect_sessions import build_pipeline_session_friction
from pulse.pipeline.sessionise import sessionise
from pulse.serving.journey_mart import build_daily_journey_mart
from pulse.synthetic.generate_ma_d import GeneratorConfig, generate, write_ma_d

REPO = Path(__file__).resolve().parents[2]
DIST = REPO / "dist"


def run_pipeline(
    *,
    n_sessions: int = 2000,
    seed: int = 20260522,
    friction_rate: float = 0.35,
    ma_d_dir: str | Path | None = None,
    ma_s_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Generate -> sessionise -> build mart. Returns the chained manifests."""
    ma_d_dir = Path(ma_d_dir) if ma_d_dir else DIST / "ma_d"
    ma_s_dir = Path(ma_s_dir) if ma_s_dir else DIST / "ma_s"

    cfg = GeneratorConfig(n_sessions=n_sessions, seed=seed, friction_rate=friction_rate)
    events, labels = generate(cfg)
    ma_d = write_ma_d(events, ma_d_dir)
    ma_s = sessionise(ma_d_dir, ma_s_dir)
    mart = build_daily_journey_mart(ma_s_dir)
    friction = build_pipeline_session_friction(ma_d_dir)
    decisions = build_decisions(ma_s_dir=ma_s_dir)

    return {
        "sessions": len(labels),
        "ma_d": ma_d,
        "ma_s": ma_s,
        "daily_journey_mart": mart,
        "session_friction": friction,
        "decisions": decisions,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Run the full Pulse pipeline (MA_D -> MA_S -> marts)")
    p.add_argument("--sessions", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20260522)
    p.add_argument("--friction-rate", type=float, default=0.35)
    args = p.parse_args()
    result = run_pipeline(
        n_sessions=args.sessions, seed=args.seed, friction_rate=args.friction_rate
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
