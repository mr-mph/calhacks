import type { AuditEntry, IssueState, QueueItem } from "../ports";
import { bullets, doc, paragraph, strong, type AdfNode } from "./adf";
import { localMinutes, SHIFT_TIME_ZONE } from "./roster";

export interface IncidentRow {
  key: string;
  zone: string;
  priority: string;
  status: string;
  assignee: string;
  createdAt: number;
  ticketLatencyMs: number | null;
  resolvedAfterMs: number | null;
}

export interface ShiftReport {
  day: string;
  incidents: IncidentRow[];
  stillOpen: IssueState[];
  queued: QueueItem[];
  updates: number;
  escalations: number;
  flagged: number;
  reverts: number;
  medianTicketLatencyMs: number | null;
  medianResolveMs: number | null;
}

export function dayStart(now: Date): number {
  const msIntoMinute = now.getUTCSeconds() * 1000 + now.getUTCMilliseconds();
  return now.getTime() - localMinutes(now) * 60_000 - msIntoMinute;
}

export const dayLabel = (now: Date): string =>
  new Intl.DateTimeFormat("en-CA", { timeZone: SHIFT_TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);

const clock = (ms: number): string =>
  new Intl.DateTimeFormat("en-US", { timeZone: SHIFT_TIME_ZONE, hour: "numeric", minute: "2-digit" }).format(new Date(ms));

export function duration(ms: number | null): string {
  if (ms === null) return "n/a";
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2;
}

function row(entry: AuditEntry, issue: IssueState | undefined): IncidentRow {
  const observedAt = typeof entry.inputs.observedAt === "number" ? entry.inputs.observedAt : null;
  return {
    key: entry.issueKey ?? "?",
    zone: String(entry.inputs.zone ?? "?"),
    priority: issue?.priority ?? String(entry.inputs.priority ?? "?"),
    status: issue?.status ?? "Unknown",
    assignee: issue?.assigneeName ?? "Unassigned",
    createdAt: entry.at,
    ticketLatencyMs: observedAt === null ? null : entry.at - observedAt,
    resolvedAfterMs: issue?.resolved ? issue.resolved - (issue.created || entry.at) : null,
  };
}

export function buildReport(
  now: Date,
  todaysEntries: AuditEntry[],
  issues: Map<string, IssueState>,
  stillOpen: IssueState[],
  queue: QueueItem[],
): ShiftReport {
  const count = (action: AuditEntry["action"]) => todaysEntries.filter((e) => e.action === action).length;
  const incidents = todaysEntries
    .filter((e) => e.action === "create" && e.issueKey)
    .map((e) => row(e, issues.get(e.issueKey!)))
    .sort((a, b) => a.createdAt - b.createdAt);
  return {
    day: dayLabel(now),
    incidents,
    stillOpen,
    queued: queue.filter((q) => q.status === "open"),
    updates: count("comment"),
    escalations: count("escalate"),
    flagged: count("flag"),
    reverts: count("revert"),
    medianTicketLatencyMs: median(incidents.flatMap((i) => (i.ticketLatencyMs === null ? [] : [i.ticketLatencyMs]))),
    medianResolveMs: median(incidents.flatMap((i) => (i.resolvedAfterMs === null ? [] : [i.resolvedAfterMs]))),
  };
}

export const reportTitle = (r: ShiftReport, now: Date): string => `Beach Patrol shift report ${r.day} (${clock(now.getTime())})`;

const summaryLines = (r: ShiftReport): string[] => [
  `${r.incidents.length} incidents opened, ${r.updates} updates on open incidents, ${r.escalations} escalations.`,
  `Median time from balloon sighting to Jira incident: ${duration(r.medianTicketLatencyMs)}. Median time to resolve: ${duration(r.medianResolveMs)}.`,
  `${r.stillOpen.length} incidents still open, ${r.queued.length} low-confidence alerts waiting for a human look.`,
  `${r.flagged} alerts contained instructions the agent ignored; ${r.reverts} agent actions were reverted by a person.`,
];

const escapeHtml = (s: string): string =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");

const table = (head: string[], rows: string[][]): string =>
  `<table><tbody><tr>${head.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr>${rows
    .map((r) => `<tr>${r.map((c) => `<td>${escapeHtml(c)}</td>`).join("")}</tr>`)
    .join("")}</tbody></table>`;

const incidentCells = (i: IncidentRow): string[] => [
  i.key, clock(i.createdAt), i.zone, i.priority, i.assignee, i.status, duration(i.ticketLatencyMs), duration(i.resolvedAfterMs),
];

export function renderStorage(r: ShiftReport): string {
  const incidents = r.incidents.length
    ? table(["Issue", "Opened", "Zone", "Priority", "Assignee", "Status", "Sighting to ticket", "Time to resolve"], r.incidents.map(incidentCells))
    : "<p>No incidents today.</p>";
  const open = r.stillOpen.length
    ? table(["Issue", "Summary", "Priority", "Assignee", "Status"], r.stillOpen.map((i) => [i.key, i.summary, i.priority ?? "", i.assigneeName ?? "Unassigned", i.status]))
    : "<p>Nothing open.</p>";
  const queued = r.queued.length
    ? table(["Received", "Zone", "Why it is waiting"], r.queued.map((q) => [clock(q.at), q.alert.zone, q.reason]))
    : "<p>Queue is empty.</p>";
  return [
    `<p>${summaryLines(r).map(escapeHtml).join("<br/>")}</p>`,
    "<h2>Incidents today</h2>", incidents,
    "<h2>Open items</h2>", open,
    "<h2>Waiting for a human look</h2>", queued,
    "<p><em>Written by Balloon Patrol from its audit log. Every action listed here can be traced on the issue's Balloon Patrol panel.</em></p>",
  ].join("");
}

export function renderAdf(r: ShiftReport): AdfNode {
  const incidentItems = r.incidents.map((i) => [strong(i.key), ` ${clock(i.createdAt)}, zone ${i.zone}, ${i.priority}, ${i.assignee}, ${i.status}, sighting to ticket ${duration(i.ticketLatencyMs)}`]);
  const openItems = [
    ...r.stillOpen.map((i) => [strong(i.key), ` ${i.summary} (${i.status})`]),
    ...r.queued.map((q) => [strong("Queued"), ` zone ${q.alert.zone}: ${q.reason}`]),
  ];
  return doc(
    ...summaryLines(r).map((line) => paragraph(line)),
    paragraph(strong("Incidents today")),
    incidentItems.length ? bullets(incidentItems) : paragraph("No incidents today."),
    paragraph(strong("Open items")),
    openItems.length ? bullets(openItems) : paragraph("Nothing open."),
  );
}
