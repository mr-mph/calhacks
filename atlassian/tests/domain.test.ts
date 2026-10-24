import { describe, expect, it } from "vitest";
import { parseAlert } from "../src/domain/alert";
import { buildReport, renderStorage } from "../src/domain/report";
import { isOnShift, validateRoster } from "../src/domain/roster";
import { header, secretMatches } from "../src/domain/secret";

const body = (o: Record<string, unknown> = {}) =>
  JSON.stringify({
    alert_id: "s1-001", text: "Rip forming", uncertainty: "fog", zone: "North Stairs",
    counts: { person_water: 1, person_beach: 4 }, confidence: 0.7, frame_url: "https://x.test/f.jpg", t: 1792872000, ...o,
  });

describe("parseAlert", () => {
  it("normalises a station alert", () => {
    const r = parseAlert(body());
    expect(r.ok && r.alert).toMatchObject({ zone: "north-stairs", personWater: 1, observedAt: 1792872000000 });
  });

  it.each([
    [{ confidence: 1.5 }, /confidence/],
    [{ counts: { person_water: -1 } }, /person_water/],
    [{ alert_id: "a b" }, /alert_id/],
    [{ zone: "!!!" }, /zone/],
    [{ text: "" }, /text/],
    [{ t: "yesterday" }, /t must be/],
  ])("rejects %j", (o, msg) => {
    const r = parseAlert(body(o));
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(msg);
  });

  it("treats a non-http frame link as missing", () => {
    const r = parseAlert(body({ frame_url: "javascript:alert(1)" }));
    expect(r.ok && r.alert.frameUrl).toBeNull();
  });

  it("rejects non-JSON", () => {
    expect(parseAlert("nope")).toEqual({ ok: false, error: "body must be JSON" });
  });
});

describe("shared secret", () => {
  const secret = "a".repeat(64);
  it("accepts only the exact secret", () => {
    expect(secretMatches(secret, secret)).toBe(true);
    expect(secretMatches(secret.slice(1), secret)).toBe(false);
    expect(secretMatches(undefined, secret)).toBe(false);
  });
  it("fails closed when the app secret is unset or weak", () => {
    expect(secretMatches("", undefined)).toBe(false);
    expect(secretMatches("short", "short")).toBe(false);
  });
  it("reads headers case-insensitively", () => {
    expect(header({ "X-Balloon-Secret": ["v"] }, "x-balloon-secret")).toBe("v");
  });
});

describe("roster", () => {
  it("handles shifts that cross midnight", () => {
    const night = { name: "N", accountId: "a", start: "22:00", end: "06:00" };
    expect(isOnShift(night, 23 * 60)).toBe(true);
    expect(isOnShift(night, 5 * 60)).toBe(true);
    expect(isOnShift(night, 12 * 60)).toBe(false);
  });
  it("rejects bad rows with a fix", () => {
    expect(() => validateRoster([{ name: "A", accountId: "x", start: "8am", end: "16:00" }])).toThrow(/HH:MM/);
    expect(() => validateRoster([{ name: "", accountId: "x", start: "08:00", end: "16:00" }])).toThrow(/name/);
  });
});

describe("shift report", () => {
  it("escapes issue text in the Confluence page", () => {
    const issue = {
      key: "BPAT-1", summary: "<script>alert(1)</script>", status: "To Do", isDone: false,
      assigneeAccountId: null, assigneeName: null, priority: "High", created: 0, resolved: null,
    };
    const html = renderStorage(buildReport(new Date(), [], new Map(), [issue], []));
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });
});
