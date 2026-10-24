import { kvs, WhereConditions } from "@forge/kvs";
import { randomUUID } from "node:crypto";
import type { Alert } from "../domain/alert";
import type { OpenIncident } from "../domain/plan";
import type { RosterEntry } from "../domain/roster";
import type { AlertRecord, AuditEntry, NewAuditEntry, QueueItem, StorePort } from "../ports";

const PAGE = 100;
const FAR_FUTURE_MS = 9_999_999_999_999;

// KVS lists keys in ascending order, so an inverted timestamp makes the newest entry come first.
const newestFirstId = (at: number): string =>
  `${String(FAR_FUTURE_MS - at).padStart(13, "0")}-${randomUUID().slice(0, 8)}`;

async function listPrefix<T>(prefix: string, limit: number): Promise<T[]> {
  const out: T[] = [];
  let cursor: string | undefined;
  do {
    let query = kvs.query().where("key", WhereConditions.beginsWith(prefix)).limit(Math.min(PAGE, limit - out.length));
    if (cursor) query = query.cursor(cursor);
    const page = await query.getMany<T>();
    out.push(...page.results.map((r) => r.value));
    cursor = page.nextCursor;
  } while (cursor && out.length < limit);
  return out;
}

async function auditForIssue(issueKey: string): Promise<AuditEntry[]> {
  const ids = await listPrefix<string>(`issue-audit:${issueKey}:`, 200);
  const entries = await Promise.all(ids.map((id) => kvs.get<AuditEntry>(`audit:${id}`)));
  return entries.filter((e): e is AuditEntry => e !== undefined);
}

async function appendAudit(entry: NewAuditEntry): Promise<AuditEntry> {
  const at = Date.now();
  const saved: AuditEntry = { ...entry, id: newestFirstId(at), at };
  await kvs.set(`audit:${saved.id}`, saved);
  if (saved.issueKey) await kvs.set(`issue-audit:${saved.issueKey}:${saved.id}`, saved.id);
  return saved;
}

async function addQueue(alert: Alert, reason: string): Promise<QueueItem> {
  const at = Date.now();
  const item: QueueItem = { id: newestFirstId(at), at, alert, reason, status: "open" };
  await kvs.set(`queue:${item.id}`, item);
  return item;
}

export const kvsStore: StorePort = {
  getRoster: async () => (await kvs.get<RosterEntry[]>("roster")) ?? [],
  setRoster: (roster) => kvs.set("roster", roster),
  getZone: async (zone) => (await kvs.get<OpenIncident>(`zone:${zone}`)) ?? null,
  setZone: (zone, incident) => kvs.set(`zone:${zone}`, incident),
  getAlert: async (alertId) => (await kvs.get<AlertRecord>(`alert:${alertId}`)) ?? null,
  setAlert: (record) => kvs.set(`alert:${record.alertId}`, record),
  appendAudit,
  getAudit: async (id) => (await kvs.get<AuditEntry>(`audit:${id}`)) ?? null,
  updateAudit: (entry) => kvs.set(`audit:${entry.id}`, entry),
  listAudit: (limit) => listPrefix<AuditEntry>("audit:", limit),
  auditForIssue,
  addQueue,
  getQueue: async (id) => (await kvs.get<QueueItem>(`queue:${id}`)) ?? null,
  updateQueue: (item) => kvs.set(`queue:${item.id}`, item),
  listQueue: () => listPrefix<QueueItem>("queue:", 200),
};
