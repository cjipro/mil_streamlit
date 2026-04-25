import { describe, expect, test } from "vitest";
import {
  addAutoApproveOrg,
  isAutoApproveOrg,
  removeAutoApproveOrg,
} from "../src/auto_approve";
import { FakeD1, asD1 } from "./fake_d1";

const NOW = new Date("2026-04-25T01:00:00.000Z");

describe("isAutoApproveOrg", () => {
  test("returns true for known org", async () => {
    const db = new FakeD1();
    await addAutoApproveOrg(asD1(db), "org_alpha", "hussain", null, NOW);
    expect(await isAutoApproveOrg(asD1(db), "org_alpha")).toBe(true);
  });

  test("returns false for unknown org", async () => {
    const db = new FakeD1();
    expect(await isAutoApproveOrg(asD1(db), "org_unknown")).toBe(false);
  });

  test("undefined / null / empty → false", async () => {
    const db = new FakeD1();
    await addAutoApproveOrg(asD1(db), "org_alpha", "hussain", null, NOW);
    expect(await isAutoApproveOrg(asD1(db), undefined)).toBe(false);
    expect(await isAutoApproveOrg(asD1(db), null)).toBe(false);
    expect(await isAutoApproveOrg(asD1(db), "")).toBe(false);
  });
});

describe("addAutoApproveOrg", () => {
  test("idempotent", async () => {
    const db = new FakeD1();
    await addAutoApproveOrg(asD1(db), "org_alpha", "hussain", "alpha cohort", NOW);
    await addAutoApproveOrg(asD1(db), "org_alpha", "hussain", "different note", NOW);
    expect(db.autoApproveOrgs).toHaveLength(1);
    expect(db.autoApproveOrgs[0].note).toBe("alpha cohort"); // first write wins
  });
});

describe("removeAutoApproveOrg", () => {
  test("removes existing row", async () => {
    const db = new FakeD1();
    await addAutoApproveOrg(asD1(db), "org_alpha", "hussain", null, NOW);
    const out = await removeAutoApproveOrg(asD1(db), "org_alpha");
    expect(out.kind).toBe("ok");
    expect(db.autoApproveOrgs).toHaveLength(0);
  });

  test("not-found when org wasn't there", async () => {
    const db = new FakeD1();
    const out = await removeAutoApproveOrg(asD1(db), "org_ghost");
    expect(out.kind).toBe("not-found");
  });
});
