# src/agents/model_router.py
# 3-tier model router for CJI Pulse.
#
# Tier 1: Qwen (local)  — boilerplate, free, fast
# Tier 2: Sonnet        — routine intelligence, balanced cost/quality
# Tier 3: Opus          — hardest problems, expensive but precise
#
# Auto-escalates on low confidence. Full audit trail in logs/model_router_audit.jsonl.
#
# Usage:
#   from src.agents.model_router import route
#   result = route(task_type="yaml_generation", prompt="...", run_id="2026-03-11_x")

import os
import re
import json
import time
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.agents.llm_client import (
    call_ollama,
    call_sonnet,
    call_opus,
    ollama_health_check,
    emit_telemetry,
)

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parent.parent.parent
_ROUTER_MANIFEST = _REPO_ROOT / "manifests" / "model_router.yaml"
_AUDIT_LOG = _REPO_ROOT / "logs" / "model_router_audit.jsonl"
_PERF_LOG = _REPO_ROOT / "logs" / "model_performance.jsonl"

_AUDIT_LOG.parent.mkdir(exist_ok=True)


# ──────────────────────────────────────────────
# Config loader
# ──────────────────────────────────────────────

def _load_config() -> dict:
    with open(_ROUTER_MANIFEST, "r") as f:
        return yaml.safe_load(f)


# ──────────────────────────────────────────────
# Tier -> model mapping
# ──────────────────────────────────────────────

def _make_callers(config: dict) -> dict:
    local_system = config["models"]["local"].get("system_prompt", "")
    return {
        1: lambda prompt, run_id, system: call_ollama(prompt, run_id, system=local_system),
        2: lambda prompt, run_id, system: call_sonnet(prompt, run_id, system),
        3: lambda prompt, run_id, system: call_opus(prompt, run_id, system),
    }

_TIER_NAMES = {1: "local", 2: "sonnet", 3: "opus"}


# ──────────────────────────────────────────────
# Errors
# ──────────────────────────────────────────────

class RoutingError(Exception):
    pass


# ──────────────────────────────────────────────
# Confidence check
# ──────────────────────────────────────────────

_CONFIDENCE_SUFFIX = (
    "\n\n---\nBefore you finish, on the very last line write exactly:\n"
    "CONFIDENCE: <score>/10\n"
    "where <score> is your confidence in the accuracy and completeness of your answer (1=very uncertain, 10=certain)."
)


def _extract_confidence(text: str) -> Optional[int]:
    """Parse 'CONFIDENCE: N' or 'CONFIDENCE: N/10' from anywhere in the response."""
    match = re.search(r"CONFIDENCE:\s*(\d+)(?:\s*/\s*10)?", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _strip_confidence_line(text: str) -> str:
    """Remove the CONFIDENCE line from anywhere in the response body."""
    return re.sub(
        r"^CONFIDENCE:\s*\d+(?:\s*/\s*10)?\s*\n?",
        "", text, flags=re.IGNORECASE
    ).strip()


def _has_uncertainty_keywords(text: str, keywords: list) -> bool:
    lower = text.lower()
    return any(kw.lower() in lower for kw in keywords)


# ──────────────────────────────────────────────
# Audit writer
# ──────────────────────────────────────────────

def _write_audit(record: dict):
    with open(_AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


def _estimate_cost(model_name: str, prompt: str, response: str, config: dict) -> float:
    """Estimate USD cost based on token counts and config rates."""
    costs = config.get("monitoring", {}).get("cost_per_1k_tokens", {})
    prompt_tokens = _estimate_tokens(prompt) / 1000
    response_tokens = _estimate_tokens(response or "") / 1000

    if model_name == "local":
        return 0.0
    elif model_name == "sonnet":
        return (prompt_tokens * costs.get("sonnet_input", 0.003) +
                response_tokens * costs.get("sonnet_output", 0.015))
    elif model_name == "opus":
        return (prompt_tokens * costs.get("opus_input", 0.015) +
                response_tokens * costs.get("opus_output", 0.075))
    return 0.0


def _write_performance(record: dict, config: dict):
    monitoring = config.get("monitoring", {})
    if not monitoring.get("enabled", False):
        return
    log_path = _REPO_ROOT / monitoring.get("log_path", "logs/model_performance.jsonl")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


# ──────────────────────────────────────────────
# Core router
# ──────────────────────────────────────────────

def route(
    task_type: str,
    prompt: str,
    run_id: Optional[str] = None,
    system: str = "",
    dry_run: bool = False,
) -> Optional[str]:
    """
    Route a prompt through the 3-tier model hierarchy.

    Args:
        task_type:  Must match a task_type in manifests/model_router.yaml.
        prompt:     The prompt to send.
        run_id:     Pipeline run ID for telemetry. Auto-generated if not provided.
        system:     Optional system prompt (Sonnet/Opus only).
        dry_run:    Return routing plan as string without calling any model.

    Returns:
        Response string, or None if all tiers failed.

    Raises:
        RoutingError: If task_type is not registered.
    """
    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d_router")

    config = _load_config()
    rules = {r["task_type"]: r for r in config["routing_rules"]}
    confidence_cfg = config.get("confidence", {})
    low_threshold = confidence_cfg.get("low_threshold", 6)
    uncertainty_keywords = confidence_cfg.get("uncertainty_keywords", [])

    if task_type not in rules:
        raise RoutingError(
            f"task_type '{task_type}' not registered in manifests/model_router.yaml. "
            f"Valid: {sorted(rules.keys())}"
        )

    rule = rules[task_type]
    start_tier = rule["start_tier"]
    max_tier = rule["max_tier"]
    confidence_check = rule.get("confidence_check", False)

    if dry_run:
        return (
            f"[DRY RUN] task_type={task_type} | "
            f"start_tier={start_tier} ({_TIER_NAMES[start_tier]}) | "
            f"max_tier={max_tier} ({_TIER_NAMES[max_tier]}) | "
            f"confidence_check={confidence_check}"
        )

    # ── Tier escalation loop ──────────────────
    callers = _make_callers(config)
    current_tier = start_tier
    models_tried = []
    confidence_scores = []
    result = None
    final_tier = None

    while current_tier <= max_tier:
        model_name = _TIER_NAMES[current_tier]
        print(f"[ROUTER] task_type={task_type} | tier={current_tier} ({model_name})")

        # Health check for local tier
        if current_tier == 1 and not ollama_health_check():
            print(f"[ROUTER] Tier 1 (local) unavailable — escalating to tier 2")
            emit_telemetry(
                "DEPENDENCY-003", f"model_router.{task_type}",
                "Ollama health check failed — escalating to sonnet", run_id
            )
            current_tier = 2
            continue

        # Tier 1 (Qwen) gets confidence via system prompt — no suffix needed.
        # Tier 2/3 get the suffix appended to the prompt.
        if confidence_check and current_tier > 1:
            active_prompt = prompt + _CONFIDENCE_SUFFIX
        else:
            active_prompt = prompt

        # Call the model — timed
        caller = callers[current_tier]
        t0 = time.time()
        response = caller(active_prompt, run_id, system)
        latency = round(time.time() - t0, 3)
        models_tried.append(model_name)

        if response is None:
            # Model failed entirely — escalate if possible
            if current_tier < max_tier:
                current_tier += 1
                continue
            else:
                break  # all tiers exhausted

        # Extract confidence if applicable
        confidence = None
        if confidence_check:
            confidence = _extract_confidence(response)
            confidence_scores.append({"tier": current_tier, "model": model_name, "score": confidence})
            response = _strip_confidence_line(response)

            # Check for low confidence or uncertainty keywords
            low_conf = (confidence is not None and confidence <= low_threshold)
            uncertain = _has_uncertainty_keywords(response, uncertainty_keywords)

            if (low_conf or uncertain) and current_tier < max_tier:
                score_str = str(confidence) if confidence is not None else "unknown"
                print(
                    f"[ROUTER] Low confidence (score={score_str}) at tier {current_tier} — "
                    f"escalating to tier {current_tier + 1}"
                )
                current_tier += 1
                continue

        # Accept this response
        result = response
        final_tier = current_tier
        break

    # ── Audit log ────────────────────────────
    audit_record = {
        "run_id": run_id,
        "task_type": task_type,
        "start_tier": start_tier,
        "final_tier": final_tier,
        "models_tried": models_tried,
        "confidence_scores": confidence_scores,
        "escalation_count": len(models_tried) - 1 if models_tried else 0,
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "success": result is not None,
    }
    _write_audit(audit_record)
    print(f"[AUDIT] {json.dumps(audit_record)}")

    if result is None:
        emit_telemetry(
            "PIPELINE-004", f"model_router.{task_type}",
            f"All tiers failed for task_type='{task_type}'", run_id
        )

    return result


# ──────────────────────────────────────────────
# Convenience wrappers
# ──────────────────────────────────────────────

def generate_yaml(prompt: str, run_id: Optional[str] = None) -> Optional[str]:
    return route("yaml_generation", prompt, run_id)

def create_file(prompt: str, run_id: Optional[str] = None) -> Optional[str]:
    return route("file_creation", prompt, run_id)

def validate(prompt: str, run_id: Optional[str] = None) -> Optional[str]:
    return route("validation_script", prompt, run_id)

def narrative(prompt: str, run_id: Optional[str] = None, system: str = "") -> Optional[str]:
    return route("narrative_generation", prompt, run_id, system=system)

def hypothesis(prompt: str, run_id: Optional[str] = None, system: str = "") -> Optional[str]:
    return route("hypothesis_evaluation", prompt, run_id, system=system)

def governance(prompt: str, run_id: Optional[str] = None, system: str = "") -> Optional[str]:
    return route("governance_review", prompt, run_id, system=system)

def architecture(prompt: str, run_id: Optional[str] = None, system: str = "") -> Optional[str]:
    return route("architecture_decision", prompt, run_id, system=system)

def vulnerable_cohort(prompt: str, run_id: Optional[str] = None, system: str = "") -> Optional[str]:
    return route("vulnerable_cohort_analysis", prompt, run_id, system=system)

def reason(prompt: str, run_id: Optional[str] = None, system: str = "") -> Optional[str]:
    return route("complex_reasoning", prompt, run_id, system=system)


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: py -m src.agents.model_router <task_type> <prompt>")
        print("       py -m src.agents.model_router --dry-run <task_type> <prompt>")
        sys.exit(1)

    dry = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    task = args[0]
    user_prompt = " ".join(args[1:])

    output = route(task_type=task, prompt=user_prompt, dry_run=dry)
    print(f"\n[OUTPUT]\n{output}")
