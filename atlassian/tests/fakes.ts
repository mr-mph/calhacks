import type { Alert } from "../src/domain/alert";
import type { OpenIncident } from "../src/domain/plan";
import type { RosterEntry } from "../src/domain/roster";
import { scopedJira } from "../src/services/scopedJira";
import type { AlertRecord, AuditEntry, Deps, IssueState, JiraPort, NewIssue, QueueItem, StorePort } from "../src/ports";

export interface Call {
  op: string;
  key?: string;
  value?: unknown;
}

export function fakeJira(projectKey = "BPAT") {
  const calls: Call[] = [];
  const issues = new Map<string, IssueState & { labels: string[]; description: unknown }>();
  let n = 0;
  const raw: JiraPort = {
    async createIssue(issue: NewIssue) {
      const key = `${projectKey}-${++n}`;
      calls.push({ op: "create", key, value: issue });
      issues.set(key, {
        key, summary: issue.summary, status: "To Do", isDone: false, assigneeAccountId: null, assigneeName: null,
        priority: issue.priority, created: Date.now(), resolved: null, labels: issue.labels, description: issue.description,
      });
      return key;
    },
    async addComment(key, body) {
      calls.push({ op: "comment", key, value: body });
      return `c${calls.length}`;
    },
    async deleteComment(key, id) {
      calls.push({ op: "delete-comment", key, value: id });
    },
    async assign(key, accountId) {
      calls.push({ op: "assign", key, value: accountId });
      const issue = issues.get(key);
      if (issue) issues.set(key, { ...issue, assigneeAccountId: accountId });
    },
    async setPriority(key, priority) {
      calls.push({ op: "priority", key, value: priority });
      const issue = issues.get(key);
      if (issue) issues.set(key, { ...issue, priority });
    },
    async getIssue(key) {
      return issues.get(key) ?? null;
    },
  };
  return { raw, jira: scopedJira(raw), calls, issues };
}

export function fakeStore(roster: RosterEntry[] = []): StorePort & { audit: AuditEntry[]; queue: QueueItem[] } {
  const audit: AuditEntry[] = [];
  const queue: QueueItem[] = [];
  const zones = new Map<string, OpenIncident>();
  const alerts = new Map<string, AlertRecord>();
  let state = roster;
  let id = 0;
  return {
    audit,
    queue,
    getRoster: async () => state,
    setRoster: async (r) => { state = r; },
    getZone: async (z) => zones.get(z) ?? null,
    setZone: async (z, i) => { zones.set(z, i); },
    getAlert: async (a) => alerts.get(a) ?? null,
    setAlert: async (r) => { alerts.set(r.alertId, r); },
    appendAudit: async (e) => {
      const saved = { ...e, id: String(++id), at: Date.now() };
      audit.unshift(saved);
      return saved;
    },
    getAudit: async (i) => audit.find((e) => e.id === i) ?? null,
    updateAudit: async (e) => { audit.splice(audit.findIndex((x) => x.id === e.id), 1, e); },
    listAudit: async (limit) => audit.slice(0, limit),
    auditForIssue: async (key) => audit.filter((e) => e.issueKey === key),
    addQueue: async (alert: Alert, reason: string) => {
      const item: QueueItem = { id: `q${++id}`, at: Date.now(), alert, reason, status: "open" };
      queue.push(item);
      return item;
    },
    getQueue: async (i) => queue.find((q) => q.id === i) ?? null,
    updateQueue: async (item) => { queue.splice(queue.findIndex((q) => q.id === item.id), 1, item); },
    listQueue: async () => queue,
  };
}

export const ROSTER: RosterEntry[] = [{ name: "Maya", accountId: "acc-maya", start: "00:00", end: "00:00" }];

export function alert(overrides: Partial<Alert> = {}): Alert {
  return {
    alertId: "a1",
    text: "Rip forming north of the stairs, 2 people in the water near it.",
    uncertainty: "Glare on the left third of the frame.",
    zone: "north-stairs",
    personWater: 2,
    personBeach: 5,
    confidence: 0.82,
    frameUrl: "https://station.local/frames/1.jpg",
    observedAt: Date.parse("2026-10-24T20:00:00Z"),
    ...overrides,
  };
}

export function deps(roster = ROSTER, now = () => new Date("2026-10-24T20:00:30Z")) {
  const j = fakeJira();
  const store = fakeStore(roster);
  const d: Deps = { jira: j.jira, store, now };
  return { d, j, store };
}
