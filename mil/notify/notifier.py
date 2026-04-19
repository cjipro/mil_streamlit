"""
mil/notify/notifier.py — MIL-38

Pluggable notification layer. Sends alerts on:
  - CLARK-3 escalation (immediate, with Opus synthesis)
  - Daily run completion (summary table, step statuses, cost)

Adapters: SlackAdapter, TeamsAdapter, EmailAdapter, NullAdapter.
Config: mil/config/notify_config.yaml  (adapter type + credentials).
Non-fatal: any send failure logs a warning and does not block the pipeline.
"""
from __future__ import annotations

import json
import logging
import smtplib
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_MIL_ROOT   = Path(__file__).parent.parent
_CONFIG_PATH = _MIL_ROOT / "config" / "notify_config.yaml"


# ── Base ──────────────────────────────────────────────────────────────────────

class NotifyAdapter(ABC):
    @abstractmethod
    def send(self, subject: str, body: str) -> bool:
        """Send a notification. Returns True on success."""

    def _safe_send(self, subject: str, body: str) -> bool:
        try:
            return self.send(subject, body)
        except Exception as exc:
            logger.warning("[notify] send failed (%s): %s", type(self).__name__, exc)
            return False


# ── Null (disabled) ───────────────────────────────────────────────────────────

class NullAdapter(NotifyAdapter):
    def send(self, subject: str, body: str) -> bool:
        logger.debug("[notify] NullAdapter — notification suppressed")
        return True


# ── Slack ─────────────────────────────────────────────────────────────────────

class SlackAdapter(NotifyAdapter):
    def __init__(self, webhook_url: str):
        self._url = webhook_url

    def send(self, subject: str, body: str) -> bool:
        text = f"*{subject}*\n{body}"
        payload = json.dumps({"text": text}).encode()
        req = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status == 200
        if ok:
            logger.info("[notify] Slack alert sent: %s", subject)
        else:
            logger.warning("[notify] Slack returned status %s", resp.status)
        return ok


# ── Microsoft Teams ───────────────────────────────────────────────────────────

class TeamsAdapter(NotifyAdapter):
    def __init__(self, webhook_url: str):
        self._url = webhook_url

    def send(self, subject: str, body: str) -> bool:
        # Teams Adaptive Card (simple text card)
        payload = json.dumps({
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {"type": "TextBlock", "size": "Medium", "weight": "Bolder", "text": subject},
                        {"type": "TextBlock", "text": body, "wrap": True},
                    ],
                },
            }],
        }).encode()
        req = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status in (200, 202)
        if ok:
            logger.info("[notify] Teams alert sent: %s", subject)
        else:
            logger.warning("[notify] Teams returned status %s", resp.status)
        return ok


# ── Email ─────────────────────────────────────────────────────────────────────

class EmailAdapter(NotifyAdapter):
    def __init__(self, smtp_host: str, smtp_port: int, username: str,
                 password: str, from_addr: str, to_addrs: list[str]):
        self._host     = smtp_host
        self._port     = smtp_port
        self._username = username
        self._password = password
        self._from     = from_addr
        self._to       = to_addrs

    def send(self, subject: str, body: str) -> bool:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = self._from
        msg["To"]      = ", ".join(self._to)
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(self._host, self._port, timeout=15) as server:
            server.starttls()
            server.login(self._username, self._password)
            server.sendmail(self._from, self._to, msg.as_string())
        logger.info("[notify] Email sent to %s: %s", self._to, subject)
        return True


# ── Factory ───────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {"adapter": "null"}
    loaded = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {"adapter": "null"}


def get_notifier() -> NotifyAdapter:
    cfg = _load_config()
    adapter = (cfg.get("adapter") or "null").lower()

    if adapter == "slack":
        url = cfg.get("slack", {}).get("webhook_url", "")
        if not url:
            logger.warning("[notify] Slack adapter configured but webhook_url is empty — using NullAdapter")
            return NullAdapter()
        return SlackAdapter(url)

    if adapter == "teams":
        url = cfg.get("teams", {}).get("webhook_url", "")
        if not url:
            logger.warning("[notify] Teams adapter configured but webhook_url is empty — using NullAdapter")
            return NullAdapter()
        return TeamsAdapter(url)

    if adapter == "email":
        ec = cfg.get("email", {})
        required = ["smtp_host", "username", "password", "from_addr", "to_addrs"]
        if not all(ec.get(k) for k in required):
            logger.warning("[notify] Email adapter missing required fields — using NullAdapter")
            return NullAdapter()
        return EmailAdapter(
            smtp_host=ec["smtp_host"],
            smtp_port=int(ec.get("smtp_port", 587)),
            username=ec["username"],
            password=ec["password"],
            from_addr=ec["from_addr"],
            to_addrs=ec["to_addrs"],
        )

    return NullAdapter()


# ── Notification templates ────────────────────────────────────────────────────

def notify_clark3(finding: dict, synthesis: str = "") -> bool:
    """Send immediate CLARK-3 alert. Called from clark_protocol.log_escalation()."""
    notifier = get_notifier()
    fid      = finding.get("finding_id", "?")
    comp     = finding.get("competitor", "?").title()
    journey  = finding.get("journey_id", "?")
    cac      = finding.get("confidence_score", 0.0)
    sev      = finding.get("dominant_severity", "?")
    chr_id   = finding.get("chronicle_id", "?")

    subject = f"MIL CLARK-3 ACT NOW — {comp} {journey}"
    lines = [
        f"Finding     : {fid}",
        f"Competitor  : {comp}",
        f"Journey     : {journey}",
        f"CAC score   : {cac:.3f}",
        f"Severity    : {sev}",
        f"Chronicle   : {chr_id}",
    ]
    if synthesis:
        lines += ["", "Opus synthesis:", synthesis]
    lines += ["", "Review at: cjipro.com/briefing-v3"]
    body = "\n".join(lines)
    return notifier._safe_send(subject, body)


# ── Autonomous Heartbeat (MIL-38) ─────────────────────────────────────────────
# Two pings bracket the pipeline so Hussain can distinguish:
#   STARTING present, completion ping absent within ~30min → crashed mid-run
#   STARTING absent at 06:30 UTC                            → cron didn't fire
# The CRASHED ping fires from an outer try/except in run_daily.py, catching
# anything the step-level handlers let slip through.

def notify_run_starting(enrich_model: str = "unknown", mode: str = "full") -> bool:
    """Pipeline-start heartbeat. Call first thing in run_daily.py main()."""
    notifier = get_notifier()
    if isinstance(notifier, NullAdapter):
        return True
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = "MIL Run ▶ STARTING"
    body = (
        f"Pipeline started at {now}.\n"
        f"Mode         : {mode}\n"
        f"Enrich model : {enrich_model}\n"
        f"Expect a CLEAN / PARTIAL / FAILED completion ping within ~15 min.\n"
        f"If no follow-up ping arrives, the run crashed mid-pipeline."
    )
    return notifier._safe_send(subject, body)


def notify_run_crashed(exc: BaseException) -> bool:
    """Uncaught-exception heartbeat. Call from outer try/except at __main__."""
    notifier = get_notifier()
    if isinstance(notifier, NullAdapter):
        return True
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = "MIL Run ✗ CRASHED"
    body = (
        f"Pipeline raised an unhandled exception at {now}.\n"
        f"Exception: {type(exc).__name__}: {str(exc)[:200]}\n\n"
        f"Fired AFTER the STARTING heartbeat but BEFORE the normal completion ping. "
        f"daily_run_log.jsonl may be missing today's entry — investigate run_daily.py logs."
    )
    return notifier._safe_send(subject, body)


def notify_run_complete(
    run_number: int,
    status: str,
    failed_steps: list[str],
    churn_score: float | None,
    churn_trend: str,
    clark_max: str,
    cost_usd: float,
    new_records: int,
) -> bool:
    """Send end-of-run summary. Called from run_daily.py main()."""
    notifier = get_notifier()
    if isinstance(notifier, NullAdapter):
        return True  # nothing configured — skip silently

    icon = "✓" if status == "CLEAN" else ("⚠" if status == "PARTIAL" else "✗")
    subject = f"MIL Run #{run_number} {icon} {status}"

    lines = [
        f"Status      : {status}",
        f"New records : {new_records}",
        f"Churn score : {churn_score:.1f}/100 ({churn_trend})" if churn_score is not None else "Churn score : unavailable",
        f"Clark max   : {clark_max}",
        f"API cost    : ${cost_usd:.4f}",
    ]
    if failed_steps:
        lines += ["", f"Failed steps: {', '.join(failed_steps)}"]
    lines += ["", "Briefing: cjipro.com/briefing-v3"]
    body = "\n".join(lines)
    return notifier._safe_send(subject, body)
