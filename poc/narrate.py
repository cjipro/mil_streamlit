"""
POC — Qwen Narrative Generator
Takes a sessionisation summary dict, calls Qwen via Ollama,
returns a structured CJI narrative.
"""

import requests
import json

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5-coder:14b"


PROMPT_TEMPLATE = """You are CJI Pulse — a customer journey intelligence system for a retail bank.
You have been given today's data on the Loans application journey.

DATA SUMMARY:
- Total Loans journey sessions: {total_loans_sessions}
- Sessions abandoned: {abandoned_count} ({abandonment_rate_pct}%)
- Sessions completed: {completed_count} ({completion_rate_pct}%)
- Top drop-off step: {top_dropoff_step} ({top_dropoff_count} sessions abandoned here)
- Average time spent before abandonment: {avg_abandon_duration_s} seconds

DROP-OFF BY STEP:
{dropoff_lines}

Write a professional 3-sentence customer journey intelligence briefing for a bank product manager.
Sentence 1: State the key finding (abandonment rate and where it is happening).
Sentence 2: Interpret what this likely means for the customer (friction, confusion, or a barrier).
Sentence 3: Give one concrete recommended action.

Be direct. No waffle. No generic advice. Specific to the data above.
"""


def build_prompt(summary: dict) -> str:
    dropoff_lines = "\n".join(
        f"  - {step}: {count} sessions"
        for step, count in summary["dropoff_by_step"].items()
        if count > 0
    )
    return PROMPT_TEMPLATE.format(
        dropoff_lines=dropoff_lines,
        **summary,
    )


def narrate(summary: dict, ollama_url: str = OLLAMA_URL, model: str = MODEL) -> str:
    prompt = build_prompt(summary)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    r = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=120)
    r.raise_for_status()
    return r.json()["response"].strip()


if __name__ == "__main__":
    # Test with a sample summary
    sample = {
        "total_loans_sessions": 1200,
        "abandoned_count": 408,
        "abandonment_rate_pct": 34.0,
        "completion_rate_pct": 22.5,
        "completed_count": 270,
        "avg_abandon_duration_s": 47.3,
        "dropoff_by_step": {
            "Loans_Menu": 45,
            "Loan_Type_Select": 89,
            "Eligibility_Check": 187,
            "Document_Upload": 62,
            "Review_Submit": 25,
            "Confirmation": 0,
        },
        "top_dropoff_step": "Eligibility_Check",
        "top_dropoff_count": 187,
    }
    print("Calling Qwen...")
    narrative = narrate(sample)
    print("\n--- NARRATIVE ---")
    print(narrative)
