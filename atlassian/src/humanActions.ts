import { handleAlert, type Outcome } from "./agent";
import { assertIssue } from "./domain/scope";
import type { AuditEntry, Deps, RevertSpec } from "./ports";

async function undo(deps: Deps, issueKey: string, spec: RevertSpec): Promise<string> {
  if (spec.type === "delete-comment") {
    await deps.jira.deleteComment(issueKey, spec.commentId);
    return `Deleted the agent's comment ${spec.commentId}`;
  }
  const issue = await deps.jira.getIssue(issueKey);
  if (!issue) throw new Error(`${issueKey} no longer exists`);
  if (spec.type === "unassign") {
    if (issue.assigneeAccountId !== spec.accountId) throw new Error("Someone changed the assignee since; leaving it alone");
    await deps.jira.assign(issueKey, null);
    return "Unassigned the issue";
  }
  if (issue.priority !== spec.to) throw new Error("Someone changed the priority since; leaving it alone");
  await deps.jira.setPriority(issueKey, spec.from as typeof spec.to);
  return `Restored priority to ${spec.from}`;
}

// Reverts only what the agent did, and refuses when a person has changed the field since,
// so a revert never overwrites a human decision.
export async function revertAction(deps: Deps, auditId: string, actor: string): Promise<AuditEntry> {
  const entry = await deps.store.getAudit(auditId);
  if (!entry) throw new Error("No such audit entry");
  if (entry.actor !== "agent" || !entry.revert || !entry.issueKey) throw new Error("This action can't be reverted");
  if (entry.revertedAt) throw new Error("Already reverted");
  assertIssue(entry.issueKey);
  const done = await undo(deps, entry.issueKey, entry.revert);
  await deps.store.updateAudit({ ...entry, revertedAt: deps.now().getTime(), revertedBy: actor });
  return deps.store.appendAudit({
    action: "revert",
    actor,
    issueKey: entry.issueKey,
    alertId: entry.alertId,
    reason: done,
    inputs: { revertedEntry: entry.id, revertedAction: entry.action },
  });
}

export async function promoteQueued(deps: Deps, queueId: string, actor: string): Promise<Outcome> {
  const item = await deps.store.getQueue(queueId);
  if (!item || item.status !== "open") throw new Error("This alert is no longer waiting");
  const result = await handleAlert(deps, item.alert, actor);
  await deps.store.updateQueue({ ...item, status: "promoted", issueKey: result.issueKey });
  await deps.store.appendAudit({
    action: "promote",
    actor,
    issueKey: result.issueKey,
    alertId: item.alert.alertId,
    reason: "A person looked at the low-confidence alert and opened an incident",
    inputs: { queueId },
  });
  return result;
}

export async function dismissQueued(deps: Deps, queueId: string, actor: string): Promise<void> {
  const item = await deps.store.getQueue(queueId);
  if (!item || item.status !== "open") throw new Error("This alert is no longer waiting");
  await deps.store.updateQueue({ ...item, status: "dismissed" });
  await deps.store.appendAudit({
    action: "dismiss",
    actor,
    alertId: item.alert.alertId,
    reason: "A person looked at the low-confidence alert and dismissed it",
    inputs: { queueId },
  });
}
