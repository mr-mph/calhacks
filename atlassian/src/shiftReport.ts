import { buildReport, dayStart, renderAdf, renderStorage, reportTitle, type ShiftReport } from "./domain/report";
import { PROJECT_KEY } from "./domain/scope";
import type { IssueState } from "./ports";
import { createPage, firstSpace } from "./services/confluence";
import { agentJira, openIncidents } from "./services/jira";
import { kvsStore as store } from "./services/store";

const AUDIT_SCAN = 1000;

export interface ReportResult {
  where: "confluence" | "jira";
  url: string;
  report: ShiftReport;
}

async function collect(now: Date): Promise<ShiftReport> {
  const since = dayStart(now);
  const today = (await store.listAudit(AUDIT_SCAN)).filter((e) => e.at >= since);
  const keys = [...new Set(today.filter((e) => e.action === "create" && e.issueKey).map((e) => e.issueKey!))];
  const issues = await Promise.all(keys.map((k) => agentJira.getIssue(k)));
  const byKey = new Map(issues.filter((i): i is IssueState => i !== null).map((i) => [i.key, i]));
  const [stillOpen, queue] = await Promise.all([openIncidents(), store.listQueue()]);
  return buildReport(now, today, byKey, stillOpen, queue);
}

async function publish(report: ShiftReport, title: string): Promise<Pick<ReportResult, "where" | "url">> {
  try {
    const space = await firstSpace();
    if (space) return { where: "confluence", url: await createPage(space.id, title, renderStorage(report)) };
  } catch (err) {
    console.warn("Confluence report failed, falling back to Jira", err);
  }
  const key = await agentJira.createIssue({
    projectKey: PROJECT_KEY,
    summary: title,
    description: renderAdf(report),
    priority: "Low",
    labels: ["balloon-patrol-report"],
  });
  return { where: "jira", url: key };
}

export async function writeShiftReport(actor: string, now = new Date()): Promise<ReportResult> {
  const report = await collect(now);
  const title = reportTitle(report, now);
  const target = await publish(report, title);
  await store.appendAudit({
    action: "report",
    actor,
    reason: `Shift report written to ${target.where}`,
    issueKey: target.where === "jira" ? target.url : undefined,
    inputs: { title, url: target.url, incidents: report.incidents.length, open: report.stillOpen.length },
  });
  return { ...target, report };
}
