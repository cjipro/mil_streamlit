"""
eval_enrichment.py — Head-to-head: claude-haiku vs qwen3:14b on schema v3 enrichment.

Samples 20 real reviews from existing enriched files (strips enrichment fields),
runs both models with the identical prompt, then prints a comparison table.

Usage: py eval_enrichment.py
"""
import json
import os
import random
import time
from pathlib import Path

# ── same constants as enrich_sonnet.py ────────────────────────────────────────
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

ENRICHED_DIR = Path("mil/data/historical/enriched")
N_SAMPLES = 20
BATCH_SIZE = 10

BLOCKING_ISSUES = {
    "App Not Opening", "Login Failed", "Payment Failed",
    "Transfer Failed", "Account Locked", "App Crashing",
}


# ── normalise (same gate logic) ───────────────────────────────────────────────
def normalise(obj: dict) -> dict:
    issue = obj.get("issue_type", "Other")
    if issue not in ISSUE_TYPES:
        issue = "Other"
    journey = obj.get("customer_journey", "General App Use")
    if journey not in CUSTOMER_JOURNEYS:
        journey = "General App Use"
    try:
        sentiment = round(max(-1.0, min(1.0, float(obj.get("sentiment_score", 0.0)))), 3)
    except (TypeError, ValueError):
        sentiment = 0.0
    severity = obj.get("severity_class", "P2")
    if severity not in ("P0", "P1", "P2"):
        severity = "P2"
    if severity in ("P0", "P1") and issue not in BLOCKING_ISSUES:
        severity = "P2"
    if issue == "Positive Feedback":
        severity = "P2"
    return {
        "issue_type": issue,
        "customer_journey": journey,
        "sentiment_score": sentiment,
        "severity_class": severity,
        "reasoning": str(obj.get("reasoning", ""))[:200],
    }


# ── sample reviews (with existing haiku labels as baseline) ──────────────────
def load_samples(n: int) -> list[dict]:
    pool = []
    for f in ENRICHED_DIR.glob("*.json"):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            competitor = p.get("competitor", f.stem)
            for r in p.get("records", []):
                text = r.get("review") or r.get("content", "")
                issue = r.get("issue_type", "")
                sev = r.get("severity_class", "")
                # only include records with valid haiku labels
                if len(text) > 30 and issue in ISSUE_TYPES and sev in ("P0", "P1", "P2"):
                    pool.append({
                        "text": text[:300],
                        "rating": r.get("rating", "?"),
                        "competitor": competitor,
                        "haiku_issue": issue,
                        "haiku_severity": sev,
                        "haiku_journey": r.get("customer_journey", ""),
                        "haiku_sentiment": r.get("sentiment_score", 0.0),
                        "haiku_reasoning": r.get("reasoning", ""),
                    })
        except Exception:
            pass
    random.seed(42)
    return random.sample(pool, min(n, len(pool)))


# ── build prompt ──────────────────────────────────────────────────────────────
def build_prompt(samples: list[dict]) -> str:
    lines = [f"{i+1}. [rating {s['rating']}/5] {s['text']}" for i, s in enumerate(samples)]
    return BATCH_PROMPT_TEMPLATE.format(
        issues=", ".join(ISSUE_TYPES),
        journeys=", ".join(CUSTOMER_JOURNEYS),
        reviews="\n".join(lines),
    )


# ── call haiku ────────────────────────────────────────────────────────────────
def call_haiku(prompt: str) -> tuple[list[dict], float]:
    import anthropic
    from dotenv import load_dotenv
    load_dotenv()
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    t0 = time.time()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed = time.time() - t0
    raw = resp.content[0].text.strip()
    return parse_json(raw), elapsed


# ── call qwen3 ────────────────────────────────────────────────────────────────
def call_qwen3(prompt: str) -> tuple[list[dict], float]:
    from openai import OpenAI
    client = OpenAI(base_url="http://127.0.0.1:11434/v1", api_key="ollama")
    t0 = time.time()
    resp = client.chat.completions.create(
        model="qwen3:14b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=2048,
        temperature=0,
        extra_body={"think": False},  # disable chain-of-thought for speed
    )
    elapsed = time.time() - t0
    raw = resp.choices[0].message.content.strip()
    return parse_json(raw), elapsed


# ── json parse ────────────────────────────────────────────────────────────────
def parse_json(raw: str) -> list[dict]:
    import re
    m = re.search(r"[\[\{]", raw)
    if not m:
        return []
    start = m.start()
    last = max(raw.rfind("]"), raw.rfind("}"))
    trimmed = raw[start:last + 1]
    try:
        parsed = json.loads(trimmed)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            parsed = json.loads(repair_json(trimmed))
        except Exception:
            return []
    return parsed if isinstance(parsed, list) else [parsed]


# ── score a result ────────────────────────────────────────────────────────────
def score(results: list[dict], n: int) -> dict:
    valid = sum(
        1 for r in results
        if r.get("issue_type") in ISSUE_TYPES
        and r.get("customer_journey") in CUSTOMER_JOURNEYS
        and r.get("severity_class") in ("P0", "P1", "P2")
        and isinstance(r.get("sentiment_score"), (int, float))
        and r.get("reasoning")
    )
    return {
        "returned": len(results),
        "expected": n,
        "schema_valid": valid,
        "schema_pct": f"{valid/n*100:.0f}%" if n else "0%",
    }


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("Loading samples...")
    samples = load_samples(N_SAMPLES)
    print(f"  {len(samples)} reviews sampled from enriched corpus\n")

    # Run qwen3 only — haiku baseline from existing enriched labels
    all_qwen3 = []
    qwen3_time = 0.0

    for batch_start in range(0, len(samples), BATCH_SIZE):
        batch = samples[batch_start:batch_start + BATCH_SIZE]
        prompt = build_prompt(batch)
        batch_n = batch_start // BATCH_SIZE + 1
        total_batches = (len(samples) + BATCH_SIZE - 1) // BATCH_SIZE

        print(f"Batch {batch_n}/{total_batches} — running qwen3:14b...", end=" ", flush=True)
        try:
            q_results, q_time = call_qwen3(prompt)
            qwen3_time += q_time
            all_qwen3.extend([normalise(r) for r in q_results])
            print(f"done ({q_time:.1f}s, {len(q_results)} records)")
        except Exception as e:
            print(f"FAILED: {e}")
            all_qwen3.extend([{}] * len(batch))

    n = len(samples)
    q_score = score(all_qwen3, n)

    # ── summary table ─────────────────────────────────────────────────────────
    print("\n" + "="*70)
    print(f"{'METRIC':<35} {'QWEN3:14B':>30}")
    print("="*70)
    print(f"{'Records returned / expected':<35} {q_score['returned']:>28}/{n}")
    print(f"{'Schema valid':<35} {q_score['schema_valid']:>30}")
    print(f"{'Schema compliance':<35} {q_score['schema_pct']:>30}")
    print(f"{'Total time (s)':<35} {qwen3_time:>29.1f}s")
    print("="*70)

    # ── per-review comparison vs haiku baseline ───────────────────────────────
    print(f"\n{'#':<3} {'REVIEW (38c)':<40} {'HAIKU (baseline)':>26} {'QWEN3':>26} {'ISSUE':>6} {'SEV':>4}")
    print("-"*112)

    issue_agree = 0
    sev_agree = 0
    for i, s in enumerate(samples):
        q = all_qwen3[i] if i < len(all_qwen3) else {}
        text = s["text"][:38].replace("\n", " ")
        h_label = f"{s['haiku_issue'][:20]} / {s['haiku_severity']}"
        q_label = f"{q.get('issue_type','?')[:20]} / {q.get('severity_class','?')}"
        i_match = "Y" if s["haiku_issue"] == q.get("issue_type") else "N"
        s_match = "Y" if s["haiku_severity"] == q.get("severity_class") else "N"
        if i_match == "Y":
            issue_agree += 1
        if s_match == "Y":
            sev_agree += 1
        print(f"{i+1:<3} {text:<40} {h_label:>26} {q_label:>26} {i_match:>6} {s_match:>4}")

    print("-"*112)
    print(f"Issue type agreement:  {issue_agree}/{n} ({issue_agree/n*100:.0f}%)")
    print(f"Severity agreement:    {sev_agree}/{n} ({sev_agree/n*100:.0f}%)\n")

    # ── severity distribution ─────────────────────────────────────────────────
    h_sevs = {"P0": 0, "P1": 0, "P2": 0}
    q_sevs = {"P0": 0, "P1": 0, "P2": 0}
    for s in samples:
        sv = s["haiku_severity"]
        if sv in h_sevs:
            h_sevs[sv] += 1
    for r in all_qwen3:
        sv = r.get("severity_class", "?")
        if sv in q_sevs:
            q_sevs[sv] += 1
    print(f"HAIKU severity dist:  P0={h_sevs['P0']}  P1={h_sevs['P1']}  P2={h_sevs['P2']}")
    print(f"QWEN3 severity dist:  P0={q_sevs['P0']}  P1={q_sevs['P1']}  P2={q_sevs['P2']}")


if __name__ == "__main__":
    main()
