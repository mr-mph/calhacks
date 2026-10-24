import type { Alert } from "./domain/alert";
import { description, frameReceived, frameRequest, repeatComment, summary } from "./domain/content";
import { decide, type OpenIncident, type Plan } from "./domain/plan";
import { PROJECT_KEY } from "./domain/scope";
import { AGENT, type AlertRecord, type Deps, type NewAuditEntry } from "./ports";

export interface Outcome {
  outcome: "created" | "updated" | "queued" | "repeat";
  reason: string;
  issueKey?: string;
  queueId?: string;
  flags: string[];
  missing: string[];
}

type Plans<K extends Plan["kind"]> = Extract<Plan, { kind: K }>;

const alertInputs = (alert: Alert): Record<string, unknown> => ({
  alertId: alert.alertId,
  zone: alert.zone,
  personWater: alert.personWater,
  personBeach: alert.personBeach,
  confidence: alert.confidence,
  frameUrl: alert.frameUrl,
  observedAt: alert.observedAt,
  text: alert.text.slice(0, 300),
});

const outcome = (plan: Plan, o: Omit<Outcome, "flags" | "missing">): Outcome => ({
  ...o,
  flags: plan.findings.map((f) => f.rule),
  missing: plan.missingFrame ? ["frame_url"] : [],
});

function audit(deps: Deps, alert: Alert, entry: Omit<NewAuditEntry, "actor" | "alertId" | "inputs"> & { inputs?: Record<string, unknown> }) {
  return deps.store.appendAudit({ actor: AGENT, alertId: alert.alertId, ...entry, inputs: { ...alertInputs(alert), ...entry.inputs } });
}

async function openIncident(deps: Deps, zone: string): Promise<OpenIncident | null> {
  const incident = await deps.store.getZone(zone);
  if (!incident) return null;
  const issue = await deps.jira.getIssue(incident.issueKey);
  return issue && !issue.isDone ? incident : null;
}

async function requestFrame(deps: Deps, alert: Alert, issueKey: string): Promise<void> {
  const commentId = await deps.jira.addComment(issueKey, frameRequest(alert));
  await audit(deps, alert, {
    action: "request-detail",
    issueKey,
    reason: "Alert has no frame link; asked the station to re-send it",
    revert: { type: "delete-comment", commentId },
  });
}

async function queue(deps: Deps, alert: Alert, plan: Plans<"queue">): Promise<Outcome> {
  const item = await deps.store.addQueue(alert, plan.reason);
  await audit(deps, alert, { action: "queue", reason: plan.reason, inputs: { queueId: item.id } });
  await deps.store.setAlert({ alertId: alert.alertId, outcome: "queued", queueId: item.id, missingFrame: plan.missingFrame });
  return outcome(plan, { outcome: "queued", queueId: item.id, reason: `Not paged. ${plan.reason}` });
}

async function update(deps: Deps, alert: Alert, plan: Plans<"update">): Promise<Outcome> {
  const { issueKey, previousPriority } = plan;
  const commentId = await deps.jira.addComment(issueKey, repeatComment(alert, plan.escalate, plan.findings));
  await audit(deps, alert, { action: "comment", issueKey, reason: plan.reason, revert: { type: "delete-comment", commentId } });
  if (plan.escalate) {
    await deps.jira.setPriority(issueKey, plan.escalate.priority);
    await audit(deps, alert, {
      action: "escalate",
      issueKey,
      reason: `${previousPriority} to ${plan.escalate.priority}: ${plan.escalate.reason}`,
      revert: { type: "restore-priority", from: previousPriority, to: plan.escalate.priority },
    });
  }
  if (plan.missingFrame) await requestFrame(deps, alert, issueKey);
  const priority = plan.escalate?.priority ?? previousPriority;
  await deps.store.setZone(alert.zone, { issueKey, priority, lastAlertAt: deps.now().getTime() });
  await deps.store.setAlert({ alertId: alert.alertId, outcome: "updated", issueKey, missingFrame: plan.missingFrame });
  return outcome(plan, { outcome: "updated", issueKey, reason: `Duplicate: commented on ${issueKey}. ${plan.reason}` });
}

async function create(deps: Deps, alert: Alert, plan: Plans<"create">, promotedBy?: string): Promise<Outcome> {
  const issueKey = await deps.jira.createIssue({
    projectKey: PROJECT_KEY,
    summary: summary(alert, plan.severity),
    description: description(alert, plan.severity, plan.assignReason, plan.findings),
    priority: plan.severity.priority,
    labels: plan.labels,
  });
  // Recorded before the follow-up calls so a station retry after a partial failure can't open a second issue.
  await deps.store.setAlert({ alertId: alert.alertId, outcome: "created", issueKey, missingFrame: plan.missingFrame });
  const why = promotedBy ? `Promoted from the review queue by ${promotedBy}. ` : "";
  await audit(deps, alert, {
    action: "create",
    issueKey,
    reason: `${why}${plan.severity.priority}: ${plan.severity.reason}`,
    inputs: { priority: plan.severity.priority, labels: plan.labels },
  });
  if (plan.assignee) {
    await deps.jira.assign(issueKey, plan.assignee.accountId);
    await audit(deps, alert, {
      action: "assign",
      issueKey,
      reason: plan.assignReason,
      inputs: { assignee: plan.assignee.name, accountId: plan.assignee.accountId },
      revert: { type: "unassign", accountId: plan.assignee.accountId },
    });
  }
  if (plan.missingFrame) await requestFrame(deps, alert, issueKey);
  await deps.store.setZone(alert.zone, { issueKey, priority: plan.severity.priority, lastAlertAt: deps.now().getTime() });
  const assigned = plan.assignee ? `assigned to ${plan.assignee.name}` : `unassigned (${plan.assignReason.toLowerCase()})`;
  return outcome(plan, { outcome: "created", issueKey, reason: `Created ${issueKey}, ${plan.severity.priority}, ${assigned}` });
}

// A re-sent alert (same alert_id) is a no-op unless it finally carries the frame we asked for.
async function repeat(deps: Deps, alert: Alert, record: AlertRecord): Promise<Outcome> {
  const base = { outcome: "repeat" as const, issueKey: record.issueKey, queueId: record.queueId, flags: [], missing: [] };
  if (!record.issueKey || !record.missingFrame || !alert.frameUrl) {
    return { ...base, reason: `Alert ${alert.alertId} was already handled (${record.outcome})` };
  }
  const commentId = await deps.jira.addComment(record.issueKey, frameReceived(alert));
  await audit(deps, alert, {
    action: "comment",
    issueKey: record.issueKey,
    reason: "Station re-sent the alert with the missing frame link",
    revert: { type: "delete-comment", commentId },
  });
  await deps.store.setAlert({ ...record, missingFrame: false });
  return { ...base, reason: `Added the missing frame to ${record.issueKey}` };
}

export async function handleAlert(deps: Deps, alert: Alert, promotedBy?: string): Promise<Outcome> {
  const record = await deps.store.getAlert(alert.alertId);
  if (record && !(promotedBy && record.outcome === "queued")) return repeat(deps, alert, record);

  const [roster, incident] = await Promise.all([deps.store.getRoster(), openIncident(deps, alert.zone)]);
  const plan = decide(alert, { now: deps.now(), roster, openIncident: incident, promotedBy });
  const result = await execute(deps, alert, plan, promotedBy);
  if (plan.findings.length) {
    await audit(deps, alert, {
      action: "flag",
      issueKey: result.issueKey,
      reason: "Alert text contained instructions. They were ignored: actions use only zone, counts, confidence and the roster.",
      inputs: { findings: plan.findings },
    });
  }
  return result;
}

function execute(deps: Deps, alert: Alert, plan: Plan, promotedBy?: string): Promise<Outcome> {
  if (plan.kind === "queue") return queue(deps, alert, plan);
  if (plan.kind === "update") return update(deps, alert, plan);
  return create(deps, alert, plan, promotedBy);
}
