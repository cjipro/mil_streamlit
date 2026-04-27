// MIL-160 — engineering page render + route tests.
//
// Tests the renderEngineering() output for the load-bearing invariants
// (opener line, three buckets, drill-down convention, callout footer)
// plus the router dispatch for /engineering and /engineering/.

import { describe, expect, test } from "vitest";
import { renderEngineering } from "../src/engineering";
import { dispatch } from "../src/router";

function req(path: string): Request {
  return new Request(`https://app.cjipro.com${path}`);
}

describe("renderEngineering", () => {
  const html = renderEngineering();

  test("emits a complete HTML document", () => {
    expect(html.startsWith("<!DOCTYPE html>")).toBe(true);
    expect(html).toContain("<html lang=\"en-GB\">");
    expect(html).toContain("</html>");
  });

  test("noindex,nofollow — auth-gated page should not be crawled", () => {
    expect(html).toMatch(/<meta name="robots" content="noindex,nofollow">/);
  });

  test("page title includes 'Engineering posture · CJI'", () => {
    expect(html).toContain("<title>Engineering posture · CJI</title>");
  });

  test("opener line is the locked panel decision (verbatim)", () => {
    expect(html).toContain(
      "This system prefers honest ignorance to unverified certainty — every claim ships with an evidence id, every gap ships with a ticket number.",
    );
  });

  test("renders all three buckets — Addressed / Planned / Considered", () => {
    expect(html).toContain("Addressed — in production today");
    expect(html).toContain("Planned — committed work, ticket-tracked");
    expect(html).toContain("Considered — post-MVP, signal-driven, not committed");
  });

  test("renders the four discipline sections under Addressed", () => {
    expect(html).toContain("§AI · Synthesis, never source-of-truth");
    expect(html).toContain("§Data · Manifest is source of truth");
    expect(html).toContain("§Security · Immutable from day one");
    expect(html).toContain("§Software · Abstractions minimal");
  });

  test("section voice rule applied — confessional in AI/Data, clinical in Security/Software", () => {
    // Voice classes are emitted on each <section> so visual styling can
    // diverge if needed later. The class itself is the structural marker
    // that the rule is in effect, not the prose.
    expect(html).toMatch(/<section class="addressed-section voice-confessional">/);
    expect(html).toMatch(/<section class="addressed-section voice-clinical">/);
  });

  test("every Addressed bullet carries both [code] and [why] anchors", () => {
    // Pull the Addressed block and count bullets vs. anchor pairs.
    // This guards the drill-down convention — if someone adds a bullet
    // without a code path, the count diverges and the test fails.
    const addressedBlock = extractBlock(
      html,
      'Addressed — in production today',
      'Planned — committed work',
    );
    const bullets = (addressedBlock.match(/<li>/g) ?? []).length;
    const codeAnchors = (addressedBlock.match(/\[code:/g) ?? []).length;
    const whyAnchors = (addressedBlock.match(/\[why:/g) ?? []).length;
    expect(bullets).toBeGreaterThan(20); // ~28 bullets across 4 sections
    expect(codeAnchors).toBe(bullets);
    expect(whyAnchors).toBe(bullets);
  });

  test("Planned bullets reference real Jira tickets (rendered as Jira links)", () => {
    const plannedBlock = extractBlock(
      html,
      'Planned — committed work',
      'Considered — post-MVP',
    );
    expect(plannedBlock).toContain("https://cjipro.atlassian.net/browse/MIL-125");
    expect(plannedBlock).toContain("https://cjipro.atlassian.net/browse/MIL-73");
    expect(plannedBlock).toContain("https://cjipro.atlassian.net/browse/MIL-74");
    expect(plannedBlock).toContain("https://cjipro.atlassian.net/browse/PULSE-11");
  });

  test("Considered section names what would unblock each item", () => {
    const consideredBlock = extractBlock(
      html,
      'Considered — post-MVP',
      'One non-obvious claim',
    );
    expect(consideredBlock).toContain("SOC 2 Type 1");
    expect(consideredBlock).toContain("Unblock:");
    // SOC 2 phrasing follows AICPA-verifiability rule (MIL-135 polish):
    // "readiness", never "in progress" / "in audit".
    expect(consideredBlock).toContain("readiness assessment underway");
    expect(consideredBlock).not.toContain("SOC 2 audit in progress");
  });

  test("footer renders four 'Did You Know' callouts, one per discipline", () => {
    const calloutsBlock = extractBlock(
      html,
      "One non-obvious claim per discipline",
      "Source: panel synthesis",
    );
    const eyebrows = (calloutsBlock.match(/class="callout-eyebrow"/g) ?? []).length;
    expect(eyebrows).toBe(4);
    expect(calloutsBlock).toContain("§AI");
    expect(calloutsBlock).toContain("§Data");
    expect(calloutsBlock).toContain("§Security");
    expect(calloutsBlock).toContain("§Software");
  });

  test("no inline JS — CSP-clean", () => {
    // The page must not ship script tags or on* event handlers; the auth
    // gate's CSP posture and the design memo both call this out.
    expect(html).not.toMatch(/<script\b/i);
    expect(html).not.toMatch(/\son[a-z]+\s*=/i);
    expect(html).not.toMatch(/javascript:/i);
  });

  test("links to GitHub blob origin for code anchors (not tree)", () => {
    expect(html).toContain("https://github.com/cjipro/mil_streamlit/blob/main/mil/SOVEREIGN_BRIEF.md");
    expect(html).toContain("https://github.com/cjipro/mil_streamlit/blob/main/mil/config/model_routing.yaml");
  });

  test("brand link in topbar resolves to /portal (gives partners a way back)", () => {
    expect(html).toMatch(/<a class="brand" href="\/portal"/);
  });

  // ── At-a-glance table (panel-driven addition) ─────────────────────

  test("renders the at-a-glance table with all four disciplines", () => {
    expect(html).toContain('<table class="ag-table">');
    expect(html).toContain("<th scope=\"col\">Discipline</th>");
    expect(html).toContain("<th scope=\"col\">Strengths</th>");
    expect(html).toContain("<th scope=\"col\">Pipeline</th>");
    expect(html).toContain("<th scope=\"col\">Ideal world</th>");
    // Each discipline appears as a <th scope="row"> in the body
    expect(html).toMatch(/<th scope="row">AI<\/th>/);
    expect(html).toMatch(/<th scope="row">Software<\/th>/);
    expect(html).toMatch(/<th scope="row">Data<\/th>/);
    expect(html).toMatch(/<th scope="row">Security<\/th>/);
  });

  test("table sits above the Addressed bucket so it's the first scan", () => {
    const tableIdx = html.indexOf('<table class="ag-table">');
    const addressedIdx = html.indexOf("Addressed — in production today");
    expect(tableIdx).toBeGreaterThan(0);
    expect(addressedIdx).toBeGreaterThan(tableIdx);
  });

  test("legend explains the three columns and disambiguates 'Ideal world'", () => {
    expect(html).toContain('<p class="ag-legend">');
    expect(html).toContain("How to read this");
    expect(html).toContain("Strengths");
    expect(html).toContain("Pipeline");
    expect(html).toContain("Ideal world");
    // Critical for AICPA-verifiability — the legend must say Ideal world
    // is NOT a current attestation, so the SOC 2 / pen-test cells can't
    // be misread.
    expect(html).toContain("Not");
    expect(html).toMatch(/current attestation/i);
  });

  test("Ideal-world cells do not claim anything as already held", () => {
    // Anti-overclaim guard. None of the Ideal-world cells should use
    // present-tense verbs that imply the control already exists.
    const tbody = extractBlock(html, "<tbody>", "</tbody>");
    // "We hold SOC 2" / "SOC 2 attested" / "audit complete" must not appear
    expect(tbody).not.toMatch(/SOC 2 (attested|certified|in audit|complete)/i);
    expect(tbody).not.toMatch(/pen-?test\s+(complete|passed)/i);
  });

  test("Pipeline cells reference real Jira tickets so they're falsifiable", () => {
    const tbody = extractBlock(html, "<tbody>", "</tbody>");
    expect(tbody).toContain("MIL-126");
    expect(tbody).toContain("MIL-125");
    expect(tbody).toContain("MIL-74");
    expect(tbody).toContain("PULSE-11");
  });

  test("table cells carry data-label attrs so the mobile-stacked layout has labels", () => {
    expect(html).toContain('data-label="Strengths"');
    expect(html).toContain('data-label="Pipeline"');
    expect(html).toContain('data-label="Ideal world"');
  });

  test("sign-out link points at login.cjipro.com/logout", () => {
    expect(html).toContain('href="https://login.cjipro.com/logout"');
  });
});

describe("dispatch — /engineering route", () => {
  test("/engineering returns 200 HTML", async () => {
    const res = await dispatch(req("/engineering"));
    expect(res).not.toBeNull();
    expect(res!.status).toBe(200);
    expect(res!.headers.get("content-type")).toContain("text/html");
  });

  test("/engineering/ (trailing slash) routes the same", async () => {
    const res = await dispatch(req("/engineering/"));
    expect(res!.status).toBe(200);
    const body = await res!.text();
    expect(body).toContain("Engineering posture");
  });

  test("/engineering body contains the opener line", async () => {
    const res = await dispatch(req("/engineering"));
    const body = await res!.text();
    expect(body).toContain(
      "This system prefers honest ignorance to unverified certainty",
    );
  });

  test("/engineering carries cache-control: no-store (auth-gated, do not cache)", async () => {
    const res = await dispatch(req("/engineering"));
    expect(res!.headers.get("cache-control")).toBe("no-store");
  });
});

// ── Helpers ────────────────────────────────────────────────────────

// Pull the substring between two anchor strings — useful for asserting
// that a particular block contains/lacks something without re-rendering
// or re-parsing the whole document.
function extractBlock(html: string, from: string, to: string): string {
  const start = html.indexOf(from);
  const end = html.indexOf(to);
  if (start < 0 || end < 0 || end < start) {
    throw new Error(`extractBlock: anchors not found (from="${from}", to="${to}")`);
  }
  return html.slice(start, end);
}
