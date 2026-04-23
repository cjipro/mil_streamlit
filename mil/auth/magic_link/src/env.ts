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
}
