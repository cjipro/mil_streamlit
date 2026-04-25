// MIL-92 — Reckoner page render tests.

import { describe, expect, test } from "vitest";
import {
  renderReckonerHtml,
  mvpSnapshot,
  type ReckonerSnapshot,
} from "../src/reckoner";

describe("renderReckonerHtml", () => {
  test("emits all three sections", () => {
    const html = renderReckonerHtml(mvpSnapshot());
    expect(html).toContain("Section 01");
    expect(html).toContain("Industry Pulse");
    expect(html).toContain("Section 02");
    expect(html).toContain("Anomalies");
    expect(html).toContain("Section 03");
    expect(html).toContain("Decisions Surfaced");
  });

  test("renders the cohort label + run number + corpus size in topbar", () => {
    const html = renderReckonerHtml(mvpSnapshot());
    expect(html).toContain("UK retail banking");
    expect(html).toContain("Run #59");
    expect(html).toContain("7,418");
  });

  test("escapes pattern names (no HTML injection)", () => {
    const malicious: ReckonerSnapshot = {
      ...mvpSnapshot(),
      industry_pulse: [
        {
          pattern: "<script>alert(1)</script>",
          cohort_share: 0.5,
          severity: "P0",
          trend: "WORSENING",
        },
      ],
    };
    const html = renderReckonerHtml(malicious);
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
  });

  test("renders P0/P1/P2 severity badges with the right CSS class", () => {
    const html = renderReckonerHtml(mvpSnapshot());
    expect(html).toMatch(/class="badge p0"/);
    expect(html).toMatch(/class="badge p1"/);
    expect(html).toMatch(/class="badge p2"/);
  });

  test("renders Clark tier badges with the right tier class", () => {
    const html = renderReckonerHtml(mvpSnapshot());
    // mvpSnapshot has CLARK-2 + CLARK-3 in decisions
    expect(html).toMatch(/class="clark t2"/);
    expect(html).toMatch(/class="clark t3"/);
  });

  test("anomalies show signed delta values", () => {
    const html = renderReckonerHtml(mvpSnapshot());
    expect(html).toContain("+11.4 pp");
    expect(html).toContain("CHR-007");
  });

  test("alpha-preview banner only renders when flag is set", () => {
    const withBanner = renderReckonerHtml({
      ...mvpSnapshot(),
      is_alpha_preview: true,
    });
    expect(withBanner).toContain("Alpha preview");

    const withoutBanner = renderReckonerHtml({
      ...mvpSnapshot(),
      is_alpha_preview: false,
    });
    expect(withoutBanner).not.toContain("Alpha preview");
  });

  test("empty industry_pulse renders the no-patterns lede", () => {
    const empty = renderReckonerHtml({
      ...mvpSnapshot(),
      industry_pulse: [],
    });
    expect(empty).toContain("No patterns surfaced");
  });

  test("empty anomalies renders a calm cohort-tracking message", () => {
    const empty = renderReckonerHtml({ ...mvpSnapshot(), anomalies: [] });
    expect(empty).toContain("No anomalies surfaced");
  });

  test("empty decisions renders a quiet-cohort message", () => {
    const empty = renderReckonerHtml({ ...mvpSnapshot(), decisions: [] });
    expect(empty).toContain("No patterns escalated");
  });

  test("disabled tabs render with aria-disabled", () => {
    const html = renderReckonerHtml(mvpSnapshot());
    expect(html).toMatch(/aria-disabled="true"[^>]*>Conversational/);
    expect(html).toMatch(/aria-disabled="true"[^>]*>Drag-drop/);
  });

  test("footer cross-links to public marketing surfaces", () => {
    const html = renderReckonerHtml(mvpSnapshot());
    expect(html).toContain("https://cjipro.com/insights/methodology/");
    expect(html).toContain("https://cjipro.com/security/");
    expect(html).toContain("https://cjipro.com/privacy/");
    expect(html).toContain("mailto:hello@cjipro.com");
  });
});

describe("mvpSnapshot", () => {
  test("returns a typed snapshot with the expected shape", () => {
    const snap = mvpSnapshot();
    expect(snap.industry_pulse.length).toBeGreaterThan(0);
    expect(snap.anomalies.length).toBeGreaterThan(0);
    expect(snap.decisions.length).toBeGreaterThan(0);
    expect(snap.is_alpha_preview).toBe(true);
    expect(snap.cohort_label).toMatch(/UK retail banking/);
  });

  test("generated_at is a valid ISO-8601 timestamp", () => {
    const snap = mvpSnapshot();
    expect(() => new Date(snap.generated_at).toISOString()).not.toThrow();
  });
});
