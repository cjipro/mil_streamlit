"""
heldout_eval.py — MIL QLoRA specialist held-out evaluation (MIL-25 post-training)

Three-way blind comparison on held-out corpus samples:
  Haiku (ground truth, already labelled in enriched files)
  qwen3:14b (current enrichment baseline — the one we're trying to beat)
  qwen3-mil-v1-4b (specialist candidate — declared in model_routing.yaml
                   as `specialist_severity`, status: declared)

Exit decision: PROMOTE if the specialist meets BOTH:
  (a) P0 Haiku-agreement >= 90%  AND  P1 Haiku-agreement >= 90%
  (b) specialist beats baseline by >= 5pp on P0 OR P1 (or equals on both +
      overall improvement) — otherwise the declared route should not go live.

Hold-out guarantee: the specialist was fine-tuned on 150 severity pairs
(mil/teacher/output/severity_pairs.jsonl, built 2026-04-19). The enriched
corpus is ~7500 records. Random sampling without de-dup gives a ~2%
overlap risk in expectation, documented in the report.

Outputs:
  mil/specialist/heldout_eval_report.md   — human-readable report
  mil/specialist/heldout_eval_state.json  — machine-readable result

MIL Zero Entanglement: no imports from pulse/, poc/, app/, dags/.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("mil.heldout_eval")

_MIL_DIR      = Path(__file__).resolve().parent.parent
_REPO_ROOT    = _MIL_DIR.parent
_ENRICHED_DIR = _MIL_DIR / "data" / "historical" / "enriched"
_REPORT_MD    = Path(__file__).parent / "heldout_eval_report.md"
_STATE_JSON   = Path(__file__).parent / "heldout_eval_state.json"

sys.path.insert(0, str(_MIL_DIR))
sys.path.insert(0, str(_REPO_ROOT))

# Gate thresholds
HAIKU_AGREEMENT_THRESHOLD   = 0.90   # specialist must match Haiku at this rate on P0 and P1
UPLIFT_THRESHOLD_PP         = 5.0    # specialist must beat qwen3:14b by this margin on at least one critical class


# ── Sampling ────────────────────────────────────────────────────────────────

def _review_text(record: dict) -> str:
    """Extract the review text across source schemas (App Store, Google Play, Reddit, etc.)."""
    return (record.get("review") or record.get("content") or
            record.get("text")   or record.get("body")    or "").strip()


def _sample_records(n: int, seed: int,
                    p0_p1_weight: float = 0.5,
                    min_text_chars: int = 30) -> list[dict]:
    """
    Draw n records from all Haiku-enriched files. Filters to records with
    at least `min_text_chars` of extractable review text so the eval
    compares classifiers on real input (not empty strings). Weights
    sampling toward P0/P1 — those are the severity classes that matter
    for production routing decisions.
    """
    rng = random.Random(seed)
    all_records: list[dict] = []
    for path in sorted(_ENRICHED_DIR.glob("*_enriched.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not data.get("model", "").startswith("claude-haiku"):
            continue
        for r in data.get("records") or []:
            if r.get("severity_class") not in ("P0", "P1", "P2"):
                continue
            if len(_review_text(r)) < min_text_chars:
                continue
            all_records.append({
                **r,
                "_source":     data.get("source", "?"),
                "_competitor": data.get("competitor", "?"),
            })

    if not all_records:
        return []

    p0p1 = [r for r in all_records if r["severity_class"] in ("P0", "P1")]
    p2   = [r for r in all_records if r["severity_class"] == "P2"]

    n_p0p1 = min(int(round(n * p0_p1_weight)), len(p0p1))
    n_p2   = min(n - n_p0p1, len(p2))

    picked = rng.sample(p0p1, n_p0p1) + rng.sample(p2, n_p2)
    rng.shuffle(picked)
    return picked


# ── Specialist (qwen3-mil-v1-4b via unsloth) ────────────────────────────────

_FT_ADAPTER = Path(__file__).parent / "qwen3-mil-v1-4b"
_ft_model = None
_ft_tokenizer = None


def _load_specialist():
    """Load the fine-tuned LoRA adapter. Proven path from collision_lock.py."""
    global _ft_model, _ft_tokenizer
    if _ft_model is not None:
        return _ft_model, _ft_tokenizer
    logger.info("[specialist] loading qwen3-mil-v1-4b via unsloth (this takes ~30s) ...")
    from unsloth import FastLanguageModel
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(_FT_ADAPTER),
        max_seq_length=1024,
        load_in_4bit=True,
        dtype=None,
    )
    FastLanguageModel.for_inference(model)
    _ft_model, _ft_tokenizer = model, tokenizer
    return model, tokenizer


def _severity_prompt(review_text: str) -> str:
    return (
        "### Instruction:\n"
        "Banking app review severity classification.\n\n"
        "P0 = complete block (cannot log in at all, payment completely fails, app will not open, total loss of access).\n"
        "P1 = significant friction (repeated failures, feature broken after update, cannot complete key action after retrying).\n"
        "P2 = minor annoyance, cosmetic issue, or positive review.\n\n"
        f'Review: "{review_text[:300]}"\n\n'
        "Return valid JSON with severity_class and reasoning.\n\n"
        "### Response:\n"
    )


def _parse_severity(decoded: str) -> str:
    """
    Extract P0|P1|P2 from the model's response. Three passes, most strict first:
      1. Parse the first JSON object and read severity_class
      2. Regex for 'severity... : P0/P1/P2'
      3. Last resort: first P0|P1|P2 token anywhere in the response
    """
    # Pass 1: JSON
    brace_start = decoded.find("{")
    if brace_start != -1:
        depth, end = 0, -1
        for i, ch in enumerate(decoded[brace_start:], brace_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end != -1:
            try:
                obj = json.loads(decoded[brace_start:end + 1])
                sev = obj.get("severity_class", "")
                if sev in ("P0", "P1", "P2"):
                    return sev
            except Exception:
                pass
    # Pass 2: "severity...: P0"
    m = re.search(r"[Ss]everity[\s\w]*:\s*(P[012])", decoded)
    if m:
        return m.group(1)
    # Pass 3: any P0/P1/P2 as a standalone token
    m = re.search(r"\b(P[012])\b", decoded)
    return m.group(1) if m else "UNKNOWN"


def _classify_specialist(review_text: str) -> str:
    import torch
    if not review_text:
        return "UNKNOWN"
    try:
        model, tokenizer = _load_specialist()
        inputs = tokenizer(_severity_prompt(review_text), return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=200,
                temperature=0.01,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        decoded = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        return _parse_severity(decoded)
    except Exception as exc:
        logger.warning("[specialist] classify failed: %s", exc)
        return "UNKNOWN"


# ── Baseline (qwen3:14b via native Ollama API with think=False) ────────────
# OpenAI-compat doesn't expose Qwen3's `think` option — without it, the
# model's hidden reasoning burns through max_tokens before emitting JSON.
# Native /api/chat accepts `think: false` which returns a clean short JSON.

import urllib.request


def _classify_baseline(review_text: str) -> str:
    if not review_text:
        return "UNKNOWN"
    payload = {
        "model":    "qwen3:14b",
        "messages": [
            {"role": "system", "content": "You classify banking app review severity. Respond with JSON only: {\"severity_class\": \"P0|P1|P2\"}. No prose."},
            {"role": "user", "content": _severity_prompt(review_text)},
        ],
        "stream":  False,
        "think":   False,   # skip Qwen3's reasoning preamble
        "options": {"temperature": 0.01, "num_predict": 200},
    }
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        return _parse_severity((data.get("message") or {}).get("content", ""))
    except Exception as exc:
        logger.warning("[baseline] qwen3:14b classify failed: %s", exc)
        return "UNKNOWN"


# ── Orchestration ───────────────────────────────────────────────────────────

def run_eval(n: int = 30, seed: int = 20260419, skip_baseline: bool = False) -> dict:
    records = _sample_records(n, seed)
    if not records:
        return {"status": "ERROR", "reason": "no Haiku-labeled records found"}

    print(f"\n[heldout_eval] running on {len(records)} samples (seed={seed})")
    print(f"  specialist: qwen3-mil-v1-4b  (via unsloth)")
    print(f"  baseline:   qwen3:14b        (via Ollama)" if not skip_baseline else
          f"  baseline:   SKIPPED (--no-baseline)")
    print(f"  truth:      Haiku (claude-haiku-4-5-20251001, labels in enriched files)\n")

    per_record = []
    for i, rec in enumerate(records, 1):
        text = _review_text(rec)[:300]
        haiku = rec.get("severity_class", "?")
        spec  = _classify_specialist(text)
        base  = _classify_baseline(text) if not skip_baseline else "SKIP"
        per_record.append({
            "idx":        i,
            "source":     rec.get("_source"),
            "competitor": rec.get("_competitor"),
            "review":     text[:80],
            "haiku":      haiku,
            "baseline":   base,
            "specialist": spec,
            "b_match":    base == haiku if base != "SKIP" else None,
            "s_match":    spec == haiku,
        })
        b_flag = ("OK" if base == haiku else "X ") if base != "SKIP" else "  "
        s_flag = "OK" if spec == haiku else "X "
        print(f"  [{i:02d}] haiku={haiku}  base={base:<8} {b_flag}  spec={spec:<8} {s_flag}")

    # Aggregate
    def _agreement(sev: str, col: str) -> tuple[int, int]:
        targets = [r for r in per_record if r["haiku"] == sev]
        matches = [r for r in targets if r[col] == sev]
        return len(matches), len(targets)

    spec_p0_m, p0_n = _agreement("P0", "specialist")
    spec_p1_m, p1_n = _agreement("P1", "specialist")
    spec_p2_m, p2_n = _agreement("P2", "specialist")
    spec_overall = sum(1 for r in per_record if r["specialist"] == r["haiku"]) / len(per_record)

    if skip_baseline:
        base_p0_m = base_p1_m = base_p2_m = 0
        base_overall = 0.0
    else:
        base_p0_m, _ = _agreement("P0", "baseline")
        base_p1_m, _ = _agreement("P1", "baseline")
        base_p2_m, _ = _agreement("P2", "baseline")
        base_overall = sum(1 for r in per_record if r["baseline"] == r["haiku"]) / len(per_record)

    def _pct(m, n): return (m / n) if n else 0.0

    spec_p0_acc = _pct(spec_p0_m, p0_n)
    spec_p1_acc = _pct(spec_p1_m, p1_n)
    spec_p2_acc = _pct(spec_p2_m, p2_n)
    base_p0_acc = _pct(base_p0_m, p0_n)
    base_p1_acc = _pct(base_p1_m, p1_n)
    base_p2_acc = _pct(base_p2_m, p2_n)

    # Decision
    meets_gate = spec_p0_acc >= HAIKU_AGREEMENT_THRESHOLD and spec_p1_acc >= HAIKU_AGREEMENT_THRESHOLD
    uplift_p0  = (spec_p0_acc - base_p0_acc) * 100
    uplift_p1  = (spec_p1_acc - base_p1_acc) * 100
    meaningful_uplift = (not skip_baseline) and (uplift_p0 >= UPLIFT_THRESHOLD_PP or uplift_p1 >= UPLIFT_THRESHOLD_PP)
    decision = "PROMOTE" if (meets_gate and (meaningful_uplift or skip_baseline)) else "KEEP"

    result = {
        "ts":          datetime.now(timezone.utc).isoformat(),
        "n_samples":   len(per_record),
        "seed":        seed,
        "haiku_agreement_threshold": HAIKU_AGREEMENT_THRESHOLD,
        "uplift_threshold_pp":       UPLIFT_THRESHOLD_PP,
        "specialist": {
            "p0_acc":  round(spec_p0_acc, 3), "p0_n": p0_n, "p0_matches": spec_p0_m,
            "p1_acc":  round(spec_p1_acc, 3), "p1_n": p1_n, "p1_matches": spec_p1_m,
            "p2_acc":  round(spec_p2_acc, 3), "p2_n": p2_n, "p2_matches": spec_p2_m,
            "overall": round(spec_overall, 3),
        },
        "baseline":   {
            "p0_acc":  round(base_p0_acc, 3), "p0_matches": base_p0_m,
            "p1_acc":  round(base_p1_acc, 3), "p1_matches": base_p1_m,
            "p2_acc":  round(base_p2_acc, 3), "p2_matches": base_p2_m,
            "overall": round(base_overall, 3),
        } if not skip_baseline else {"skipped": True},
        "uplift_p0_pp": round(uplift_p0, 1) if not skip_baseline else None,
        "uplift_p1_pp": round(uplift_p1, 1) if not skip_baseline else None,
        "meets_haiku_gate":    meets_gate,
        "meaningful_uplift":   meaningful_uplift,
        "decision":            decision,
        "per_record":          per_record,
    }
    return result


# ── Reporting ───────────────────────────────────────────────────────────────

def _write_markdown(result: dict) -> None:
    s = result["specialist"]
    b = result["baseline"]
    lines = [
        "# MIL Specialist — Held-out Evaluation Report",
        "",
        f"- **Generated**: {result['ts']}",
        f"- **Samples**: {result['n_samples']}  (seed={result['seed']})",
        f"- **Haiku threshold**: {int(result['haiku_agreement_threshold']*100)}% on P0 and P1",
        f"- **Uplift threshold**: +{result['uplift_threshold_pp']}pp over baseline on P0 or P1",
        "",
        "## Summary",
        "",
        "| Model | Overall | P0 | P1 | P2 |",
        "|---|---:|---:|---:|---:|",
        f"| **Haiku** (ground truth) | 1.000 | 1.000 ({s['p0_n']}) | 1.000 ({s['p1_n']}) | 1.000 ({s['p2_n']}) |",
    ]
    if b.get("skipped"):
        lines.append("| **qwen3:14b** baseline | _skipped (--no-baseline)_ | | | |")
    else:
        lines.append(
            f"| **qwen3:14b** baseline | {b['overall']:.1%} | "
            f"{b['p0_acc']:.1%} | {b['p1_acc']:.1%} | {b['p2_acc']:.1%} |"
        )
    lines.append(
        f"| **qwen3-mil-v1-4b** specialist | {s['overall']:.1%} | "
        f"{s['p0_acc']:.1%} | {s['p1_acc']:.1%} | {s['p2_acc']:.1%} |"
    )
    lines += ["", "## Gate"]
    lines.append(f"- Specialist ≥ 90% on P0: **{'PASS' if s['p0_acc'] >= 0.9 else 'FAIL'}** ({s['p0_acc']:.1%})")
    lines.append(f"- Specialist ≥ 90% on P1: **{'PASS' if s['p1_acc'] >= 0.9 else 'FAIL'}** ({s['p1_acc']:.1%})")
    if not b.get("skipped"):
        lines.append(f"- P0 uplift vs qwen3:14b: **{result['uplift_p0_pp']:+.1f}pp**")
        lines.append(f"- P1 uplift vs qwen3:14b: **{result['uplift_p1_pp']:+.1f}pp**")
    lines += [
        "",
        f"## Decision: **{result['decision']}**",
        "",
        ("Promote `status: declared` → `status: live` in `mil/config/model_routing.yaml` "
         "(still requires GGUF deploy + spot-check)." if result['decision'] == "PROMOTE" else
         "Do not promote. Investigate specialist failures on P0/P1 samples where haiku and specialist disagree; "
         "consider retraining with additional pairs covering the missed patterns."),
        "",
        "## Per-record detail",
        "",
        "| # | Source | Haiku | Baseline | Specialist | Review snippet |",
        "|---|---|---|---|---|---|",
    ]
    for r in result["per_record"]:
        b_cell = r["baseline"] if r["baseline"] != "SKIP" else "—"
        b_mark = " ✓" if r.get("b_match") else (" ✗" if r.get("b_match") is False else "")
        s_mark = " ✓" if r["s_match"] else " ✗"
        review = r["review"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {r['idx']} | {r['source']}/{r['competitor']} | {r['haiku']} | "
            f"{b_cell}{b_mark} | {r['specialist']}{s_mark} | {review} |"
        )

    _REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    ap = argparse.ArgumentParser(description="MIL specialist held-out eval")
    ap.add_argument("-n",      type=int, default=30,       help="sample size")
    ap.add_argument("--seed",  type=int, default=20260419, help="random seed (reproducibility)")
    ap.add_argument("--no-baseline", action="store_true",  help="skip qwen3:14b baseline (specialist-only sanity check)")
    args = ap.parse_args()

    result = run_eval(n=args.n, seed=args.seed, skip_baseline=args.no_baseline)

    if result.get("status") == "ERROR":
        print(f"\n[ERROR] {result.get('reason')}")
        return 2

    _STATE_JSON.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    _write_markdown(result)

    s = result["specialist"]; b = result["baseline"]
    print("\n" + "=" * 70)
    print("  HELD-OUT EVAL RESULTS")
    print("=" * 70)
    print(f"  Specialist overall: {s['overall']:.1%}  "
          f"P0={s['p0_acc']:.1%} ({s['p0_matches']}/{s['p0_n']})  "
          f"P1={s['p1_acc']:.1%} ({s['p1_matches']}/{s['p1_n']})  "
          f"P2={s['p2_acc']:.1%} ({s['p2_matches']}/{s['p2_n']})")
    if not b.get("skipped"):
        print(f"  Baseline   overall: {b['overall']:.1%}  "
              f"P0={b['p0_acc']:.1%}  P1={b['p1_acc']:.1%}  P2={b['p2_acc']:.1%}")
        print(f"  Uplift:            P0={result['uplift_p0_pp']:+.1f}pp  P1={result['uplift_p1_pp']:+.1f}pp")
    print(f"  Decision:          {result['decision']}")
    print(f"  Report:            {_REPORT_MD}")
    print(f"  State:             {_STATE_JSON}")
    print("=" * 70 + "\n")

    return 0 if result["decision"] == "PROMOTE" else 1


if __name__ == "__main__":
    sys.exit(main())
