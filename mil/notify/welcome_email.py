"""
Send a one-shot welcome email to an alpha partner after their email
has been added to the approved_users allowlist.

Usage:
    py -m mil.notify.welcome_email <email>
    py -m mil.notify.welcome_email --preview     # write rendered HTML to mil/data/welcome_preview.html
"""
from __future__ import annotations

import logging
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from mil.config import tenant_loader

logger = logging.getLogger(__name__)

SUBJECT = "Welcome to CJI Briefing"
FROM_ADDR = tenant_loader.organisation_contact_email()
FROM_NAME = tenant_loader.organisation_display_name()

CREAM = "#F5F2EC"
INK   = "#1a1a1a"
NAVY  = "#003A5C"
RULE  = "#1a1a1a"
MUTED = "#6b6b6b"


PLAIN_TEMPLATE = """━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

                    C J I   B R I E F I N G
        Customer Journey Intelligence
              Decisions, not dashboards.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Welcome edition · {dateline}


Welcome.

You have been invited to access the secure area of the
CJI platform.


─── HOW TO SIGN IN ───

  1.  Visit {apex_host}
      ─────────────────────────────────────────────────
  2.  Click "Partner sign-in" in the top-right corner
      ─────────────────────────────────────────────────
  3.  Enter your email — no password is required
      ─────────────────────────────────────────────────
  4.  We will email you a 6-digit code; enter it to
      complete sign-in.

You will be taken directly to your partner portal.


If you did not expect this invitation, please disregard
this message.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

      Anecdote → Aggregate → Awareness → Action

{org_name} · {apex_host} · {contact_email}
"""


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light only">
  <meta name="supported-color-schemes" content="light only">
  <title>Welcome to CJI Briefing</title>
</head>
<body style="margin:0;padding:0;background:{cream};font-family:'Source Serif 4',Georgia,'Times New Roman',serif;color:{ink};-webkit-font-smoothing:antialiased;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:{cream};padding:56px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="560" style="max-width:560px;width:100%;background:{cream};">

          <!-- Masthead: triple rule wordmark + tagline -->
          <tr>
            <td style="padding:0 8px;">
              <div style="border-top:2px solid {navy};border-bottom:1px solid {navy};padding:24px 0 18px;text-align:center;">
                <div style="font-family:'Source Serif 4',Georgia,'Times New Roman',serif;font-size:22px;font-weight:600;color:{navy};letter-spacing:0.36em;text-transform:uppercase;line-height:1;">CJI&nbsp;&nbsp;Briefing</div>
                <div style="font-family:'Source Serif 4',Georgia,serif;font-size:13px;color:{navy};letter-spacing:0.04em;margin-top:10px;line-height:1.4;">
                  Customer Journey Intelligence
                </div>
                <div style="font-family:'Source Serif 4',Georgia,serif;font-style:italic;font-size:13px;color:{muted};letter-spacing:0.02em;margin-top:2px;line-height:1.4;">
                  Decisions, not dashboards.
                </div>
              </div>
              <div style="border-bottom:1px solid {navy};height:3px;"></div>
            </td>
          </tr>

          <!-- Dateline -->
          <tr>
            <td style="padding:18px 8px 0;text-align:center;">
              <div style="font-family:'Source Serif 4',Georgia,serif;font-style:italic;font-size:13px;color:{muted};letter-spacing:0.04em;">Welcome edition · {dateline}</div>
            </td>
          </tr>

          <!-- Headline -->
          <tr>
            <td style="padding:48px 8px 8px;">
              <h1 style="margin:0;font-family:'Source Serif 4',Georgia,'Times New Roman',serif;font-size:38px;font-weight:600;color:{navy};letter-spacing:-0.012em;line-height:1.15;">Welcome.</h1>
            </td>
          </tr>

          <!-- Lede -->
          <tr>
            <td style="padding:18px 8px 32px;font-family:'Source Serif 4',Georgia,'Times New Roman',serif;font-size:17px;line-height:1.7;color:{ink};">
              <p style="margin:0;">You have been invited to access the secure area of the CJI platform.</p>
            </td>
          </tr>

          <!-- Section rule: small caps with hairlines -->
          <tr>
            <td style="padding:8px 8px 0;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                  <td style="border-bottom:1px solid {navy};line-height:1px;font-size:1px;width:32%;">&nbsp;</td>
                  <td style="padding:0 16px;font-family:Helvetica,Arial,sans-serif;font-size:11px;letter-spacing:0.24em;font-weight:700;color:{navy};text-transform:uppercase;text-align:center;white-space:nowrap;">How to sign in</td>
                  <td style="border-bottom:1px solid {navy};line-height:1px;font-size:1px;">&nbsp;</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Numbered steps with hairlines between -->
          <tr>
            <td style="padding:24px 8px 8px;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="font-family:'Source Serif 4',Georgia,'Times New Roman',serif;font-size:17px;line-height:1.55;color:{ink};">

                <tr><td style="padding:14px 0;">
                  <span style="display:inline-block;width:32px;font-family:'Source Serif 4',Georgia,serif;font-style:italic;color:{navy};font-size:18px;">1.</span>
                  Visit <a href="{apex_url}" style="color:{navy};text-decoration:underline;">{apex_host}</a>
                </td></tr>
                <tr><td style="border-top:1px solid #E6E1D8;line-height:1px;font-size:1px;">&nbsp;</td></tr>

                <tr><td style="padding:14px 0;">
                  <span style="display:inline-block;width:32px;font-family:'Source Serif 4',Georgia,serif;font-style:italic;color:{navy};font-size:18px;">2.</span>
                  Click <strong style="color:{navy};">Partner sign-in</strong> in the top-right corner
                </td></tr>
                <tr><td style="border-top:1px solid #E6E1D8;line-height:1px;font-size:1px;">&nbsp;</td></tr>

                <tr><td style="padding:14px 0;">
                  <span style="display:inline-block;width:32px;font-family:'Source Serif 4',Georgia,serif;font-style:italic;color:{navy};font-size:18px;">3.</span>
                  Enter your email &mdash; no password is required
                </td></tr>
                <tr><td style="border-top:1px solid #E6E1D8;line-height:1px;font-size:1px;">&nbsp;</td></tr>

                <tr><td style="padding:14px 0;">
                  <span style="display:inline-block;width:32px;font-family:'Source Serif 4',Georgia,serif;font-style:italic;color:{navy};font-size:18px;">4.</span>
                  We will email you a 6-digit code; enter it to complete sign-in.
                </td></tr>

              </table>
            </td>
          </tr>

          <!-- Closing -->
          <tr>
            <td style="padding:32px 8px 0;font-family:'Source Serif 4',Georgia,'Times New Roman',serif;font-size:16px;line-height:1.65;color:{ink};">
              <p style="margin:0 0 14px;">You will be taken directly to your partner portal.</p>
              <p style="margin:0;color:{muted};font-size:13px;font-style:italic;">If you did not expect this invitation, please disregard this message.</p>
            </td>
          </tr>

          <!-- Footer: chain-phrase + colophon -->
          <tr>
            <td style="padding:48px 8px 0;">
              <div style="border-top:1px solid {navy};height:1px;line-height:1px;font-size:1px;">&nbsp;</div>
            </td>
          </tr>
          <tr>
            <td style="padding:22px 8px 6px;text-align:center;">
              <div style="font-family:'Source Serif 4',Georgia,'Times New Roman',serif;font-style:italic;font-size:14px;color:{navy};letter-spacing:0.04em;line-height:1.5;">
                Anecdote &rarr; Aggregate &rarr; Awareness &rarr; Action
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:14px 8px 8px;text-align:center;font-family:Helvetica,Arial,sans-serif;font-size:11px;color:{muted};letter-spacing:0.08em;line-height:1.7;">
              <div style="color:{navy};font-weight:600;letter-spacing:0.32em;text-transform:uppercase;margin-bottom:6px;">{org_name}</div>
              <div><a href="{apex_url}" style="color:{muted};text-decoration:none;">{apex_host}</a> &middot; <a href="mailto:{contact_email}" style="color:{muted};text-decoration:none;">{contact_email}</a></div>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _dateline() -> str:
    return datetime.now(timezone.utc).strftime("%-d %B %Y") if sys.platform != "win32" \
        else datetime.now(timezone.utc).strftime("%#d %B %Y")


def _render() -> tuple[str, str]:
    dateline = _dateline()
    apex_host = tenant_loader.domain_apex()
    apex_url = tenant_loader.apex_url()
    contact_email = tenant_loader.organisation_contact_email()
    org_name = tenant_loader.organisation_name()
    plain = PLAIN_TEMPLATE.format(
        dateline=dateline,
        apex_host=apex_host,
        contact_email=contact_email,
        org_name=org_name,
    )
    html = HTML_TEMPLATE.format(
        dateline=dateline,
        cream=CREAM,
        ink=INK,
        navy=NAVY,
        muted=MUTED,
        apex_host=apex_host,
        apex_url=apex_url,
        contact_email=contact_email,
        org_name=org_name,
    )
    return plain, html


def send(email: str) -> bool:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587") or 587)
    user = os.getenv("SMTP_USER", "").strip()
    pwd  = os.getenv("SMTP_APP_PASSWORD", "").strip()

    if not (host and user and pwd):
        print("[welcome_email] SMTP creds missing in .env — aborting", file=sys.stderr)
        return False

    plain, html = _render()
    msg = MIMEMultipart("alternative")
    msg["Subject"]  = SUBJECT
    msg["From"]     = formataddr((FROM_NAME, FROM_ADDR))
    msg["Reply-To"] = FROM_ADDR
    msg["To"]       = email
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html,  "html",  "utf-8"))

    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()
        server.login(user, pwd)
        server.sendmail(FROM_ADDR, [email], msg.as_string())

    print(f"[welcome_email] sent to {email}")
    return True


def preview() -> Path:
    _, html = _render()
    out = Path(__file__).resolve().parents[1] / "data" / "welcome_preview.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"[welcome_email] preview written to {out}")
    return out


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--preview":
        preview()
        return
    if len(sys.argv) != 2:
        print("Usage:", file=sys.stderr)
        print("  py -m mil.notify.welcome_email <email>", file=sys.stderr)
        print("  py -m mil.notify.welcome_email --preview", file=sys.stderr)
        sys.exit(64)
    send(sys.argv[1].strip())


if __name__ == "__main__":
    main()
