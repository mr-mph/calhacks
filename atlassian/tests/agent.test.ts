import { describe, expect, it } from "vitest";
import { handleAlert } from "../src/agent";
import { dismissQueued, promoteQueued, revertAction } from "../src/humanActions";
import { alert, deps } from "./fakes";

const at = (iso: string) => () => new Date(iso);

describe("handleAlert", () => {
  it("creates a Highest incident assigned to whoever is on shift", async () => {
    const { d, j, store } = deps();
    const out = await handleAlert(d, alert());
    expect(out).toMatchObject({ outcome: "created", issueKey: "BPAT-1", flags: [], missing: [] });
    expect(j.issues.get("BPAT-1")).toMatchObject({ priority: "Highest", assigneeAccountId: "acc-maya" });
    expect(j.issues.get("BPAT-1")?.labels).toEqual(["balloon-patrol", "rip-current", "zone-north-stairs", "people-in-water"]);
    expect(store.audit.map((e) => e.action).reverse()).toEqual(["create", "assign"]);
  });

  it("leaves the incident unassigned and says why when no one is on shift", async () => {
    const { d, j, store } = deps([{ name: "Sam", accountId: "acc-sam", start: "06:00", end: "07:00" }]);
    const out = await handleAlert(d, alert());
    expect(j.calls.some((c) => c.op === "assign")).toBe(false);
    expect(out.reason).toMatch(/no one on the roster is on shift/);
    expect(store.audit.find((e) => e.action === "create")).toBeDefined();
  });

  it("comments instead of creating a duplicate within 10 minutes", async () => {
    const { d, j } = deps();
    await handleAlert(d, alert({ alertId: "a1", personWater: 0 }));
    const out = await handleAlert({ ...d, now: at("2026-10-24T20:08:00Z") }, alert({ alertId: "a2", personWater: 0 }));
    expect(out.outcome).toBe("updated");
    expect(out.issueKey).toBe("BPAT-1");
    expect(j.calls.filter((c) => c.op === "create")).toHaveLength(1);
  });

  it("escalates the open incident when people enter the water", async () => {
    const { d, j, store } = deps();
    await handleAlert(d, alert({ alertId: "a1", personWater: 0, personBeach: 3 }));
    await handleAlert(d, alert({ alertId: "a2", personWater: 1 }));
    expect(j.issues.get("BPAT-1")?.priority).toBe("Highest");
    expect(store.audit[0]?.action).toBe("escalate");
    expect(store.audit[0]?.revert).toEqual({ type: "restore-priority", from: "High", to: "Highest" });
  });

  it("opens a new incident once the zone has been quiet for 10 minutes", async () => {
    const { d } = deps();
    await handleAlert(d, alert({ alertId: "a1" }));
    const out = await handleAlert({ ...d, now: at("2026-10-24T20:11:00Z") }, alert({ alertId: "a2" }));
    expect(out).toMatchObject({ outcome: "created", issueKey: "BPAT-2" });
  });

  it("opens a new incident if the earlier one is done", async () => {
    const { d, j } = deps();
    await handleAlert(d, alert({ alertId: "a1" }));
    j.issues.set("BPAT-1", { ...j.issues.get("BPAT-1")!, isDone: true });
    const out = await handleAlert(d, alert({ alertId: "a2" }));
    expect(out.issueKey).toBe("BPAT-2");
  });

  it("queues low-confidence alerts without touching Jira", async () => {
    const { d, j, store } = deps();
    const out = await handleAlert(d, alert({ confidence: 0.31 }));
    expect(out.outcome).toBe("queued");
    expect(out.reason).toMatch(/0\.31 is below 0\.5/);
    expect(j.calls).toEqual([]);
    expect(store.queue).toHaveLength(1);
  });

  it("asks the station for a missing frame, then records it when re-sent", async () => {
    const { d, j, store } = deps();
    const first = await handleAlert(d, alert({ frameUrl: null }));
    expect(first.missing).toEqual(["frame_url"]);
    expect(store.audit[0]?.action).toBe("request-detail");
    const again = await handleAlert(d, alert());
    expect(again.outcome).toBe("repeat");
    expect(again.reason).toMatch(/Added the missing frame/);
    expect(j.calls.filter((c) => c.op === "comment")).toHaveLength(2);
  });

  it("ignores an alert it has already handled", async () => {
    const { d, j } = deps();
    await handleAlert(d, alert());
    const before = j.calls.length;
    expect((await handleAlert(d, alert())).outcome).toBe("repeat");
    expect(j.calls.length).toBe(before);
  });
});

describe("human actions", () => {
  it("reverts the agent's assignment, comment and escalation", async () => {
    const { d, j, store } = deps();
    await handleAlert(d, alert({ alertId: "a1", personWater: 0 }));
    await handleAlert(d, alert({ alertId: "a2", personWater: 3 }));
    const ids = (action: string) => store.audit.filter((e) => e.action === action).map((e) => e.id);

    await revertAction(d, ids("assign")[0]!, "acc-admin");
    await revertAction(d, ids("comment")[0]!, "acc-admin");
    await revertAction(d, ids("escalate")[0]!, "acc-admin");

    expect(j.issues.get("BPAT-1")).toMatchObject({ assigneeAccountId: null, priority: "High" });
    expect(j.calls.some((c) => c.op === "delete-comment")).toBe(true);
    expect(store.audit.filter((e) => e.action === "revert")).toHaveLength(3);
    await expect(revertAction(d, ids("assign")[0]!, "acc-admin")).rejects.toThrow(/Already reverted/);
  });

  it("refuses to revert over a human change", async () => {
    const { d, j, store } = deps();
    await handleAlert(d, alert());
    j.issues.set("BPAT-1", { ...j.issues.get("BPAT-1")!, assigneeAccountId: "acc-lifeguard" });
    const assign = store.audit.find((e) => e.action === "assign")!;
    await expect(revertAction(d, assign.id, "acc-admin")).rejects.toThrow(/changed the assignee/);
    const create = store.audit.find((e) => e.action === "create")!;
    await expect(revertAction(d, create.id, "acc-admin")).rejects.toThrow(/can't be reverted/);
  });

  it("promotes a queued alert into an incident, or dismisses it", async () => {
    const { d, store } = deps();
    await handleAlert(d, alert({ alertId: "low1", confidence: 0.2 }));
    await handleAlert(d, alert({ alertId: "low2", confidence: 0.2, zone: "south" }));
    const out = await promoteQueued(d, store.queue[0]!.id, "acc-admin");
    expect(out).toMatchObject({ outcome: "created", issueKey: "BPAT-1" });
    await dismissQueued(d, store.queue[1]!.id, "acc-admin");
    expect(store.queue.map((q) => q.status)).toEqual(["promoted", "dismissed"]);
    await expect(promoteQueued(d, store.queue[1]!.id, "acc-admin")).rejects.toThrow(/no longer waiting/);
  });
});
