import type { Alert } from "./alert";

export const PRIORITIES = ["Lowest", "Low", "Medium", "High", "Highest"] as const;
export type Priority = (typeof PRIORITIES)[number];

export interface Severity {
  priority: Priority;
  reason: string;
}

export function severityOf(alert: Alert): Severity {
  if (alert.personWater > 0) {
    return { priority: "Highest", reason: `${alert.personWater} people in the water near a rip current` };
  }
  if (alert.personBeach > 0) {
    return { priority: "High", reason: `Rip current forming with ${alert.personBeach} people on the beach nearby` };
  }
  return { priority: "Medium", reason: "Rip current forming with no one counted nearby" };
}

export function rank(priority: string | null | undefined): number {
  return PRIORITIES.indexOf(priority as Priority);
}
