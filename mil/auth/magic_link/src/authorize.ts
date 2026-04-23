// MIL-63 — build the WorkOS AuthKit authorize URL
//
// AuthKit authorize endpoint pattern:
//   https://<authkit-host>/oauth2/authorize
//     ?response_type=code
//     &client_id=<client_id>
//     &redirect_uri=<callback>
//     &state=<signed-state>
//     &provider=authkit
//
// <authkit-host> is either:
//   - the default AuthKit domain (ideal-log-65-staging.authkit.app) before cutover, or
//   - login.cjipro.com after cutover.
// Both paths work with the same query params; the only difference is
// what the user sees in the URL bar. Panel rule: only *.cjipro.com
// in production — but pre-cutover staging is fine for dev.

export type AuthorizeConfig = {
  authkitHost: string;
  clientId: string;
  redirectUri: string;
};

export function buildAuthorizeUrl(
  cfg: AuthorizeConfig,
  signedState: string,
): string {
  const base = `https://${cfg.authkitHost}/oauth2/authorize`;
  const params = new URLSearchParams({
    response_type: "code",
    client_id: cfg.clientId,
    redirect_uri: cfg.redirectUri,
    state: signedState,
    provider: "authkit",
  });
  return `${base}?${params.toString()}`;
}
