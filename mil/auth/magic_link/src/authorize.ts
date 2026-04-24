// MIL-63 — build the WorkOS AuthKit authorize URL
//
// Flow initiation goes through WorkOS's User Management authorize
// endpoint, which issues an authorization_session_id and then 302s to
// whichever AuthKit domain is bound to the client in the dashboard
// (e.g. ideal-log-65-staging.authkit.app pre-cutover, login.cjipro.com
// after). The AuthKit domain's own /oauth2/authorize is a different,
// SSO-only endpoint that rejects User Management client_ids with
// `application_not_found` — do not point at it.
//
// Canonical pattern:
//   https://api.workos.com/user_management/authorize
//     ?response_type=code
//     &client_id=<client_id>
//     &redirect_uri=<callback>
//     &state=<signed-state>
//     &provider=authkit

const AUTHORIZE_BASE = "https://api.workos.com/user_management/authorize";

export type AuthorizeConfig = {
  clientId: string;
  redirectUri: string;
};

export function buildAuthorizeUrl(
  cfg: AuthorizeConfig,
  signedState: string,
): string {
  const params = new URLSearchParams({
    response_type: "code",
    client_id: cfg.clientId,
    redirect_uri: cfg.redirectUri,
    state: signedState,
    provider: "authkit",
  });
  return `${AUTHORIZE_BASE}?${params.toString()}`;
}
