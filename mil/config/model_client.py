"""
model_client.py — unified LLM call wrapper for all MIL Anthropic API calls.

Provides:
  - Consistent timeout (from thresholds.yaml api.anthropic_timeout_s)
  - Exponential backoff retry (max_retries from thresholds.yaml)
  - Trace ID on every call for log correlation
  - Single import point for anthropic client
  - Data egress log (MIL-37): every external call appended to data_egress_log.jsonl

Usage:
    from mil.config.model_client import call_anthropic

    text = call_anthropic(
        task="commentary",
        system="You are an analyst.",
        user_prompt="Analyse this...",
        max_tokens=300,
    )
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Data Egress Log (MIL-37) ──────────────────────────────────────────────────

_MIL_ROOT   = Path(__file__).parent.parent
_EGRESS_LOG = _MIL_ROOT / "data" / "data_egress_log.jsonl"

# Cost per 1M tokens (USD) — (input, output, cache_read, cache_create)
# cache_create = same as input; cache_read ≈ 10% of input
_MODEL_COSTS: dict[str, tuple[float, float, float, float]] = {
    "claude-haiku-4-5-20251001": (0.80,   4.00,  0.08,  0.80),
    "claude-sonnet-4-6":         (3.00,  15.00,  0.30,  3.00),
    "claude-opus-4-7":          (15.00,  75.00,  1.50, 15.00),
}


def _write_egress(
    *,
    provider: str,
    task: str,
    model: str,
    trace_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_create_tokens: int,
    success: bool,
) -> None:
    costs = _MODEL_COSTS.get(model, (3.00, 15.00, 0.30, 3.00))
    cost_usd = round(
        (input_tokens        * costs[0]
         + output_tokens     * costs[1]
         + cache_read_tokens * costs[2]
         + cache_create_tokens * costs[3]) / 1_000_000,
        6,
    )
    entry = {
        "timestamp":           datetime.now(timezone.utc).isoformat(),
        "provider":            provider,
        "task":                task,
        "model":               model,
        "trace_id":            trace_id,
        "input_tokens":        input_tokens,
        "output_tokens":       output_tokens,
        "cache_read_tokens":   cache_read_tokens,
        "cache_create_tokens": cache_create_tokens,
        "cost_usd":            cost_usd,
        "success":             success,
    }
    try:
        with _EGRESS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.warning("[egress_log] write failed: %s", exc)


class CircuitBreakerError(RuntimeError):
    """Raised when a task has hit CIRCUIT_BREAKER_THRESHOLD consecutive failures."""
    def __init__(self, task: str, failures: int):
        self.task = task
        self.failures = failures
        super().__init__(
            f"[circuit_breaker] task={task} tripped after {failures} consecutive failures — "
            f"falling back to cached/degraded output."
        )


CIRCUIT_BREAKER_THRESHOLD = 3
_failure_counts: dict[str, int] = {}   # consecutive failure count per task, reset on success


def _get_client():
    import anthropic
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set")

    try:
        from mil.config.thresholds import T
    except ImportError:
        from config.thresholds import T  # subprocess path

    return anthropic.Anthropic(api_key=api_key, timeout=float(T("api.anthropic_timeout_s")))


# Minimum system prompt length (chars) to enable prompt caching.
# Anthropic caching threshold: ~1024 tokens ≈ 4000 chars.
_CACHE_MIN_CHARS = 4000


def call_anthropic(
    task: str,
    user_prompt: str,
    system: str = "",
    max_tokens: int = 512,
    trace_id: Optional[str] = None,
    cache_system: bool = False,
) -> str:
    """
    Call Anthropic API for the given task. Returns response text.

    Args:
        task:         Model routing task name (used for model selection + logging).
        user_prompt:  The user message content.
        system:       Optional system prompt. If cache_system=True and len >= threshold,
                      cache_control is added for prompt caching.
        max_tokens:   Token limit for the response.
        trace_id:     Optional caller-supplied ID for log correlation.
        cache_system: Enable prompt caching on the system prompt (use when the system
                      prompt is static and long enough to cross the 1024-token threshold).

    Raises:
        RuntimeError: If all retries are exhausted.
        EnvironmentError: If ANTHROPIC_API_KEY is not set.
    """
    try:
        from mil.config.get_model import get_model
        from mil.config.thresholds import T
    except ImportError:
        from config.get_model import get_model
        from config.thresholds import T

    cfg = get_model(task)
    model = cfg["model"]
    max_retries = int(T("api.max_retries"))
    tid = trace_id or uuid.uuid4().hex[:8]

    client = _get_client()
    messages = [{"role": "user", "content": user_prompt}]
    kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}

    if system:
        if cache_system and len(system) >= _CACHE_MIN_CHARS:
            kwargs["system"] = [{"type": "text", "text": system,
                                 "cache_control": {"type": "ephemeral"}}]
        else:
            kwargs["system"] = system

    # Circuit breaker: refuse to attempt if task already hit threshold this process run
    if _failure_counts.get(task, 0) >= CIRCUIT_BREAKER_THRESHOLD:
        raise CircuitBreakerError(task, _failure_counts[task])

    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, max_retries + 1):
        try:
            logger.debug("[model_client] tid=%s task=%s attempt=%d/%d", tid, task, attempt, max_retries)
            response = client.messages.create(**kwargs)
            text = response.content[0].text.strip()

            # Token usage — logged at INFO so it's visible in production logs
            usage = getattr(response, "usage", None)
            in_tok = out_tok = cache_rd = cache_cr = 0
            if usage:
                in_tok   = getattr(usage, "input_tokens", 0)
                out_tok  = getattr(usage, "output_tokens", 0)
                cache_rd = getattr(usage, "cache_read_input_tokens", 0)
                cache_cr = getattr(usage, "cache_creation_input_tokens", 0)
                logger.info(
                    "[model_client] tid=%s task=%s model=%s in=%d out=%d cache_read=%d cache_create=%d",
                    tid, task, model, in_tok, out_tok, cache_rd, cache_cr,
                )
            _write_egress(
                provider="anthropic", task=task, model=model, trace_id=tid,
                input_tokens=in_tok, output_tokens=out_tok,
                cache_read_tokens=cache_rd, cache_create_tokens=cache_cr,
                success=True,
            )
            _failure_counts[task] = 0   # reset on success
            return text
        except CircuitBreakerError:
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning("[model_client] tid=%s task=%s attempt %d/%d failed: %s",
                           tid, task, attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(2 ** attempt)

    _failure_counts[task] = _failure_counts.get(task, 0) + 1
    logger.warning("[model_client] task=%s consecutive_failures=%d threshold=%d",
                   task, _failure_counts[task], CIRCUIT_BREAKER_THRESHOLD)
    _write_egress(
        provider="anthropic", task=task, model=model, trace_id=tid,
        input_tokens=0, output_tokens=0,
        cache_read_tokens=0, cache_create_tokens=0,
        success=False,
    )
    raise RuntimeError(f"[model_client] task={task} tid={tid} exhausted {max_retries} retries: {last_exc}") from last_exc
