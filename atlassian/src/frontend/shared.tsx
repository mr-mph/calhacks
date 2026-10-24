import { invoke } from "@forge/bridge";
import { Lozenge } from "@forge/react";
import type { AuditAction, AuditEntry } from "../ports";

type Result<T> = { ok: true; data: T } | { ok: false; error: string };

export async function call<T>(name: string, payload: Record<string, unknown> = {}): Promise<T> {
  const result = (await invoke(name, payload)) as Result<T>;
  if (!result.ok) throw new Error(result.error);
  return result.data;
}

type Appearance = "default" | "success" | "removed" | "inprogress" | "new" | "moved";

const APPEARANCE: Record<AuditAction, Appearance> = {
  create: "success",
  comment: "default",
  assign: "inprogress",
  escalate: "removed",
  "request-detail": "new",
  queue: "new",
  flag: "moved",
  blocked: "removed",
  error: "removed",
  revert: "default",
  promote: "success",
  dismiss: "default",
  roster: "default",
  setup: "default",
  report: "inprogress",
};

export const ActionLozenge = ({ action }: { action: AuditAction }) => (
  <Lozenge appearance={APPEARANCE[action]} isBold={action === "flag" || action === "escalate"}>
    {action}
  </Lozenge>
);

export const when = (ms: number): string =>
  new Date(ms).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", second: "2-digit" });

export const actorLabel = (entry: AuditEntry): string => (entry.actor === "agent" ? "Agent" : entry.actor === "station" ? "Station" : "Person");
