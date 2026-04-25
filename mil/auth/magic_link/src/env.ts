// MIL-63 — Worker env binding types.
//
// Non-secret values live in `[vars]` of wrangler.toml. Secrets are
// set via `wrangler secret put <NAME>` and never committed.

export interface Env {
  // Vars
  AUTHKIT_HOST: string;
  CLIENT_ID: string;
  REDIRECT_URI: string;
  DEFAULT_RETURN_TO: string;
  COOKIE_NAME: string;
  COOKIE_DOMAIN: string;
  COOKIE_MAX_AGE_SECONDS: string;
  RETURN_TO_PARAM: string;

  // Secrets
  WORKOS_CLIENT_SECRET: string;
  STATE_SIGNING_KEY: string;

  // MIL-65 — audit log binding. Optional; absent binding degrades to
  // console.log only. Activation procedure documented in wrangler.toml.
  AUDIT_DB?: D1Database;

  // MIL-66b — admin routes require JWT verification against the same
  // WorkOS JWKS the edge-bouncer uses. Values must match
  // edge_bouncer/wrangler.toml so the same cookie validates on both.
  JWKS_URL?: string;
  EXPECTED_AUD?: string;
  EXPECTED_ISS?: string;
  JWKS_CACHE_TTL_SECONDS?: string;

  // MIL-67a — WorkOS webhook signing secret. Optional; when absent
  // the /webhooks/workos endpoint returns 503. Set via
  //   wrangler secret put WORKOS_WEBHOOK_SECRET
  // after creating the webhook in the WorkOS dashboard.
  WORKOS_WEBHOOK_SECRET?: string;
}
