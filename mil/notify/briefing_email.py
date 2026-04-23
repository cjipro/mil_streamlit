"""
mil/notify/briefing_email.py — MIL-49

Daily Sonar PDB email. Fires at the end of run_daily.py on CLEAN runs.

Constitution (MIL-49, locked 2026-04-22):

1.  Verbatim is sacred             — quote text never mutated
2.  Denominators always named      — enforced in Opus prompt
3.  Judgments back-sourced         — enforced in Opus prompt
4.  Confidence stated              — enforced in Opus prompt, regex-checked
5.  Analyst voice, never operator  — enforced in Opus prompt (banned verbs)
6.  No internal codes              — regex scrub on Opus output + commentary
7.  Lead with position/proportion  — enforced in Opus prompt (structural)
8.  One priority per memo          — Box 3 selector picks one issue
9.  Silent days = no email         — guard returns early below threshold
10. Source transparency            — deterministic footer
11. Subject is an immutable string — Teams inbox rules depend on it

Subject line is a fixed constant across every send. All per-day variance
lives in the body (Opus-generated headline + lede, three verbatim quotes,
commentary paragraph, source footer).

Distribution list : mil/config/distribution.yaml
SMTP creds        : .env — SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_APP_PASSWORD,
                    optional SMTP_FROM (defaults to SMTP_USER)
Per-send log      : mil/data/email_log.jsonl
Opus cache        : mil/data/email_lede_log.jsonl (keyed by run_number)
"""
from __future__ import annotations

import json
import logging
import os
import re
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_MIL_ROOT          = Path(__file__).parent.parent
_DISTRIBUTION_YAML = _MIL_ROOT / "config" / "distribution.yaml"
_EMAIL_LOG         = _MIL_ROOT / "data" / "email_log.jsonl"
_LEDE_CACHE        = _MIL_ROOT / "data" / "email_lede_log.jsonl"
_COMMENTARY_LOG    = _MIL_ROOT / "data" / "commentary_log.jsonl"
_BRIEFING_HTML     = _MIL_ROOT / "publish" / "output" / "index_v4.html"
_ENRICHED_DIR      = _MIL_ROOT / "data" / "historical" / "enriched"
_BRIEFING_URL      = "https://cjipro.com/briefing-v4"

# Locked constant — Teams rules depend on byte-for-byte identity.
_SUBJECT_LINE = "Voice of the Customer: Barclays App Experience (Open Sources)"

_COHORT_PEERS = ["NatWest", "Lloyds", "HSBC", "Monzo", "Revolut"]

# Silent-day thresholds (principle 9)
_MIN_DAYS_ACTIVE = 3
_MIN_GAP_PP      = 2.0
_QUALIFYING_SEVERITIES = {"P0", "P1"}

# Sources for verbatim quote selection. Order matters: App Store and Google
# Play are preferred for the first two slots; the third slot draws from any
# non-store source that has a matching quote.
_SOURCES: list[tuple[str, str, str, str]] = [
    ("App Store",    "app_store_barclays_enriched.json",    "review",  "date"),
    ("Google Play",  "google_play_barclays_enriched.json",  "content", "at"),
    ("Reddit",       "reddit_barclays_enriched.json",       "body",    "date"),
    ("YouTube",      "youtube_barclays_enriched.json",      "review",  "date"),
    ("DownDetector", "downdetector_barclays_enriched.json", "review",  "date"),
]

# Internal-code scrubber (principle 6).
# Matches CLARK / CLARK-N, P0/P1/P2 as standalone tokens, CAC, CHR-NNN,
# and the literal phrases "chronicle anchor", "issue type", "severity class".
_CODE_RE = re.compile(
    r"\b(?:CLARK-\d+|CLARK|P[012]|CAC|CHR-\d+|chronicle\s+anchor|issue\s+type|severity\s+class)\b",
    flags=re.IGNORECASE,
)


# ── Palette (serif memo, paper-like) ──────────────────────────────────────────

_BG       = "#FAFAFA"
_INK      = "#1A2332"
_MUTED    = "#5A6778"
_HAIRLINE = "#D8DEE6"
_ACCENT   = "#1F3A5F"
_ALARM    = "#B7322C"
_SERIF    = "Georgia, 'Times New Roman', serif"
_SANS     = "-apple-system, 'Segoe UI', Roboto, Arial, sans-serif"
_MONO     = "'SF Mono', Consolas, 'Courier New', monospace"


# ── IO helpers ────────────────────────────────────────────────────────────────

def _load_distribution() -> list[dict]:
    if not _DISTRIBUTION_YAML.exists():
        return []
    try:
        raw = yaml.safe_load(_DISTRIBUTION_YAML.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("[briefing_email] distribution.yaml load failed: %s", exc)
        return []
    return [r for r in (raw.get("recipients") or []) if isinstance(r, dict) and r.get("email")]


def _sha256_hex(s: str) -> str:
    import hashlib
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def _quote_sigs(quotes: list[dict]) -> list[dict]:
    """MIL-56 — per-slot signatures for the audit log. Enables MIL-57 dedup
    and per-auditor reconstruction of evidence trail per send."""
    return [
        {
            "slot":          i,
            "source":        q.get("source", ""),
            "text_sha256":   _sha256_hex(q.get("text", "")),
            "original_date": (q.get("date") or "")[:10],
        }
        for i, q in enumerate(quotes or [], 1)
    ]


def _log_send(recipient: str, subject: str, status: str, error: str = "",
              run=None, date: str | None = None, priority_issue: str | None = None,
              headline: str | None = None, lede_sha256: str | None = None,
              quote_sigs: list[dict] | None = None) -> None:
    """Append one record per recipient x send to email_log.jsonl.

    MIL-56: on status='ok', record the audit fields (headline, lede_sha256,
    quote_sigs, run, date, priority_issue) so MIL-57 rotation + MIL-58
    same-story detection can read the log. Pre-send selections are not
    commitments — audit fields are omitted on status='error' entries.
    """
    try:
        _EMAIL_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "recipient": recipient,
            "subject":   subject,
            "status":    status,
            "error":     error,
        }
        if status == "ok":
            if run is not None:            entry["run"] = run
            if date is not None:           entry["date"] = date
            if priority_issue is not None: entry["priority_issue"] = priority_issue
            if headline is not None:       entry["headline"] = headline
            if lede_sha256 is not None:    entry["lede_sha256"] = lede_sha256
            if quote_sigs is not None:     entry["quote_sigs"] = quote_sigs
        with _EMAIL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("[briefing_email] email_log append failed: %s", exc)


def _esc(s) -> str:
    if not isinstance(s, str):
        s = "" if s is None else str(s)
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


def _scrub_codes(text: str) -> str:
    """Apply principle 6 — strip pipeline artefacts from reader-facing prose."""
    out = _CODE_RE.sub("", text or "")
    # Tidy up punctuation/whitespace left by removals
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([.,;:!?])", r"\1", out)
    return out.strip()


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


_ENTITY_MAP = {
    "&middot;": "·", "&ldquo;": "“", "&rdquo;": "”",
    "&mdash;": "—", "&ndash;": "–",
    "&darr;": "↓", "&uarr;": "↑", "&rarr;": "→",
    "&ge;": "≥", "&le;": "≤", "&times;": "×",
    "&amp;": "&", "&quot;": "\"", "&apos;": "'",
    "&#39;": "'", "&lsquo;": "‘", "&rsquo;": "’",
    "&nbsp;": " ",
}


def _entity_decode(s: str) -> str:
    for k, v in _ENTITY_MAP.items():
        s = s.replace(k, v)
    return s


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", _entity_decode(_strip_tags(s))).strip()


def _date_sort_key(dstr: str) -> int:
    if not dstr:
        return 0
    digits = re.sub(r"\D", "", dstr[:10])
    try:
        return int(digits) if digits else 0
    except Exception:
        return 0


# ── Box 3 priority-issue lookup (minimal; only need priority_issue) ───────────

def _priority_issue_from_html(html: str) -> str | None:
    cls_marker = 'class="topbar-box exec-alert-panel"'
    cls_idx = html.find(cls_marker)
    if cls_idx == -1:
        return None
    start = html.rfind("<div", 0, cls_idx)
    if start == -1:
        return None
    depth = 0
    i = start
    section = ""
    while i < len(html):
        if html[i:i+4] == "<div":
            depth += 1
            i += 4
        elif html[i:i+6] == "</div>":
            depth -= 1
            if depth == 0:
                section = html[start:i+6]
                break
            i += 6
        else:
            i += 1
    if not section:
        return None
    m = re.search(r"<strong[^>]*color:#FFD580[^>]*>(.*?)</strong>", section, re.DOTALL)
    return _clean(m.group(1)) if m else None


def _load_priority_issue() -> str | None:
    if not _BRIEFING_HTML.exists():
        return None
    try:
        return _priority_issue_from_html(_BRIEFING_HTML.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[briefing_email] priority lookup failed: %s", exc)
        return None


# ── Commentary lookup (today's prose per issue) ───────────────────────────────

def _load_commentary(priority_issue: str, date: str) -> dict | None:
    if not _COMMENTARY_LOG.exists():
        return None
    matches = []
    try:
        for line in _COMMENTARY_LOG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (e.get("issue_type") or "") == priority_issue and (e.get("date") or "") == date:
                matches.append(e)
    except Exception as exc:
        logger.warning("[briefing_email] commentary_log read failed: %s", exc)
        return None
    if not matches:
        return None
    # Prefer risk cards; if multiple, the longest prose is usually the canonical Box 3 copy.
    matches.sort(key=lambda e: (0 if (e.get("type") == "risk") else 1, -len(e.get("prose") or "")))
    return matches[0]


# ── Verbatim quote selection (principle 1 — NEVER modify text) ────────────────

def _collect_quote_candidates(priority_issue: str) -> dict[str, list[dict]]:
    """Return {source_label: [candidate, ...]}, each candidate has keys
    {source, date, text, severity}."""
    out: dict[str, list[dict]] = {label: [] for label, *_ in _SOURCES}
    for label, fname, text_f, date_f in _SOURCES:
        fp = _ENRICHED_DIR / fname
        if not fp.exists():
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            recs = data.get("records") if isinstance(data, dict) else data
        except Exception as exc:
            logger.warning("[briefing_email] load %s failed: %s", fname, exc)
            continue
        for r in recs or []:
            if not isinstance(r, dict):
                continue
            if (r.get("issue_type") or "").strip() != priority_issue:
                continue
            sev = (r.get("severity_class") or "").strip()
            if sev not in _QUALIFYING_SEVERITIES:
                continue
            text = r.get(text_f)
            if not isinstance(text, str):
                continue
            text = text.strip()
            if len(text) < 40:
                continue
            out[label].append({
                "source":   label,
                "date":     r.get(date_f) or "",
                "text":     text,   # VERBATIM — do not touch
                "severity": sev,
            })
    return out


def _pick_verbatims(priority_issue: str) -> list[dict]:
    """Up to three quotes. One App Store, one Google Play, one best-of-other."""
    buckets = _collect_quote_candidates(priority_issue)

    def rank(c: dict):
        sev_score = 0 if c["severity"] == "P0" else 1
        length    = len(c["text"])
        length_score = 0 if 80 <= length <= 320 else 1
        return (sev_score, length_score, -_date_sort_key(c["date"]))

    picks: list[dict] = []
    # Slot 1+2: stores
    for label in ("App Store", "Google Play"):
        cands = sorted(buckets.get(label, []), key=rank)
        if cands:
            picks.append(cands[0])
    # Slot 3: first non-empty non-store source
    for label in ("Reddit", "YouTube", "DownDetector"):
        cands = sorted(buckets.get(label, []), key=rank)
        if cands:
            picks.append(cands[0])
            break
    return picks[:3]


def _format_date_short(dstr: str) -> str:
    if not dstr:
        return ""
    try:
        # Tolerate ISO timestamps, pick the date part
        s = dstr[:10]
        d = datetime.strptime(s, "%Y-%m-%d")
        return d.strftime("%-d %b %Y") if os.name != "nt" else d.strftime("%#d %b %Y")
    except Exception:
        return dstr[:10]


# ── Facts + Opus lede ─────────────────────────────────────────────────────────

def _diagnostic_notes(quotes: list[dict]) -> str:
    """Distil salient diagnostic details from quotes for the Opus user prompt."""
    if not quotes:
        return "no diagnostic specifics surfaced"
    patterns = [
        (r"android\s*\d+(?:\.\d+)?", "Android version"),
        (r"ios\s*\d+(?:\.\d+)?",     "iOS version"),
        (r"one\s*ui\s*[\d.]+",       "OneUI version"),
        (r"(iphone|samsung|pixel|oneplus|xiaomi)", "device family"),
    ]
    found: list[str] = []
    for q in quotes:
        low = q["text"].lower()
        for pat, _ in patterns:
            m = re.search(pat, low)
            if m:
                found.append(m.group(0))
    lines = []
    if found:
        lines.append("device/OS mentions: " + ", ".join(sorted(set(found))))
    # Note broken surfaces hinted at via frequent nouns
    noun_hits = []
    for noun in ("pin", "otp", "card controls", "barclaycard", "cache",
                 "login", "password", "biometric", "face id", "transfer", "payment"):
        if sum(noun in q["text"].lower() for q in quotes) >= 2:
            noun_hits.append(noun)
    if noun_hits:
        lines.append("surfaces named across multiple quotes: " + ", ".join(noun_hits))
    return "; ".join(lines) if lines else "no diagnostic specifics surfaced"


def _build_facts(commentary: dict, quotes: list[dict], run_entry: dict,
                 all_candidate_quotes: list[dict] | None = None) -> dict:
    # chr_resonance may be str or list[str] in the commentary log schema — normalise
    chr_raw = commentary.get("chr_resonance")
    if isinstance(chr_raw, list):
        chr_text = " ".join(str(x) for x in chr_raw)
    elif isinstance(chr_raw, str):
        chr_text = chr_raw
    else:
        chr_text = ""

    # Diagnostic fact scan runs over every matching quote, not just the three
    # displayed, so a long rambling-but-informative review still surfaces its
    # OS/device details even when we skip it for the quote block.
    diag_pool = all_candidate_quotes if all_candidate_quotes else quotes

    return {
        "run_number":       run_entry.get("run", "?"),
        "date":             run_entry.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "priority_issue":   commentary.get("issue_type") or "",
        "barclays_rate":    commentary.get("barclays_rate"),
        "peer_avg":         commentary.get("peer_avg_rate"),
        "gap_pp":           commentary.get("gap_pp"),
        "days_active":      commentary.get("days_active") or 0,
        "first_seen":       commentary.get("first_seen") or "",
        "dominant_sev":     commentary.get("dominant_severity") or "",
        "commentary_prose": _scrub_codes(commentary.get("prose") or ""),
        "chr_precedent":    _scrub_codes(chr_text) or "no direct precedent on file",
        "diagnostic_notes": _diagnostic_notes(diag_pool),
        "quotes":           quotes,
    }


_OPUS_SYSTEM_PROMPT = """You are the senior analyst producing Sonar's daily Barclays intelligence memo. Your reader is a UK retail banking executive who will skim this in Outlook or have it pasted into Microsoft Teams, reading between meetings. Your job is to make them understand the shape of today's strongest public signal in under 30 seconds of reading the opening paragraph.

You write like an analyst at a serious institution — Bank of England briefings, the Economist's banking coverage, Goldman Global Strategy memos. Not like a product manager, not like a copywriter. Observe patterns. Surface consequence. Cite precedent. Never issue orders.

These principles are binding. A violation is a rewrite:

1. VERBATIM IS SACRED. You will receive verbatim customer quotes as context. They appear separately below your paragraph. Do not reproduce them, paraphrase them, or retell their scenario in your own words. Two specific traps:
   (a) any run of 4+ consecutive words lifted from a quote (e.g. "cache-clearing is ineffective") is a violation — including when wrapped in reporter framing ("customers describe cache-clearing is ineffective"). Even partial lifts count if the distinctive word ordering is preserved.
   (b) renaming a quote's trigger in your own words is also a violation. If Quote [2] says "crashes when not main focus window" and you write "fails when switched into a background state" or "the app becoming unusable once a second application is brought forward", you have retold the quote's cause-and-effect story as an authorial claim. The quote said WHEN it breaks; you added the author's framing of the mechanism. Both are prohibited.
   The safe pattern is to describe EFFECTS and COUNTABLE PATTERNS only: "PIN retrieval is named across multiple reports", "severity observations cluster at the most acute tier". If you cannot describe the pattern without borrowing the quote's own framing, leave it out — the quotes speak for themselves in the block below.

2. DENOMINATORS ALWAYS NAMED. No percentage without saying what it is a percentage OF. No "sustained" without days. No "peer average" without listing the peers in the cohort at least once.

3. JUDGMENTS BACK-SOURCED. Any claim touching regulatory consequence, customer switching, or reputational damage must either (a) cite a precedent whose record in the FACTS block EXPLICITLY contains the same consequence (if you claim a precedent "drew regulatory attention", the FACTS precedent description must name regulator / regulatory / FCA / supervision — do not infer regulator involvement from duration or severity alone), or (b) soften to analytic observation ("a pattern of this shape is consistent with"). The precedent's temporal shape ("ran three weeks before a fix") is not a source for regulatory or switching consequences — it only supports duration comparisons. Bare assertions are always a failure.

4. CONFIDENCE STATED. Your closing sentence names a confidence rating using exactly one of: "Confidence: low", "Confidence: medium", or "Confidence: high", followed by a one-clause justification grounded in the data shape.

5. ANALYST VOICE, NEVER OPERATOR VOICE. Banned verbs when referring to what Barclays should do: ship, fix, deploy, mandate, issue, convene, escalate, address, resolve, launch, rollout. Allowed analytic verbs: describe, report, cluster, suggest, point to, is consistent with, mirrors, measures, holds, exposes, invites.

6. NO INTERNAL CODES. Never write: CLARK, CLARK-1, CLARK-2, CLARK-3, P0, P1, P2, CAC, CHR-001 (or any CHR-NNN), "chronicle anchor", "issue type", "severity class". These are pipeline artefacts. Translate to plain analytic English.

7. LEAD WITH POSITION, PROPORTION, AND THE MOST DIAGNOSTIC FACT. Sentence 1: where Barclays sits against the cohort, with sustained days. Sentence 2: how narrow or broad the signal is, with explicit denominator. Sentences 3-4: the sharpest single diagnostic fact available, then the pattern that cuts across quotes. "Sharpest diagnostic" means the most telling COUNTABLE PATTERN across evidence, not a code-level root cause. You have exactly three moves available for that sentence: (i) name the convergence ("device detail converges on Android 16 and Samsung hardware"); (ii) name surface concentration ("PIN, Barclaycard, transfer, and payment each appear more than once across the quotes"); (iii) name the temporal or severity shape ("all severity observations cluster at the most acute tier across fifteen days"). Do not reach for a fourth move that explains WHY the app breaks — that is principle 8.

8. NO UNSUPPORTED ENGINEERING DIAGNOSIS. Do not name WHY the app breaks — only WHEN and WHERE it is observed to break, as a counted pattern. Three trap shapes:
   (a) named mechanism nouns — "race condition", "background-state failure", "cache corruption", "state-persistence bug", "session-token expiry", "IdP timeout", "deploy regression", "SDK issue", "foreground focus", "cold-start defect", "memory leak", "thread contention", "multi-app behaviour" — or any similar mechanism-level noun phrase, whether in the banned list or a near neighbour.
   (b) implicit mechanism via trigger-naming — "failure is triggered by X", "breaks once Y happens", "crashes when switched to Z". Even if no banned noun appears, you are asserting the app's internal logic failed because X/Y/Z occurred, which is mechanism inference. This trap catches authors who think they are only reporting an observation; if the sentence tells the reader WHY it breaks, it fails this principle.
   (c) implicit mechanism via solution-failure framing — "self-remediation steps do not restore function", "cache-clearing narrows the plausible surface to non-transient faults", "standard recovery steps are reported as ineffective". These diagnose the fault by diagnosing what doesn't fix it.
   ALLOWED: countable cross-quote patterns ("complaints cluster on Android 16 devices", "three surfaces are named across reports", "severity observations cluster at the most acute tier"). If a mechanism-level claim is genuinely warranted, it MUST be hedged — "is consistent with", "mirrors the shape of", "a pattern of this shape suggests" — and the hedge must be unambiguous.

You output STRICT JSON only. No preamble, no markdown fences, no commentary about the task. Exactly this shape:

{"headline": "<declarative news-style sentence, no more than 90 characters, contains 'Barclays', no internal codes, no colon>", "lede": "<opening paragraph of the memo, 140-200 words, follows principles 1-7 above>"}

REJECTED DRAFT SHAPES (from recent sends — anything matching these will be rewritten):

REJECTED (principles 1, 8): "customers describe the app becoming unusable once a second application is brought forward on the device, a pattern that suggests the failure is triggered by ordinary multi-app behaviour rather than a rare edge case"
    — why: "second application is brought forward" retells Quote [2]'s scenario in the author's words; "triggered by ordinary multi-app behaviour" is mechanism inference without any banned noun.

REJECTED (principles 1, 8): "the sharpest diagnostic is that customers describe the app failing when switched into a background state, with standard self-remediation steps reported as not restoring function"
    — why: "background state" is the author's technical rename of Quote [2]'s "not main focus window"; "self-remediation steps reported as not restoring function" is solution-failure inference.

REJECTED (principle 3): "mirrors the HSBC 2025 post-refresh episode, which ran three weeks before a fix, drew regulator attention"
    — why: the FACTS precedent entry names the duration; if it does not name regulator involvement, "drew regulator attention" is bare assertion.

PREFERRED PATTERNS:

"Across the verbatims, multiple reports name PIN retrieval, transfers, and cache as failure surfaces; device detail converges on Android 16 and Samsung hardware. Severity observations cluster at the most acute tier." — countable pattern, no mechanism, no quote retelling.

"The duration and surface concentration echo the shape of the HSBC 2025 post-refresh episode, which ran three weeks before resolution." — hedged precedent; temporal claim backed by precedent's own temporal record.
"""


def _build_user_prompt(facts: dict) -> str:
    q = facts["quotes"]
    quote_lines = []
    for i, x in enumerate(q, 1):
        quote_lines.append(f"[{i}] {x['source']}, {_format_date_short(x['date'])}: {x['text']}")
    quotes_block = "\n".join(quote_lines) if quote_lines else "(no qualifying quotes this cycle)"

    rate  = facts["barclays_rate"]
    pavg  = facts["peer_avg"]
    gap   = facts["gap_pp"]
    rate_s = f"{rate:.1f}%" if isinstance(rate, (int, float)) else "?"
    pavg_s = f"{pavg:.1f}%" if isinstance(pavg, (int, float)) else "?"
    gap_s  = f"{gap:+.1f}pp" if isinstance(gap, (int, float)) else "?"

    return f"""FACTS FOR TODAY (run {facts['run_number']}, {facts['date']}):

Priority issue surfaced: {facts['priority_issue']}
Barclays rate vs cohort: {rate_s} against cohort average {pavg_s} (gap {gap_s})
Cohort (6 UK peers): Barclays, {', '.join(_COHORT_PEERS)}
Sustained since: {facts['first_seen']} ({facts['days_active']} days)
Dominant severity observed: {facts['dominant_sev']}
Diagnostic details observable in the quotes: {facts['diagnostic_notes']}
Precedent on file: {facts['chr_precedent']} (cite only if directly analogous; otherwise ignore)

TODAY'S ANALYST COMMENTARY (for context — do NOT restate in the lede, set it up):
{facts['commentary_prose']}

VERBATIM QUOTES INCLUDED IN THE EMAIL (for your awareness — do NOT quote or paraphrase in your paragraph):
{quotes_block}

OUTPUT:
"""


_VERIFIER_SYSTEM_PROMPT = """You are a strict factual verifier for an executive intelligence memo. You receive the FACTS block that was handed to the author, the verbatim QUOTES that were handed to the author, and the AUTHOR'S OUTPUT (headline + lede). Your job is to check whether the author stayed within the evidence and obeyed the drafting principles.

For each principle below, decide PASS or FAIL. If FAIL, record the offending text and which principle it breaches.

ANTI-HALLUCINATION RULE: every violation you record MUST quote EXACT TEXT FROM THE LEDE (or headline). Never quote text from the QUOTES block or FACTS block as evidence that the lede violated a principle — that text is not in the lede. Before logging a violation, confirm the offending phrase appears verbatim in the AUTHOR'S HEADLINE or AUTHOR'S LEDE. If it doesn't, don't flag it.

TIE-BREAK RULE: if a phrase could be read as either (a) a countable cross-quote pattern (allowed by principle 7) or (b) mechanism inference (forbidden by principle 8), prefer (a) and do not flag. Only flag unambiguous mechanism inference.

Principles (apply strictly — but read the scope notes before flagging):

1. VERBATIM NOT REWRITTEN — applies ONLY to the customer QUOTES, not the FACTS block. The author must not paraphrase, embed, or retell any customer quote's scenario inside their prose. Two trigger conditions: (a) a run of 4+ consecutive words lifted from a quote (or near-lifted with trivial word swaps that preserve distinctive ordering) is a FAIL; (b) renaming the quote's trigger in the author's words — e.g. Quote says "crashes when not main focus window" and author writes "fails when switched into a background state" or "becomes unusable when a second application is brought forward" — is also a FAIL, because the author has retold the quote's cause-and-effect story as an authorial claim. Rephrasing numbers, dates, cohort names, and precedent references from the FACTS block is expected — do NOT flag that.

2. DENOMINATORS NAMED — the PRIMARY claim (cohort position + proportion) must carry an explicit denominator (percentages name "of what"; "sustained" names days; peer average names the cohort). Secondary observations introduced later (e.g. "clusters on Android 16 devices", "three surfaces named across quotes") inherit the same sample and do NOT need their own fresh denominator — do not flag these.

3. JUDGMENTS BACK-SOURCED — any claim touching regulatory consequence, customer switching, or reputational damage either cites a concrete precedent from the FACTS block (the "Precedent on file" line is a valid source) or uses hedge language ("consistent with", "mirrors", "a pattern of this shape"). Bare assertions of regulatory exposure are a FAIL; referencing a precedent the FACTS block names is NOT a bare assertion.

4. CONFIDENCE STATED — the lede contains exactly one of: "Confidence: low", "Confidence: medium", or "Confidence: high", followed by a justification clause (introduced by "given", "because", "due to", or similar).

5. ANALYST VOICE — the author uses no imperative verbs directed at Barclays: ship, fix, deploy, mandate, issue, convene, escalate, address, resolve, launch, rollout.

6. NO INTERNAL CODES — these must be absent from both headline and lede: CLARK, CLARK-1/2/3, P0, P1, P2, CAC, CHR-NNN, "chronicle anchor", "issue type", "severity class".

7. STRUCTURAL LEAD — within the first three sentences of the LEDE (not the headline), establish both cohort position and proportion with named denominator. The HEADLINE is a compact news-style label; it does NOT need to carry a denominator — its job is to name the core claim, and disambiguation lives in the lede. Do not flag the headline for missing denominator.

8. NO UNSUPPORTED ENGINEERING DIAGNOSIS — the author must not assert a TECHNICAL MECHANISM (the "why it breaks at the code level") unless a verbatim quote explicitly names that mechanism. Three trap shapes to flag as FAIL (all apply even if the phrase is not in any banned list):
   (a) named mechanism noun — "background-state failure", "race condition", "cache corruption", "state-persistence bug", "session-token expiry", "IdP timeout", "deploy regression", "SDK issue", "memory leak", "multi-app behaviour", or any similar mechanism-level noun phrase.
   (b) implicit mechanism via trigger-naming — "failure is triggered by X", "breaks once Y happens", "crashes when switched to Z", "becomes unusable when a second application is brought forward". If the sentence tells the reader WHY it breaks by naming an authorial trigger not verbatim in a quote, FAIL.
   (c) implicit mechanism via solution-failure framing — "self-remediation steps do not restore function", "cache-clearing narrows the plausible surface to non-transient faults". Diagnosing the fault by diagnosing what doesn't fix it is also mechanism inference.
   ALLOWED (do NOT flag these shapes — they are principle 7's three sanctioned diagnostic moves):
     (i) convergence framing: "device detail converges on Android 16 and Samsung hardware", "Android 16 and Samsung hardware recur across reports", "device family converges on Samsung", "complaints cluster on Android 16 devices";
     (ii) surface concentration: "PIN, Barclaycard, transfer, cache, and payment are each named across reports", "three surfaces named across quotes", "multiple reports name X as a failure surface";
     (iii) temporal/severity pattern: "severity observations cluster at the most acute tier", "reports persist across fifteen consecutive days", "all severity markers sit at the most acute tier".
   Hedged mechanism claims introduced by "is consistent with", "mirrors the shape of", "a pattern of this shape suggests", "echoes the shape of" are always acceptable. Confidence-clause hedges ("the verbatim base is thin", "device convergence rests on a small number of reports", "given fifteen-day persistence") are principle-4 justifications, not mechanism claims — do NOT flag them under principle 8.

FACT ACCURACY: every numeric claim in the headline and lede (%, rank, days, multiplier) must be either present in the FACTS block or trivially derivable from it (e.g. 12.8 vs 6.0 rounds to "about 2.1x"; a 6.8pp gap of 12.8/6.0 rates is also "more than twice"). Flag any number that does NOT appear in or derive from the FACTS block.

Output STRICT JSON only. No preamble, no markdown fences. Exactly this shape:

{"pass": <true iff every principle is PASS and every number is supported>, "violations": ["principle N: <short quote of offending text or description>"], "notes": "<one-sentence summary>"}"""


def _build_verifier_user_prompt(facts: dict, headline: str, lede: str) -> str:
    q_lines = []
    for i, x in enumerate(facts.get("quotes") or [], 1):
        q_lines.append(f"[{i}] {x['source']}, {_format_date_short(x['date'])}: {x['text']}")
    quotes_block = "\n".join(q_lines) if q_lines else "(none)"

    rate  = facts.get("barclays_rate")
    pavg  = facts.get("peer_avg")
    gap   = facts.get("gap_pp")
    rate_s = f"{rate:.1f}%" if isinstance(rate, (int, float)) else "?"
    pavg_s = f"{pavg:.1f}%" if isinstance(pavg, (int, float)) else "?"
    gap_s  = f"{gap:+.1f}pp" if isinstance(gap, (int, float)) else "?"

    return f"""FACTS PROVIDED TO AUTHOR:
Priority issue: {facts.get('priority_issue', '')}
Barclays rate vs cohort: {rate_s} against cohort average {pavg_s} (gap {gap_s})
Cohort: Barclays, {', '.join(_COHORT_PEERS)}
Sustained since: {facts.get('first_seen', '')} ({facts.get('days_active', 0)} days)
Dominant severity: {facts.get('dominant_sev', '')}
Diagnostic details from quotes: {facts.get('diagnostic_notes', '')}
Precedent on file: {facts.get('chr_precedent', '')}

QUOTES PROVIDED TO AUTHOR:
{quotes_block}

AUTHOR'S HEADLINE:
{headline}

AUTHOR'S LEDE:
{lede}

VERIFY:
"""


def _verify_lede(facts: dict, headline: str, lede: str) -> dict:
    """Returns {pass: bool, violations: list[str], notes: str}. Never raises."""
    try:
        from mil.config.model_client import call_anthropic, CircuitBreakerError
    except ImportError as exc:
        logger.warning("[briefing_email] verifier import failed: %s", exc)
        return {"pass": True, "violations": [], "notes": f"verifier unavailable: {exc}"}

    user_prompt = _build_verifier_user_prompt(facts, headline, lede)
    try:
        raw = call_anthropic(
            task="briefing_verifier",
            user_prompt=user_prompt,
            system=_VERIFIER_SYSTEM_PROMPT,
            max_tokens=512,
            cache_system=True,
        )
    except CircuitBreakerError as exc:
        logger.warning("[briefing_email] verifier circuit-breaker tripped: %s", exc)
        return {"pass": True, "violations": [], "notes": f"verifier CB: {exc}"}
    except Exception as exc:
        logger.warning("[briefing_email] verifier call failed: %s", exc)
        return {"pass": True, "violations": [], "notes": f"verifier error: {exc}"}

    try:
        body = raw.strip()
        fence = re.match(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.DOTALL)
        if fence:
            body = fence.group(1)
        else:
            inner = re.search(r"\{.*\}", body, re.DOTALL)
            if inner:
                body = inner.group(0)
        data = json.loads(body)
    except (json.JSONDecodeError, AttributeError):
        logger.warning("[briefing_email] verifier output not JSON (fail-safe → pass=False): %r", raw[:200])
        return {
            "pass":       False,
            "violations": ["verifier output unparseable — fail-safe default"],
            "notes":      "verifier output unparseable",
        }

    return {
        "pass":       bool(data.get("pass", True)),
        "violations": list(data.get("violations") or []),
        "notes":      str(data.get("notes") or ""),
    }


def _regenerate_with_corrections(facts: dict, draft_headline: str, draft_lede: str,
                                  violations: list[str]) -> dict | None:
    """One retry after a verifier fail. Feeds violations back as corrections."""
    correction_block = "\n".join(f"- {v}" for v in violations)
    user_prompt = _build_user_prompt(facts) + (
        f"\nYour previous draft had these verifier violations:\n{correction_block}\n\n"
        f"Previous draft (do NOT keep verbatim — rewrite to address each violation):\n"
        f"  headline: {draft_headline}\n  lede: {draft_lede}\n\nRewrite OUTPUT:\n"
    )
    try:
        from mil.config.model_client import call_anthropic, CircuitBreakerError
        raw = call_anthropic(
            task="briefing_lede",
            user_prompt=user_prompt,
            system=_OPUS_SYSTEM_PROMPT,
            max_tokens=800,
            cache_system=True,
        )
    except CircuitBreakerError as exc:
        logger.warning("[briefing_email] retry CB tripped: %s", exc)
        return None
    except Exception as exc:
        logger.warning("[briefing_email] retry call failed: %s", exc)
        return None

    try:
        body = raw.strip()
        fence = re.match(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.DOTALL)
        if fence:
            body = fence.group(1)
        data = json.loads(body)
    except (json.JSONDecodeError, AttributeError):
        logger.warning("[briefing_email] retry output not JSON: %r", raw[:200])
        return None

    headline = _scrub_codes((data.get("headline") or "").strip())
    lede     = _scrub_codes((data.get("lede") or "").strip())
    if not headline or not lede:
        return None
    return {"headline": headline, "lede": lede}


def _load_cached_lede(run_number) -> dict | None:
    if not _LEDE_CACHE.exists():
        return None
    try:
        for line in _LEDE_CACHE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("run") == run_number and e.get("headline") and e.get("lede"):
                return e
    except Exception:
        pass
    return None


def _cache_lede(run_number, headline: str, lede: str, prompt_hash: str,
                verify_first: dict | None = None, verify_final: dict | None = None,
                regenerated: bool = False) -> None:
    try:
        _LEDE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp":    datetime.now(timezone.utc).isoformat(),
            "run":          run_number,
            "headline":     headline,
            "lede":         lede,
            "prompt_hash":  prompt_hash,
            "regenerated":  regenerated,
        }
        if verify_first is not None:
            entry["verify_first"] = verify_first
        if verify_final is not None:
            entry["verify_final"] = verify_final
        with _LEDE_CACHE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("[briefing_email] lede cache write failed: %s", exc)


def _generate_lede(facts: dict) -> dict | None:
    """Call Opus 4.7. Returns {headline, lede} or None on failure. Scrubbed for codes."""
    import hashlib
    user_prompt  = _build_user_prompt(facts)
    prompt_hash  = hashlib.md5((_OPUS_SYSTEM_PROMPT + user_prompt).encode("utf-8")).hexdigest()[:8]

    try:
        from mil.config.model_client import call_anthropic, CircuitBreakerError
    except ImportError as exc:
        logger.warning("[briefing_email] model_client import failed: %s", exc)
        return None

    try:
        raw = call_anthropic(
            task="briefing_lede",
            user_prompt=user_prompt,
            system=_OPUS_SYSTEM_PROMPT,
            max_tokens=800,
            cache_system=True,
        )
    except CircuitBreakerError as exc:
        logger.warning("[briefing_email] opus circuit-breaker tripped: %s", exc)
        return None
    except Exception as exc:
        logger.warning("[briefing_email] opus call failed: %s", exc)
        return None

    try:
        # Tolerate fenced JSON if Opus gets chatty (principle 6 says not to, but be safe)
        body = raw.strip()
        fence = re.match(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.DOTALL)
        if fence:
            body = fence.group(1)
        data = json.loads(body)
    except (json.JSONDecodeError, AttributeError):
        logger.warning("[briefing_email] opus output not JSON: %r", raw[:200])
        return None

    headline = _scrub_codes((data.get("headline") or "").strip())
    lede     = _scrub_codes((data.get("lede") or "").strip())
    if not headline or not lede:
        return None
    if "Confidence:" not in lede:
        logger.info("[briefing_email] opus lede missing 'Confidence:' line — accepting anyway, principle 4 relaxed")

    return {"headline": headline, "lede": lede, "prompt_hash": prompt_hash}


# ── Silent-day guard ──────────────────────────────────────────────────────────

def _is_silent_day(commentary: dict | None) -> tuple[bool, str]:
    """Returns (silent, reason). Principle 9 — no email when no issue clears."""
    if commentary is None:
        return True, "no commentary for priority issue today"
    try:
        days_active = int(commentary.get("days_active") or 0)
    except Exception:
        days_active = 0
    if days_active < _MIN_DAYS_ACTIVE:
        return True, f"days_active={days_active} below threshold {_MIN_DAYS_ACTIVE}"
    try:
        gap_pp = float(commentary.get("gap_pp") or 0.0)
    except Exception:
        gap_pp = 0.0
    severity = (commentary.get("dominant_severity") or "").strip()
    qualifies = gap_pp >= _MIN_GAP_PP or severity in _QUALIFYING_SEVERITIES
    if not qualifies:
        return True, f"gap_pp={gap_pp} below {_MIN_GAP_PP} and severity={severity!r} outside {_QUALIFYING_SEVERITIES}"
    return False, "qualifying: sustained, material gap or severity"


# ── Template builders ────────────────────────────────────────────────────────

def _build_plaintext(recipient: dict, headline: str, lede: str,
                     date: str, quotes: list[dict]) -> str:
    lines = [
        _SUBJECT_LINE,
        "",
        headline,
        "",
        "Dear Team,",
        "",
        lede,
        "",
    ]
    if quotes:
        lines.append("Voices from the cycle:")
        lines.append("")
        for q in quotes:
            lines.append(f'  "{q["text"]}"')
            lines.append(f"  — {q['source']}, {_format_date_short(q['date'])}")
            lines.append("")

    used_sources = sorted({q["source"] for q in quotes})
    all_sources  = [s[0] for s in _SOURCES]
    absent       = [s for s in all_sources if s not in used_sources]
    footer_bits  = [
        "Public-signal intelligence.",
        f"Quote sources this cycle: {', '.join(used_sources) or 'none'}.",
    ]
    if absent:
        footer_bits.append(f"No directly matching reports from: {', '.join(absent)}.")
    footer_bits.append(f"Full evidence trail: {_BRIEFING_URL}")
    lines.append(" ".join(footer_bits))
    if date:
        lines.append(f"Brief date: {date}")
    return "\n".join(lines) + "\n"


def _html_quote_block(quotes: list[dict]) -> str:
    if not quotes:
        return ""
    blocks = []
    for q in quotes:
        blocks.append(
            f'<blockquote style="margin:0 0 18px 0;padding:12px 18px;'
            f'border-left:3px solid {_ACCENT};background:#FFFFFF;'
            f'font-family:{_SERIF};font-style:italic;font-size:14px;'
            f'color:{_INK};line-height:1.55;">'
            f'“{_esc(q["text"])}”'
            f'<div style="margin-top:10px;font-family:{_SANS};font-style:normal;'
            f'font-size:11px;color:{_MUTED};letter-spacing:0.4px;">'
            f'— {_esc(q["source"])}, {_esc(_format_date_short(q["date"]))}'
            f'</div></blockquote>'
        )
    return "".join(blocks)


def _build_html(recipient: dict, headline: str, lede: str,
                quotes: list[dict]) -> str:
    header_strip = (
        f'<div style="font-family:{_MONO};font-size:11px;color:{_MUTED};'
        f'letter-spacing:0.3px;padding:8px 12px;background:#FFFFFF;'
        f'border:1px solid {_HAIRLINE};border-radius:3px;margin-bottom:22px;'
        f'word-break:break-word;">{_esc(_SUBJECT_LINE)}</div>'
    )

    headline_block = (
        f'<h1 style="margin:0 0 18px 0;font-family:{_SERIF};font-size:22px;'
        f'font-weight:700;color:{_INK};line-height:1.3;">{_esc(headline)}</h1>'
    )

    salute = (
        f'<p style="margin:0 0 14px 0;font-family:{_SERIF};font-size:15px;'
        f'color:{_INK};">Dear Team,</p>'
    )

    lede_html = (
        f'<p style="margin:0 0 22px 0;font-family:{_SERIF};font-size:14.5px;'
        f'color:{_INK};line-height:1.65;">{_esc(lede)}</p>'
    )

    used_sources = sorted({q["source"] for q in quotes})
    all_sources  = [s[0] for s in _SOURCES]
    absent       = [s for s in all_sources if s not in used_sources]
    footer_parts = [
        "Public-signal intelligence.",
        f"Quote sources this cycle: {', '.join(used_sources) or 'none'}.",
    ]
    if absent:
        footer_parts.append(f"No directly matching reports from: {', '.join(absent)}.")
    footer_parts.append(
        f'Full evidence trail: <a href="{_BRIEFING_URL}" '
        f'style="color:{_ACCENT};text-decoration:underline;">cjipro.com/briefing-v4</a>'
    )
    footer_html = (
        f'<p style="margin:28px 0 0 0;font-family:{_SANS};font-size:11px;'
        f'color:{_MUTED};line-height:1.6;border-top:1px solid {_HAIRLINE};'
        f'padding-top:14px;">{" ".join(footer_parts)}</p>'
    )

    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_esc(_SUBJECT_LINE)}</title></head>'
        f'<body style="margin:0;padding:0;background:{_BG};">'
        f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:{_BG};">'
        f'<tr><td align="center" style="padding:24px 12px;">'
        f'<table role="presentation" cellpadding="0" cellspacing="0" width="640" style="max-width:640px;width:100%;background:{_BG};">'
        f'<tr><td style="padding:8px 20px;">'
        f'{header_strip}{headline_block}{salute}{lede_html}'
        f'{_html_quote_block(quotes)}{footer_html}'
        f'</td></tr></table></td></tr></table>'
        '</body></html>'
    )


# ── SMTP send ─────────────────────────────────────────────────────────────────

def send_briefing_notification(run_entry: dict) -> dict:
    """Main entry. Returns {sent, failed, skipped, silent}. Never raises.

    Silent-day short-circuit happens before SMTP creds are even checked — we
    want the pipeline to make its 'should-send?' decision purely from data,
    not from deployment state.
    """
    result = {"sent": 0, "failed": 0, "skipped": 0, "silent": False}

    date = run_entry.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    priority = _load_priority_issue()
    if not priority:
        result["silent"] = True
        logger.info("[briefing_email] silent-day: no priority issue surfaced in Box 3 (no briefing HTML, or unparseable)")
        return result

    commentary = _load_commentary(priority, date)
    silent, reason = _is_silent_day(commentary)
    if silent:
        result["silent"] = True
        logger.info("[briefing_email] silent-day for %r (%s): %s", priority, date, reason)
        return result

    quote_pool = _collect_quote_candidates(priority)
    all_candidates = [q for bucket in quote_pool.values() for q in bucket]
    quotes = _pick_verbatims(priority)
    if not quotes:
        result["silent"] = True
        logger.info("[briefing_email] silent-day: no qualifying verbatims for %r", priority)
        return result

    facts = _build_facts(commentary, quotes, run_entry,
                         all_candidate_quotes=all_candidates)

    # Opus call → verifier → optional retry → cache → send
    run_number = run_entry.get("run")
    cached = _load_cached_lede(run_number)
    if cached:
        logger.info("[briefing_email] reusing cached lede for run #%s", run_number)
        headline, lede = cached["headline"], cached["lede"]
    else:
        gen = _generate_lede(facts)
        if not gen:
            logger.warning("[briefing_email] opus generation failed — no email sent (principle 9: prefer silence to noise)")
            result["silent"] = True
            return result
        headline, lede = gen["headline"], gen["lede"]

        # Haiku verifier — first pass
        verify_first = _verify_lede(facts, headline, lede)
        logger.info("[briefing_email] verifier pass=%s violations=%d notes=%r",
                    verify_first["pass"], len(verify_first["violations"]), verify_first["notes"])

        verify_final = verify_first
        regenerated = False
        if not verify_first["pass"] and verify_first["violations"]:
            logger.info("[briefing_email] retrying with corrections: %s", verify_first["violations"])
            retry = _regenerate_with_corrections(facts, headline, lede, verify_first["violations"])
            if retry:
                headline, lede = retry["headline"], retry["lede"]
                regenerated = True
                verify_final = _verify_lede(facts, headline, lede)
                logger.info("[briefing_email] retry verifier pass=%s violations=%d",
                            verify_final["pass"], len(verify_final["violations"]))
                if not verify_final["pass"]:
                    logger.warning("[briefing_email] retry STILL failing verifier — sending anyway, violations: %s",
                                   verify_final["violations"])

        _cache_lede(run_number, headline, lede, gen["prompt_hash"],
                    verify_first=verify_first, verify_final=verify_final,
                    regenerated=regenerated)

    # SMTP
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587") or 587)
    user = os.getenv("SMTP_USER", "").strip()
    pwd  = os.getenv("SMTP_APP_PASSWORD", "").strip()
    from_addr = (os.getenv("SMTP_FROM") or user).strip()
    if not (host and user and pwd):
        logger.info("[briefing_email] SMTP creds missing — skipping distribution")
        return result

    recipients = _load_distribution()
    if not recipients:
        logger.info("[briefing_email] distribution list empty — skipping")
        return result

    # MIL-56 — compute audit fields once per send, pass per recipient.
    lede_hash  = _sha256_hex(lede)
    quote_sigs = _quote_sigs(quotes)

    for r in recipients:
        addr = (r.get("email") or "").strip()
        if not addr:
            result["skipped"] += 1
            continue
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = _SUBJECT_LINE
            msg["From"]    = from_addr
            msg["To"]      = addr
            msg.attach(MIMEText(_build_plaintext(r, headline, lede, date, quotes), "plain", "utf-8"))
            msg.attach(MIMEText(_build_html(r, headline, lede, quotes),             "html",  "utf-8"))
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls()
                server.login(user, pwd)
                server.sendmail(from_addr, [addr], msg.as_string())
            logger.info("[briefing_email] sent to %s", addr)
            _log_send(addr, _SUBJECT_LINE, "ok",
                      run=run_number, date=date, priority_issue=priority,
                      headline=headline, lede_sha256=lede_hash, quote_sigs=quote_sigs)
            result["sent"] += 1
        except Exception as exc:
            logger.warning("[briefing_email] send to %s failed: %s", addr, exc)
            _log_send(addr, _SUBJECT_LINE, "error", error=str(exc))
            result["failed"] += 1

    return result


# ── Manual test fire ──────────────────────────────────────────────────────────

def _latest_run_entry() -> dict | None:
    log = _MIL_ROOT / "data" / "daily_run_log.jsonl"
    if not log.exists():
        return None
    last = None
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last = json.loads(line)
        except json.JSONDecodeError:
            continue
    return last


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Fire the MIL-49 briefing email manually")
    parser.add_argument("--ignore-status", action="store_true",
                        help="Send even if the latest run status is not CLEAN.")
    parser.add_argument("--clear-cache", action="store_true",
                        help="Discard any cached Opus lede for the latest run and regenerate.")
    args = parser.parse_args()

    entry = _latest_run_entry()
    if not entry:
        logger.error("No entries in daily_run_log.jsonl — nothing to send.")
        raise SystemExit(1)

    if entry.get("status") != "CLEAN" and not args.ignore_status:
        logger.info("Latest run status=%s (not CLEAN) — skipping. Use --ignore-status to test fire.",
                    entry.get("status"))
        raise SystemExit(0)

    if args.clear_cache and _LEDE_CACHE.exists():
        run_n = entry.get("run")
        keep = []
        for line in _LEDE_CACHE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                if e.get("run") != run_n:
                    keep.append(line)
            except json.JSONDecodeError:
                pass
        _LEDE_CACHE.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
        logger.info("[briefing_email] cleared cached lede for run #%s", run_n)

    res = send_briefing_notification(entry)
    logger.info("briefing_email summary: %s", res)
