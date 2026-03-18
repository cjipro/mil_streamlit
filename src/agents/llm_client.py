# src/agents/llm_client.py
# Thin clients for Qwen (Ollama), Claude Sonnet, and Claude Opus.
# Called only by model_router.py — never directly by pipeline code.

import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

# Load .env from repo root
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass


# ──────────────────────────────────────────────
# Telemetry helper
# ──────────────────────────────────────────────

def emit_telemetry(error_code: str, step_id: str, output_summary: str, run_id: str):
    """Emit a telemetry event to stdout. Conforms to telemetry_spec.yaml."""
    event = {
        "step_id": step_id,
        "input_reference": f"llm_client@{datetime.now(timezone.utc).date()}",
        "output_summary": output_summary,
        "error_code": error_code,
        "error_class": "DEPENDENCY",
        "retryability": "backoff",
        "business_impact_tier": "P2",
        "downstream_dependency_impact": "model_router",
        "manifest_spec_reference": "manifests/system_manifest.yaml#model_router",
        "recovery_strategy_reference": "manifests/model_router.yaml#fallback_policy",
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": run_id,
    }
    print(f"[TELEMETRY] {json.dumps(event)}")


# ──────────────────────────────────────────────
# Tier 1 — Qwen via Ollama
# ──────────────────────────────────────────────

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b")


def ollama_health_check() -> bool:
    """Return True if Ollama is reachable and the target model is loaded."""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            return any(OLLAMA_MODEL in m for m in models)
    except Exception:
        return False


def call_ollama(prompt: str, run_id: str, timeout: int = 120, system: str = "") -> Optional[str]:
    """Call Qwen via Ollama. Returns response text or None on failure."""
    body = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        body["system"] = system
    payload = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        emit_telemetry("DEPENDENCY-003", "llm_client.call_ollama", f"Ollama unavailable: {e}", run_id)
        return None
    except Exception as e:
        emit_telemetry("PIPELINE-004", "llm_client.call_ollama", f"Unexpected error: {e}", run_id)
        return None


# ──────────────────────────────────────────────
# Tier 2 / Tier 3 — Claude via Anthropic SDK
# ──────────────────────────────────────────────

SONNET_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
OPUS_MODEL = os.getenv("CLAUDE_OPUS_MODEL", "claude-opus-4-6")


def call_claude(
    prompt: str,
    run_id: str,
    model: str = None,
    system: str = "",
    timeout: int = 60,
) -> Optional[str]:
    """
    Call Claude (Sonnet or Opus) via the Anthropic SDK.
    model defaults to SONNET_MODEL if not specified.
    Returns response text or None on failure.
    """
    if model is None:
        model = SONNET_MODEL

    try:
        import anthropic
    except ImportError:
        emit_telemetry(
            "DEPENDENCY-003", "llm_client.call_claude",
            "anthropic package not installed — run: pip install anthropic", run_id
        )
        return None

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        kwargs = {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        message = client.messages.create(**kwargs)
        return message.content[0].text.strip()

    except Exception as e:
        emit_telemetry("PIPELINE-004", "llm_client.call_claude", f"Claude API call failed: {e}", run_id)
        return None


def call_sonnet(prompt: str, run_id: str, system: str = "") -> Optional[str]:
    return call_claude(prompt, run_id, model=SONNET_MODEL, system=system, timeout=60)


def call_opus(prompt: str, run_id: str, system: str = "") -> Optional[str]:
    return call_claude(prompt, run_id, model=OPUS_MODEL, system=system, timeout=120)
