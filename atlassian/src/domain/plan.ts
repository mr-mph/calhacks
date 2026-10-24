import type { Alert } from "./alert";
import { detectInjection, type InjectionFinding } from "./injection";
import { onShift, type RosterEntry } from "./roster";
import { rank, severityOf, type Priority, type Severity } from "./severity";

export const DEDUPE_WINDOW_MS = 10 * 60 * 1000;
export const LOW_CONFIDENCE = 0.5;

export interface OpenIncident {
  issueKey: string;
  priority: Priority;
  lastAlertAt: number;
}

export interface PlanContext {
  now: Date;
  roster: readonly RosterEntry[];
  openIncident: OpenIncident | null;
  promotedBy?: string;
}

interface Common {
  findings: InjectionFinding[];
  missingFrame: boolean;
}

export type Plan =
  | (Common & { kind: "queue"; reason: string })
  | (Common & { kind: "update"; issueKey: string; previousPriority: Priority; reason: string; escalate: Severity | null })
  | (Common & { kind: "create"; severity: Severity; assignee: RosterEntry | null; assignReason: string; labels: string[] });

function labels(alert: Alert, findings: InjectionFinding[]): string[] {
  return [
    "balloon-patrol",
    "rip-current",
    `zone-${alert.zone}`,
    ...(alert.personWater > 0 ? ["people-in-water"] : []),
    ...(findings.length > 0 ? ["injection-flagged"] : []),
  ];
}

function assignment(roster: readonly RosterEntry[], now: Date): { assignee: RosterEntry | null; assignReason: string } {
  const assignee = onShift(roster, now);
  if (assignee) return { assignee, assignReason: `${assignee.name} is on shift ${assignee.start} to ${assignee.end}` };
  return { assignee: null, assignReason: roster.length ? "No one on the roster is on shift right now" : "The roster is empty" };
}

function isRecent(incident: OpenIncident | null, now: Date): incident is OpenIncident {
  return incident !== null && now.getTime() - incident.lastAlertAt <= DEDUPE_WINDOW_MS;
}

// Decisions depend only on the structured fields (zone, counts, confidence, frame) and app state.
// alert.text is read here solely to flag injection attempts; it never selects an action, target or value.
export function decide(alert: Alert, ctx: PlanContext): Plan {
  const findings = detectInjection(alert.text, alert.uncertainty);
  const common = { findings, missingFrame: alert.frameUrl === null };

  if (alert.confidence < LOW_CONFIDENCE && !ctx.promotedBy) {
    return {
      ...common,
      kind: "queue",
      reason: `Frame confidence ${alert.confidence.toFixed(2)} is below ${LOW_CONFIDENCE}. Look at the frame before anyone is paged.`,
    };
  }

  const severity = severityOf(alert);
  if (isRecent(ctx.openIncident, ctx.now)) {
    const escalate = rank(severity.priority) > rank(ctx.openIncident.priority) ? severity : null;
    return {
      ...common,
      kind: "update",
      issueKey: ctx.openIncident.issueKey,
      previousPriority: ctx.openIncident.priority,
      reason: `${ctx.openIncident.issueKey} is open for zone ${alert.zone} and had an alert in the last 10 minutes`,
      escalate,
    };
  }

  return { ...common, kind: "create", severity, labels: labels(alert, findings), ...assignment(ctx.roster, ctx.now) };
}
