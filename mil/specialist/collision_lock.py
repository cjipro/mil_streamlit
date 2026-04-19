"""
collision_lock.py — MIL QLoRA Gate 5

Prevents QLoRA-trained qwen3 from being used if it produces severity
classifications that conflict with the Haiku enrichment baseline.

Runs a 20-record spot-check:
  - Enriches a sample with Haiku (ground truth)
  - Gets severity classification from qwen3:14b for the same records
  - Compares P0/P1 agreement rate

Result:
  ACTIVE  — P0/P1 agreement >= 90%  → training permitted
  LOCKED  — P0/P1 agreement < 90%   → training blocked

State saved to: mil/specialist/lock_state.json

Usage:
  py mil/specialist/collision_lock.py          # run check + save state
  py mil/specialist/collision_lock.py --status # print current saved state

MIL Zero Entanglement: no imports from pulse/, poc/, app/, dags/
"""
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("mil.collision_lock")

MIL_DIR    = Path(__file__).resolve().parent.parent
REPO_ROOT  = MIL_DIR.parent
ENRICHED_DIR = MIL_DIR / "data" / "historical" / "enriched"
STATE_FILE = Path(__file__).parent / "lock_state.json"

sys.path.insert(0, str(MIL_DIR))
sys.path.insert(0, str(REPO_ROOT))

AGREEMENT_THRESHOLD = 0.90
SAMPLE_SIZE         = 20


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_sample_records(n: int = SAMPLE_SIZE) -> list[dict]:
    """Load n enriched records from the existing enriched files (already Haiku-classified)."""
    records = []
    for path in sorted(ENRICHED_DIR.glob("*_enriched.json")):
        try:
            data  = json.loads(path.read_text(encoding="utf-8"))
            # Records are under data["records"] (schema v3 wrapper format)
            batch = data.get("records", []) if isinstance(data, dict) else data
            # Only records that have severity_class (Haiku-enriched)
            v3 = [r for r in batch if r.get("severity_class")]
            records.extend(v3)
        except Exception:
            pass
    if not records:
        return []
    # Prioritise P0/P1 — most important for the check
    p0p1  = [r for r in records if r.get("severity_class") in ("P0", "P1")]
    rest  = [r for r in records if r.get("severity_class") not in ("P0", "P1")]
    pool  = (p0p1 + rest)[:n]
    return pool


FINETUNED_ADAPTER = Path(__file__).parent / "qwen3-mil-v1-4b"
FINETUNED_BASE_ID  = "unsloth/Qwen3-4B-unsloth-bnb-4bit"

_ft_model = None
_ft_tokenizer = None

def _load_finetuned():
    """Load fine-tuned Qwen3-4B LoRA adapter (cached after first call)."""
    global _ft_model, _ft_tokenizer
    if _ft_model is not None:
        return _ft_model, _ft_tokenizer
    from unsloth import FastLanguageModel
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(FINETUNED_ADAPTER),
        max_seq_length=1024,
        load_in_4bit=True,
        dtype=None,
    )
    FastLanguageModel.for_inference(model)
    _ft_model, _ft_tokenizer = model, tokenizer
    return model, tokenizer


def _classify_with_qwen3(record: dict) -> str:
    """Classify severity using the fine-tuned Qwen3-4B LoRA model."""
    import re
    import torch
    text = (record.get("review") or record.get("review_text") or record.get("text") or record.get("body") or "")[:300]
    if not text:
        return "P2"

    prompt = (
        "### Instruction:\n"
        "Banking app review severity classification.\n\n"
        "P0 = complete block (cannot log in at all, payment completely fails, app will not open, total loss of access).\n"
        "P1 = significant friction (repeated failures, feature broken after update, cannot complete key action after retrying).\n"
        "P2 = minor annoyance, cosmetic issue, or positive review.\n\n"
        f'Review: "{text}"\n\n'
        "Return valid JSON with severity_class and reasoning.\n\n"
        "### Response:\n"
    )

    try:
        model, tokenizer = _load_finetuned()
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=200,
                temperature=0.01,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        decoded = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()

        # Try JSON extraction first (severity pair format)
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
                    result = json.loads(decoded[brace_start:end + 1])
                    sev = result.get("severity_class", "")
                    if sev in ("P0", "P1", "P2"):
                        return sev
                except Exception:
                    pass

        # Fallback: extract from inline text (CAC inference format)
        # e.g. "Severity classification: P1." or "severity: P0"
        sev_match = re.search(r'[Ss]everity[\s\w]*:\s*(P[012])', decoded)
        if sev_match:
            return sev_match.group(1)

        logger.debug("could not parse severity from: %s", decoded[:150])
        return "UNKNOWN"
    except Exception as exc:
        logger.warning("fine-tuned model classification failed: %s", exc)
        return "UNKNOWN"
    except Exception as exc:
        logger.warning("qwen3 classification failed: %s", exc)
        return "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────────
# Core lock check
# ─────────────────────────────────────────────────────────────────────────────

def check_lock(sample_size: int = SAMPLE_SIZE) -> dict:
    """
    Run collision check. Compares Haiku severity (ground truth, already in
    enriched files) against qwen3:14b classification on the same records.

    Returns lock state dict and saves to lock_state.json.
    """
    records = _load_sample_records(sample_size)
    if not records:
        state = {
            "status":        "LOCKED",
            "checked_at":    datetime.now(timezone.utc).isoformat(),
            "p0_agreement":  0.0,
            "p1_agreement":  0.0,
            "overall_agreement": 0.0,
            "sample_size":   0,
            "reason":        "No enriched records found — cannot verify.",
        }
        _save_state(state)
        return state

    print(f"\n[collision_lock] checking {len(records)} records (Haiku baseline vs qwen3:14b)\n")

    haiku_sev = []
    qwen_sev  = []
    for i, rec in enumerate(records):
        h_sev = rec.get("severity_class", "P2")
        q_sev = _classify_with_qwen3(rec)
        haiku_sev.append(h_sev)
        qwen_sev.append(q_sev)
        match = "OK" if h_sev == q_sev else "MISMATCH"
        print(f"  [{i+1:02d}] Haiku={h_sev}  qwen3={q_sev:<8}  {match}")

    total   = len(records)
    p0_haiku = [i for i, s in enumerate(haiku_sev) if s == "P0"]
    p1_haiku = [i for i, s in enumerate(haiku_sev) if s == "P1"]

    def _agreement(indices):
        if not indices:
            return 1.0
        return sum(1 for i in indices if qwen_sev[i] == haiku_sev[i]) / len(indices)

    p0_agr   = _agreement(p0_haiku)
    p1_agr   = _agreement(p1_haiku)
    overall  = sum(1 for h, q in zip(haiku_sev, qwen_sev) if h == q) / total

    # Gate: P0 agreement and P1 agreement both >= threshold
    # (If there are no P0 records in sample, P0 agreement defaults to 1.0)
    passed = (p0_agr >= AGREEMENT_THRESHOLD and p1_agr >= AGREEMENT_THRESHOLD)
    status = "ACTIVE" if passed else "LOCKED"
    reason = (
        "P0/P1 agreement meets threshold — training permitted."
        if passed
        else (
            f"P0 agreement {p0_agr:.1%} or P1 agreement {p1_agr:.1%} "
            f"below {AGREEMENT_THRESHOLD:.0%} threshold — training blocked."
        )
    )

    state = {
        "status":            status,
        "checked_at":        datetime.now(timezone.utc).isoformat(),
        "p0_agreement":      round(p0_agr, 3),
        "p1_agreement":      round(p1_agr, 3),
        "overall_agreement": round(overall, 3),
        "sample_size":       total,
        "p0_sample_n":       len(p0_haiku),
        "p1_sample_n":       len(p1_haiku),
        "threshold":         AGREEMENT_THRESHOLD,
        "reason":            reason,
    }
    _save_state(state)

    print(f"\n{'='*60}")
    print(f"  Collision Lock — Gate 5 Check")
    print(f"  Sample:          {total} records")
    print(f"  P0 agreement:    {p0_agr:.1%}  (n={len(p0_haiku)})")
    print(f"  P1 agreement:    {p1_agr:.1%}  (n={len(p1_haiku)})")
    print(f"  Overall:         {overall:.1%}")
    print(f"  Threshold:       {AGREEMENT_THRESHOLD:.0%}")
    print(f"  Gate 5 result:   {status}")
    print(f"  Reason:          {reason}")
    print(f"{'='*60}\n")

    return state


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def is_active() -> bool:
    """Return True if lock state is ACTIVE (gate 5 passes)."""
    if not STATE_FILE.exists():
        return False
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return state.get("status") == "ACTIVE"
    except Exception:
        return False


def get_state() -> dict:
    if not STATE_FILE.exists():
        return {"status": "UNCHECKED", "reason": "check_lock() has not been run yet"}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "ERROR", "reason": "could not read lock_state.json"}


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="MIL Collision Lock — Gate 5")
    parser.add_argument("--status", action="store_true", help="Print saved lock state and exit")
    parser.add_argument("--n",      type=int, default=SAMPLE_SIZE, help=f"Sample size (default: {SAMPLE_SIZE})")
    args = parser.parse_args()

    if args.status:
        state = get_state()
        print(json.dumps(state, indent=2))
        sys.exit(0 if state.get("status") == "ACTIVE" else 1)

    state = check_lock(sample_size=args.n)
    sys.exit(0 if state["status"] == "ACTIVE" else 1)


if __name__ == "__main__":
    main()
