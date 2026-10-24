import type { Alert } from "./domain/alert";
import type { AdfNode } from "./domain/adf";
import type { OpenIncident } from "./domain/plan";
import type { RosterEntry } from "./domain/roster";
import type { Priority } from "./domain/severity";

export interface IssueState {
  key: string;
  summary: string;
  status: string;
  isDone: boolean;
  assigneeAccountId: string | null;
  assigneeName: string | null;
  priority: string | null;
  created: number;
  resolved: number | null;
}

export interface NewIssue {
  projectKey: string;
  summary: string;
  description: AdfNode;
  priority: Priority;
  labels: string[];
}

export interface JiraPort {
  createIssue(issue: NewIssue): Promise<string>;
  addComment(issueKey: string, body: AdfNode): Promise<string>;
  deleteComment(issueKey: string, commentId: string): Promise<void>;
  assign(issueKey: string, accountId: string | null): Promise<void>;
  setPriority(issueKey: string, priority: Priority): Promise<void>;
  getIssue(issueKey: string): Promise<IssueState | null>;
}

export type AuditAction =
  | "create"
  | "comment"
  | "assign"
  | "escalate"
  | "request-detail"
  | "queue"
  | "flag"
  | "blocked"
  | "error"
  | "revert"
  | "promote"
  | "dismiss"
  | "roster"
  | "setup"
  | "report";

export type RevertSpec =
  | { type: "delete-comment"; commentId: string }
  | { type: "unassign"; accountId: string }
  | { type: "restore-priority"; from: string; to: Priority };

export interface AuditEntry {
  id: string;
  at: number;
  action: AuditAction;
  actor: string;
  reason: string;
  issueKey?: string;
  alertId?: string;
  inputs: Record<string, unknown>;
  revert?: RevertSpec;
  revertedAt?: number;
  revertedBy?: string;
}

export type NewAuditEntry = Omit<AuditEntry, "id" | "at">;

export interface AlertRecord {
  alertId: string;
  outcome: "created" | "updated" | "queued";
  issueKey?: string;
  queueId?: string;
  missingFrame: boolean;
}

export interface QueueItem {
  id: string;
  at: number;
  alert: Alert;
  reason: string;
  status: "open" | "promoted" | "dismissed";
  issueKey?: string;
}

export interface StorePort {
  getRoster(): Promise<RosterEntry[]>;
  setRoster(roster: RosterEntry[]): Promise<void>;
  getZone(zone: string): Promise<OpenIncident | null>;
  setZone(zone: string, incident: OpenIncident): Promise<void>;
  getAlert(alertId: string): Promise<AlertRecord | null>;
  setAlert(record: AlertRecord): Promise<void>;
  appendAudit(entry: NewAuditEntry): Promise<AuditEntry>;
  getAudit(id: string): Promise<AuditEntry | null>;
  updateAudit(entry: AuditEntry): Promise<void>;
  listAudit(limit: number): Promise<AuditEntry[]>;
  auditForIssue(issueKey: string): Promise<AuditEntry[]>;
  addQueue(alert: Alert, reason: string): Promise<QueueItem>;
  getQueue(id: string): Promise<QueueItem | null>;
  updateQueue(item: QueueItem): Promise<void>;
  listQueue(): Promise<QueueItem[]>;
}

export interface Deps {
  jira: JiraPort;
  store: StorePort;
  now: () => Date;
}

export const AGENT = "agent";
