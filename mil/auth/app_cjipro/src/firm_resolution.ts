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

// Alpha-cohort hardcode. When a real entitlements/email-domain table
// lands in D1 (or as a build artefact from clients.yaml), swap to that.
// Keys are lowercase, no leading "@". Values are client_slugs from
// mil/config/clients.yaml.
const PARTNER_DOMAIN_TO_SLUG: Record<string, { slug: string; display: string }> = {
  "barclays.com":     { slug: "barclays", display: "Barclays" },
  "barclays.co.uk":   { slug: "barclays", display: "Barclays" },
};

// Default subject for admin-internal users. The only "subject" status
// client today (clients.yaml) is barclays — admin gets the same default
// briefing surface as the Barclays partner cohort, with an "Internal"
// badge to make role visible. When more subjects come online, this
// becomes a picker.
const ADMIN_DEFAULT_SUBJECT_SLUG = "barclays";
const ADMIN_FIRM_DISPLAY = "CJI";

export function resolveFirm(
  profile: PartnerProfile | null,
  email: string,
  isAdmin: boolean,
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
  //    unprovisioned partners).
  if (isAdmin) {
    return {
      slug: ADMIN_DEFAULT_SUBJECT_SLUG,
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
