import { describe, expect, test } from "vitest";
import { buildAuthorizeUrl } from "../src/authorize";

describe("buildAuthorizeUrl", () => {
  const cfg = {
    clientId: "client_01KPY7CA07ZD1WG3DMQE1FZQE1",
    redirectUri: "https://login.cjipro.com/callback",
  };

  test("includes required OAuth params against WorkOS User Management endpoint", () => {
    const url = new URL(buildAuthorizeUrl(cfg, "signed-state"));
    expect(url.origin).toBe("https://api.workos.com");
    expect(url.pathname).toBe("/user_management/authorize");
    expect(url.searchParams.get("response_type")).toBe("code");
    expect(url.searchParams.get("client_id")).toBe(cfg.clientId);
    expect(url.searchParams.get("redirect_uri")).toBe(cfg.redirectUri);
    expect(url.searchParams.get("state")).toBe("signed-state");
    expect(url.searchParams.get("provider")).toBe("authkit");
  });

  test("url-encodes redirect_uri and state", () => {
    const url = buildAuthorizeUrl(cfg, "a/b+c=d");
    // URLSearchParams handles encoding — just check it round-trips
    // via a parser rather than asserting specific % sequences.
    const parsed = new URL(url);
    expect(parsed.searchParams.get("state")).toBe("a/b+c=d");
  });
});
