// MIL-144 — firm resolution for the /portal welcome surface.
//
// partner_profiles.firm_slug is admin-set only (threat model: self-set
// would let a user spoof firm context). But for display alone, we can
// infer a friendly firm context from email domain or admin status.
//
// Resolution order (first match wins):
//   1. admin-set       — partner_profiles.firm_slug + firm_name populated
//   2. admin-internal  — caller is in admin_users (CJI team member)
//   3. domain-inferred — email domain matches a known partner domain
//   4. unprovisioned   — neither — show "Setting up your account"
//
// IMPORTANT: this is a DISPLAY hint, not an access-control decision.
// Briefing access at /sonar/{slug}/ remains gated by approved_users +
// the future workos_org_id check (MIL-86 soft-launch admits any approved
// user to any subject's briefing). Renaming this is fine — what matters
// is that no caller treats `kind === "domain-inferred"` as authorisation.

import type { PartnerProfile } from "../../approvals/src/partner_profiles";
import { PARTNER_DOMAIN_TO_SLUG } from "./partner_domains.generated";
import { SUBJECTS } from "./subjects.generated";

export type FirmResolutionKind =
  | "admin-set"
  | "admin-internal"
  | "domain-inferred"
  | "unprovisioned";

export interface ResolvedFirm {
  slug: string | null;          // routing slug for /sonar/{slug}/. null when unprovisioned.
  display_name: string;         // "Barclays" / "CJI" / "Setting up your account"
  kind: FirmResolutionKind;
  is_internal: boolean;         // true for admin-internal — drives the "Internal" badge
  has_briefing: boolean;        // can we show a working briefing hero? false for unprovisioned
}

// PARTNER_DOMAIN_TO_SLUG is auto-generated at deploy time from
// mil/config/clients.yaml (MIL-155). To add or change a partner's email
// domains, edit clients.yaml — the npm predeploy hook regenerates the
// TS artefact before upload. Keys are lowercase, no leading "@".

// MIL-156 — default subject for admin-internal users is the FIRST
// `status: subject` entry in clients.yaml (today: barclays). With one
// subject, this is the only thing rendered. With >= 2 subjects + a
// valid `__Host-cji_admin_subject` cookie, the cookie value overrides.
// Falls back to first-subject if SUBJECTS is somehow empty (defensive —
// the loader rejects an empty subjects list at load time, but Workers
// shouldn't crash on a misgenerated artefact).
const ADMIN_DEFAULT_SUBJECT_SLUG: string = SUBJECTS[0]?.slug ?? "barclays";
const ADMIN_FIRM_DISPLAY = "CJI";

/**
 * MIL-156 — given the admin's selected-subject cookie value (or null /
 * undefined), return the slug + display the admin-internal portal should
 * route to. Cookie wins ONLY if it matches a current SUBJECTS entry —
 * stale or tampered cookies fall back to the default. Returns the picker
 * source-of-truth tuple so portal.ts can also light up the right radio.
 */
export function resolveAdminSubject(
  cookieValue: string | null | undefined,
): { slug: string; display: string } {
  if (cookieValue) {
    const hit = SUBJECTS.find((s) => s.slug === cookieValue);
    if (hit) return { slug: hit.slug, display: hit.display };
  }
  // First subject in YAML order is the default. SUBJECTS is non-empty in
  // production; the ?? guard is defensive against a misgenerated artefact.
  const first = SUBJECTS[0];
  return first
    ? { slug: first.slug, display: first.display }
    : { slug: ADMIN_DEFAULT_SUBJECT_SLUG, display: "Barclays" };
}

export function resolveFirm(
  profile: PartnerProfile | null,
  email: string,
  isAdmin: boolean,
  // MIL-156 — admin-side subject cookie (`__Host-cji_admin_subject`).
  // Only consulted on the admin-internal branch. Default falls back to
  // SUBJECTS[0] — barclays today — when cookie is absent or invalid.
  adminSubjectCookie: string | null = null,
): ResolvedFirm {
  // 1. Admin-set firm always wins (most specific).
  if (profile?.firm_slug && profile?.firm_name) {
    return {
      slug: profile.firm_slug,
      display_name: profile.firm_name,
      kind: "admin-set",
      is_internal: false,
      has_briefing: true,
    };
  }

  // 2. Admin / CJI-internal user. Display "CJI" but route briefing-hero
  //    Open button to the default subject so the surface is still
  //    functional (otherwise admins land on the same dead surface as
  //    unprovisioned partners). MIL-156 — cookie value picks among
  //    multiple subjects when they exist; falls back to first.
  if (isAdmin) {
    const picked = resolveAdminSubject(adminSubjectCookie);
    return {
      slug: picked.slug,
      display_name: ADMIN_FIRM_DISPLAY,
      kind: "admin-internal",
      is_internal: true,
      has_briefing: true,
    };
  }

  // 3. Email-domain inference for known partner domains.
  const domain = emailDomain(email);
  if (domain && PARTNER_DOMAIN_TO_SLUG[domain]) {
    const hit = PARTNER_DOMAIN_TO_SLUG[domain];
    return {
      slug: hit.slug,
      display_name: hit.display,
      kind: "domain-inferred",
      is_internal: false,
      has_briefing: true,
    };
  }

  // 4. No signal — admin must run partner_set_firm before this user
  //    sees a useful briefing hero.
  return {
    slug: null,
    display_name: "Setting up your account",
    kind: "unprovisioned",
    is_internal: false,
    has_briefing: false,
  };
}

function emailDomain(email: string): string | null {
  const at = email.lastIndexOf("@");
  if (at < 0 || at === email.length - 1) return null;
  return email.slice(at + 1).toLowerCase().trim();
}
