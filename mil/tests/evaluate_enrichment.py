#!/usr/bin/env python3
"""
mil/tests/evaluate_enrichment.py — Model comparison against human-labeled eval set.

Usage:
  # Haiku baseline (Anthropic API):
  py mil/tests/evaluate_enrichment.py --file mil/tests/spot_check_2026-04-18.json --model haiku

  # Refuel-8B baseline (Ollama):
  py mil/tests/evaluate_enrichment.py --file mil/tests/spot_check_2026-04-18.json --model refuel

  # Fine-tuned model via unsloth (no Ollama / GGUF needed):
  py mil/tests/evaluate_enrichment.py --file mil/tests/spot_check_2026-04-18.json --model unsloth-local --label fine_tuned_v1

  # Fine-tuned model post-training (Ollama, after GGUF export):
  py mil/tests/evaluate_enrichment.py --file mil/tests/spot_check_2026-04-18.json --model qwen3-mil-ft

Gate: fine-tuned model must beat Haiku P0/P1 agreement rate. If not, do not swap routing.

Appends to mil/data/enrichment_accuracy_log.jsonl with model name + date.
"""
import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluate_enrichment")

MIL_ROOT     = Path(__file__).parent.parent
ACCURACY_LOG = MIL_ROOT / "data" / "enrichment_accuracy_log.jsonl"

ISSUE_TYPES = [
    "App Not Opening", "App Crashing", "Login Failed", "Payment Failed",
    "Transfer Failed", "Biometric / Face ID Issue", "Card Frozen or Blocked",
    "Slow Performance", "Feature Broken", "Notification Issue", "Account Locked",
    "Missing Transaction", "Incorrect Balance", "Customer Support Failure",
    "Positive Feedback", "Other",
]
CUSTOMER_JOURNEYS = [
    "Log In to Account", "Make a Payment", "Transfer Money",
    "Check Balance or Statement", "Open or Register Account",
    "Apply for Loan or Overdraft", "Manage Card", "Get Support", "General App Use",
]
BLOCKING_ISSUES = {
    "App Not Opening", "Login Failed", "Payment Failed",
    "Transfer Failed", "Account Locked", "App Crashing",
}
SEVERITY_CLASSES = ["P0", "P1", "P2"]

SYSTEM_PROMPT = (
    "You are a banking app complaints analyst. "
    "Output MUST be a valid JSON array only. "
    "No preamble, no markdown, no explanation outside the JSON."
)
BATCH_PROMPT_TEMPLATE = """Classify each numbered banking app review. Return a JSON array with one object per review.

Each object must have exactly these fields:
- issue_type: what went wrong. One of: {issues}
- customer_journey: what the customer was trying to do. One of: {journeys}
- sentiment_score: number from -1.0 (very negative) to 1.0 (very positive)
- severity_class: P0, P1, or P2 using these rules:
    P0 = complete block (cannot log in at all, payment completely fails, app will not open, total loss of access)
    P1 = significant friction (repeated failures, feature broken after update, cannot complete key action after retrying)
    P2 = minor annoyance, cosmetic issue, or positive review
- reasoning: one sentence explaining the severity choice

Reviews:
{reviews}"""


# ── Normalise ─────────────────────────────────────────────────────────────────

def _normalise(obj: dict) -> dict:
    issue = obj.get("issue_type", "Other")
    if issue not in ISSUE_TYPES:
        issue = "Other"

    severity = obj.get("severity_class", "P2")
    if severity not in SEVERITY_CLASSES:
        severity = "P2"
    if severity in ("P0", "P1") and issue not in BLOCKING_ISSUES:
        severity = "P2"
    if issue == "Positive Feedback":
        severity = "P2"

    return {"issue_type": issue, "severity_class": severity}


# ── Model backends ─────────────────────────────────────────────────────────────

def _classify_anthropic(records: list[dict], model_id: str) -> list[dict]:
    import anthropic
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=api_key)

    results = []
    batch_size = 10
    for i in range(0, len(records), batch_size):
        batch = records[i: i + batch_size]
        lines = [
            f"{j+1}. [rating {r.get('rating', '?')}/5] {r['text'][:300]}"
            for j, r in enumerate(batch)
        ]
        prompt = BATCH_PROMPT_TEMPLATE.format(
            issues=", ".join(ISSUE_TYPES),
            journeys=", ".join(CUSTOMER_JOURNEYS),
            reviews="\n".join(lines),
        )
        for attempt in range(1, 4):
            try:
                resp = client.messages.create(
                    model=model_id,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw = resp.content[0].text.strip()
                parsed = _parse_json_response(raw, len(batch))
                results.extend(parsed)
                logger.info("Batch %d/%d classified", i // batch_size + 1,
                            (len(records) + batch_size - 1) // batch_size)
                break
            except Exception as exc:
                logger.warning("Anthropic batch attempt %d failed: %s", attempt, exc)
                if attempt < 3:
                    time.sleep(3 * attempt)
                else:
                    results.extend([{"issue_type": "Other", "severity_class": "P2"}] * len(batch))
    return results


def _classify_unsloth_local(records: list[dict]) -> list[dict]:
    """Load qwen3-mil-v1 LoRA adapter directly via unsloth — no Ollama / GGUF needed."""
    import os, torch
    os.environ["XFORMERS_DISABLED"] = "1"
    from unsloth import FastLanguageModel

    adapter_dir = Path(__file__).parent.parent / "specialist" / "qwen3-mil-v1"
    if not adapter_dir.exists():
        raise FileNotFoundError(f"Adapter not found: {adapter_dir}")

    logger.info("[unsloth-local] Loading adapter from %s", adapter_dir)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(adapter_dir),
        max_seq_length=1024,
        load_in_4bit=True,
        dtype=None,
    )
    FastLanguageModel.for_inference(model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    results = []
    batch_size = 3
    for i in range(0, len(records), batch_size):
        batch = records[i: i + batch_size]
        lines = [
            f"{j+1}. [rating {r.get('rating', '?')}/5] {r['text'][:300]}"
            for j, r in enumerate(batch)
        ]
        prompt = BATCH_PROMPT_TEMPLATE.format(
            issues=", ".join(ISSUE_TYPES),
            journeys=", ".join(CUSTOMER_JOURNEYS),
            reviews="\n".join(lines),
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ]
        input_ids = tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True,
            return_tensors="pt",
        ).to(model.device)

        with torch.no_grad():
            output_ids = model.generate(
                input_ids,
                max_new_tokens=512,
                temperature=0.1,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        generated = output_ids[0][input_ids.shape[-1]:]
        raw = tokenizer.decode(generated, skip_special_tokens=True).strip()
        parsed = _parse_json_response(raw, len(batch))
        results.extend(parsed)
        logger.info("Batch %d/%d classified", i // batch_size + 1,
                    (len(records) + batch_size - 1) // batch_size)

    del model
    torch.cuda.empty_cache()
    return results


def _classify_ollama(records: list[dict], model_name: str) -> list[dict]:
    import urllib.request
    OLLAMA_BASE = "http://127.0.0.1:11434/v1"

    results = []
    batch_size = 5
    for i in range(0, len(records), batch_size):
        batch = records[i: i + batch_size]
        lines = [
            f"{j+1}. [rating {r.get('rating', '?')}/5] {r['text'][:300]}"
            for j, r in enumerate(batch)
        ]
        prompt = BATCH_PROMPT_TEMPLATE.format(
            issues=", ".join(ISSUE_TYPES),
            journeys=", ".join(CUSTOMER_JOURNEYS),
            reviews="\n".join(lines),
        )
        payload = json.dumps({
            "model": model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }).encode()

        for attempt in range(1, 4):
            try:
                req = urllib.request.Request(
                    f"{OLLAMA_BASE}/chat/completions",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    body = json.loads(resp.read())
                raw = body["choices"][0]["message"]["content"].strip()
                parsed = _parse_json_response(raw, len(batch))
                results.extend(parsed)
                logger.info("Batch %d/%d classified", i // batch_size + 1,
                            (len(records) + batch_size - 1) // batch_size)
                break
            except Exception as exc:
                logger.warning("Ollama batch attempt %d failed: %s", attempt, exc)
                if attempt < 3:
                    time.sleep(3 * attempt)
                else:
                    results.extend([{"issue_type": "Other", "severity_class": "P2"}] * len(batch))
    return results


def _parse_json_response(raw: str, expected: int) -> list[dict]:
    import re
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        try:
            import json_repair
            parsed = json_repair.repair_json(raw, return_objects=True)
        except Exception:
            m = re.search(r"\[.*\]", raw, re.DOTALL)
            parsed = json.loads(m.group()) if m else []

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        parsed = []

    results = [_normalise(obj) for obj in parsed[:expected]]
    # Pad if short
    while len(results) < expected:
        results.append({"issue_type": "Other", "severity_class": "P2"})
    return results


# ── Classify dispatch ──────────────────────────────────────────────────────────

ANTHROPIC_MODELS = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-7",
}
OLLAMA_MODELS = {
    "refuel": "michaelborck/refuled:latest",
}

def _classify(records: list[dict], model_arg: str) -> tuple[list[dict], str]:
    """Returns (predictions, canonical_model_id)."""
    if model_arg == "unsloth-local":
        return _classify_unsloth_local(records), "qwen3-mil-v1-local"
    if model_arg in ANTHROPIC_MODELS:
        model_id = ANTHROPIC_MODELS[model_arg]
        return _classify_anthropic(records, model_id), model_id
    if model_arg in OLLAMA_MODELS:
        model_id = OLLAMA_MODELS[model_arg]
        return _classify_ollama(records, model_id), model_id
    # Treat as raw Ollama model name (fine-tuned or custom)
    return _classify_ollama(records, model_arg), model_arg


# ── Metrics ───────────────────────────────────────────────────────────────────

def _compute_metrics(records: list[dict], preds: list[dict]) -> dict:
    it_correct = 0
    sc_correct = 0
    p01_agree  = 0
    p01_total  = 0
    scored     = 0

    per_issue: dict[str, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    # severity confusion: actual -> predicted -> count
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for r, pred in zip(records, preds):
        h_it = r.get("issue_type_human", "").strip()
        h_sc = r.get("severity_class_human", "").strip()
        if not h_it or not h_sc:
            continue  # unlabeled record

        true_it = r["issue_type_model"] if h_it.upper() == "AGREE" else h_it
        true_sc = r["severity_class_model"] if h_sc.upper() == "AGREE" else h_sc

        pred_it = pred["issue_type"]
        pred_sc = pred["severity_class"]

        it_match = pred_it == true_it
        sc_match = pred_sc == true_sc

        it_correct += int(it_match)
        sc_correct += int(sc_match)
        scored += 1

        per_issue[true_it]["total"] += 1
        per_issue[true_it]["correct"] += int(it_match)

        confusion[true_sc][pred_sc] += 1

        # P0/P1 agreement: both true and pred must be P0 or P1
        if true_sc in ("P0", "P1") or pred_sc in ("P0", "P1"):
            p01_total += 1
            p01_agree += int(sc_match)

    it_acc = round(it_correct / scored, 4) if scored else 0.0
    sc_acc = round(sc_correct / scored, 4) if scored else 0.0
    p01_rate = round(p01_agree / p01_total, 4) if p01_total else None

    return {
        "scored": scored,
        "issue_type_accuracy": it_acc,
        "severity_class_accuracy": sc_acc,
        "p01_agreement_rate": p01_rate,
        "p01_total": p01_total,
        "per_issue_type": {
            k: round(v["correct"] / v["total"], 4)
            for k, v in per_issue.items() if v["total"] > 0
        },
        "severity_confusion": {k: dict(v) for k, v in confusion.items()},
    }


# ── Report ─────────────────────────────────────────────────────────────────────

def _print_report(metrics: dict, model_id: str, baseline_haiku: dict | None) -> None:
    it_acc  = metrics["issue_type_accuracy"]
    sc_acc  = metrics["severity_class_accuracy"]
    p01     = metrics["p01_agreement_rate"]
    scored  = metrics["scored"]

    it_flag = "PASS" if it_acc >= 0.85 else "FAIL"
    sc_flag = "PASS" if sc_acc >= 0.90 else "FAIL"

    gate_line = ""
    if baseline_haiku and p01 is not None:
        haiku_p01 = baseline_haiku.get("p01_agreement_rate")
        if haiku_p01 is not None:
            beats = p01 > haiku_p01
            gate_line = (
                f"\n  P0/P1 gate vs Haiku ({haiku_p01:.1%}): "
                + ("PASS — beats baseline" if beats else "FAIL — does not beat Haiku baseline")
            )

    print()
    print("=" * 60)
    print("ENRICHMENT EVALUATION RESULTS")
    print("=" * 60)
    print(f"  Model:               {model_id}")
    print(f"  Sample size:         {scored}")
    print(f"  issue_type accuracy: {it_acc:.1%}  [{it_flag}]  (target >85%)")
    print(f"  severity accuracy:   {sc_acc:.1%}  [{sc_flag}]  (target >90%)")
    p01_str = f"{p01:.1%}" if p01 is not None else "n/a"
    print(f"  P0/P1 agreement:     {p01_str}  ({metrics['p01_total']} P0/P1 records){gate_line}")

    print()
    print("  Severity confusion matrix (actual -> predicted):")
    for actual in SEVERITY_CLASSES:
        row = metrics["severity_confusion"].get(actual, {})
        cells = "  ".join(f"{s}:{row.get(s, 0):3d}" for s in SEVERITY_CLASSES)
        print(f"    actual {actual}:  {cells}")

    print()
    print("  Per issue_type accuracy:")
    for issue, acc in sorted(metrics["per_issue_type"].items(), key=lambda x: -x[1]):
        print(f"    {issue:<35} {acc:.0%}")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate enrichment model against human labels")
    parser.add_argument("--file", required=True, metavar="FILE",
                        help="Path to labeled spot-check JSON file")
    parser.add_argument("--model", required=True,
                        help="Model to evaluate: haiku | refuel | <ollama-model-name>")
    parser.add_argument("--label", default=None,
                        help="Override label stored in log (e.g. 'baseline_haiku', 'fine_tuned_v1')")
    args = parser.parse_args()

    spot_file = Path(args.file)
    if not spot_file.exists():
        logger.error("File not found: %s", spot_file)
        sys.exit(1)

    payload = json.loads(spot_file.read_text(encoding="utf-8"))
    records = payload.get("records", [])

    labeled = [r for r in records if r.get("issue_type_human") and r.get("severity_class_human")]
    if not labeled:
        logger.error("No labeled records found — fill in human labels first")
        sys.exit(1)

    logger.info("Evaluating %d labeled records with model: %s", len(labeled), args.model)

    preds, model_id = _classify(labeled, args.model)
    metrics = _compute_metrics(labeled, preds)

    # Load Haiku baseline for gate comparison
    baseline_haiku = None
    if ACCURACY_LOG.exists():
        for line in ACCURACY_LOG.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
                if "haiku" in entry.get("model", "").lower() or \
                   entry.get("label", "").startswith("baseline_haiku"):
                    baseline_haiku = entry
            except Exception:
                pass

    _print_report(metrics, model_id, baseline_haiku)

    # Append to accuracy log
    log_entry = {
        "date":                    date.today().isoformat(),
        "label":                   args.label or args.model,
        "model":                   model_id,
        "spot_check_file":         spot_file.name,
        "sample_size":             metrics["scored"],
        "issue_type_accuracy":     metrics["issue_type_accuracy"],
        "severity_class_accuracy": metrics["severity_class_accuracy"],
        "p01_agreement_rate":      metrics["p01_agreement_rate"],
        "p01_total":               metrics["p01_total"],
        "issue_type_pass":         metrics["issue_type_accuracy"] >= 0.85,
        "severity_class_pass":     metrics["severity_class_accuracy"] >= 0.90,
        "per_issue_type":          metrics["per_issue_type"],
        "severity_confusion":      metrics["severity_confusion"],
    }
    with ACCURACY_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(log_entry) + "\n")
    logger.info("Results appended to %s", ACCURACY_LOG)

    # Exit 1 if P0/P1 gate fails vs Haiku (for fine-tuned model check)
    if baseline_haiku and metrics["p01_agreement_rate"] is not None:
        haiku_p01 = baseline_haiku.get("p01_agreement_rate")
        if haiku_p01 and metrics["p01_agreement_rate"] <= haiku_p01 \
                and args.model not in ("haiku", "refuel"):
            print("ACTION REQUIRED: fine-tuned model does not beat Haiku P0/P1 baseline. Do not swap routing.")
            sys.exit(1)


if __name__ == "__main__":
    main()
