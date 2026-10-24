import type { Alert } from "./alert";
import { bullets, doc, link, panel, paragraph, strong, type AdfNode } from "./adf";
import type { InjectionFinding } from "./injection";
import type { Severity } from "./severity";

const MAX_SUMMARY = 120;

const iso = (ms: number): string => new Date(ms).toISOString().replace(".000Z", "Z");

export function summary(alert: Alert, severity: Severity): string {
  const who = alert.personWater > 0 ? `${alert.personWater} in water` : "rip forming";
  return `[${severity.priority}] Zone ${alert.zone}: ${who}`.slice(0, MAX_SUMMARY);
}

function facts(alert: Alert): AdfNode {
  return bullets([
    [strong("People in water: "), String(alert.personWater)],
    [strong("People on beach: "), String(alert.personBeach)],
    [strong("Confidence: "), alert.confidence.toFixed(2)],
    [strong("Zone: "), alert.zone],
    [strong("Seen by the balloon at: "), iso(alert.observedAt)],
    [strong("Alert id: "), alert.alertId],
  ]);
}

const frame = (alert: Alert): AdfNode =>
  alert.frameUrl
    ? paragraph(strong("Frame: "), link(alert.frameUrl))
    : paragraph(strong("Frame: "), "missing. The agent asked the station for it in a comment.");

export function injectionNotice(findings: InjectionFinding[]): AdfNode {
  const list = findings.map((f) => `${f.rule} ("${f.match}")`).join("; ");
  return panel(
    "warning",
    paragraph(strong("Instructions in alert text were ignored. "), `The agent treats alert text as data. Flagged: ${list}.`),
  );
}

export function description(alert: Alert, severity: Severity, assignReason: string, findings: InjectionFinding[]): AdfNode {
  return doc(
    paragraph(strong("Alert (station text, confirmed by a person): "), alert.text),
    paragraph(strong("Uncertainty: "), alert.uncertainty || "none given"),
    facts(alert),
    frame(alert),
    paragraph(strong("Why this priority: "), `${severity.priority} because ${severity.reason.toLowerCase()}.`),
    paragraph(strong("Why this assignee: "), `${assignReason}.`),
    ...(findings.length ? [injectionNotice(findings)] : []),
  );
}

export function repeatComment(alert: Alert, escalate: Severity | null, findings: InjectionFinding[]): AdfNode {
  return doc(
    paragraph(strong("Same zone, new alert: "), alert.text),
    paragraph(strong("Uncertainty: "), alert.uncertainty || "none given"),
    facts(alert),
    frame(alert),
    ...(escalate ? [paragraph(strong("Escalated to " + escalate.priority + ": "), `${escalate.reason}.`)] : []),
    ...(findings.length ? [injectionNotice(findings)] : []),
  );
}

export function frameRequest(alert: Alert): AdfNode {
  return doc(
    paragraph(
      strong("Missing detail: "),
      `alert ${alert.alertId} arrived without a frame link. Station, please re-send this alert with frame_url so the patrol can see what the balloon saw.`,
    ),
  );
}

export function frameReceived(alert: Alert): AdfNode {
  return doc(paragraph(strong("Frame received for alert " + alert.alertId + ": "), link(alert.frameUrl ?? "")));
}
