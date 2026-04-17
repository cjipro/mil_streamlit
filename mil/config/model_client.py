"""
model_client.py — unified LLM call wrapper for all MIL Anthropic API calls.

Provides:
  - Consistent timeout (from thresholds.yaml api.anthropic_timeout_s)
  - Exponential backoff retry (max_retries from thresholds.yaml)
  - Trace ID on every call for log correlation
  - Single import point for anthropic client

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

import logging
import os
import time
import uuid
from typing import Optional

logger = logging.getLogger(__name__)


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


def call_anthropic(
    task: str,
    user_prompt: str,
    system: str = "",
    max_tokens: int = 512,
    trace_id: Optional[str] = None,
) -> str:
    """
    Call Anthropic API for the given task. Returns response text.

    Args:
        task:        Model routing task name (used for model selection + logging).
        user_prompt: The user message content.
        system:      Optional system prompt.
        max_tokens:  Token limit for the response.
        trace_id:    Optional caller-supplied ID for log correlation.
                     Auto-generated (8-char UUID prefix) if not provided.

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
        kwargs["system"] = system

    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(1, max_retries + 1):
        try:
            logger.debug("[model_client] tid=%s task=%s attempt=%d/%d", tid, task, attempt, max_retries)
            response = client.messages.create(**kwargs)
            text = response.content[0].text.strip()
            logger.debug("[model_client] tid=%s task=%s ok tokens=%s", tid, task,
                         getattr(response, "usage", {}).get("output_tokens", "?"))
            return text
        except Exception as exc:
            last_exc = exc
            logger.warning("[model_client] tid=%s task=%s attempt %d/%d failed: %s",
                           tid, task, attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(2 ** attempt)

    raise RuntimeError(f"[model_client] task={task} tid={tid} exhausted {max_retries} retries: {last_exc}") from last_exc
