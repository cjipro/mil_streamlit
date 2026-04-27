// MIL-147 — personal-email domain detection.
//
// A pure function used by /request-access intake + admin dashboard to
// flag personal-email submissions for extra-scrutiny manual triage.
// Personal-email submissions are NOT auto-rejected (Hussain Q3) — they
// just render with an amber badge so the approver knows to look harder
// at the "why" field before approving.
//
// Keep the list short and high-signal. Catch-all domains add noise; the
// goal is to flag the obvious 90% (gmail/yahoo/outlook), not catch every
// possible personal address. A partner forwarding to a corp email after
// approval is fine — admin sees the flag at intake time, accepts the
// partner anyway, partner uses corp email going forward.

const PERSONAL_DOMAINS = new Set<string>([
  "gmail.com",
  "googlemail.com",
  "yahoo.com",
  "yahoo.co.uk",
  "outlook.com",
  "hotmail.com",
  "hotmail.co.uk",
  "live.com",
  "live.co.uk",
  "icloud.com",
  "me.com",
  "mac.com",
  "proton.me",
  "protonmail.com",
  "aol.com",
  "msn.com",
  "ymail.com",
  "rocketmail.com",
  "btinternet.com",
  "sky.com",
  "virginmedia.com",
  "talktalk.net",
  "ntlworld.com",
  "tutanota.com",
  "gmx.com",
  "gmx.net",
  "fastmail.com",
  "zoho.com",
  "mail.com",
]);

export function isPersonalEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  const at = email.lastIndexOf("@");
  if (at < 0 || at === email.length - 1) return false;
  const domain = email.slice(at + 1).toLowerCase().trim();
  return PERSONAL_DOMAINS.has(domain);
}

// Exported for tests + future admin tooling that wants to display the
// canonical list (e.g. an admin docs page).
export function personalDomains(): readonly string[] {
  return Array.from(PERSONAL_DOMAINS).sort();
}
