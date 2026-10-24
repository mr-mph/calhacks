import { v } from "convex/values";
import { internal } from "./_generated/api";
import type { Doc } from "./_generated/dataModel";
import { internalAction, internalMutation, internalQuery, type MutationCtx, type QueryCtx } from "./_generated/server";
import { jiraStatus } from "./validators";

// Confirmed alerts go to the Balloon Patrol Forge web trigger (atlassian/README.md, "What happens to an alert").
// Env vars: FORGE_WEBTRIGGER_URL, FORGE_SECRET, FORGE_HEADER (default X-Balloon-Secret).
const TIMEOUT_MS = 25_000;
const MAX_TEXT = 300;
const FALLBACK_ZONE = "beach";

type Payload = {
  alert_id: string;
  text: string;
  uncertainty: string;
  zone: string;
  counts: { person_water: number; person_beach: number };
  confidence: number;
  frame_url: string | null;
  t: number;
};

type Result =
  | { status: "sent"; outcome: string; issueKey?: string; reason?: string }
  | { status: "failed"; error: string };

export async function startSend(ctx: MutationCtx, alert: Doc<"alerts">): Promise<void> {
  const attempts = (alert.jira?.attempts ?? 0) + 1;
  await ctx.db.patch(alert._id, { jira: { status: "sending", attempts, updatedAt: Date.now() / 1000 } });
  await ctx.scheduler.runAfter(0, internal.jira.send, { id: alert._id });
}

async function frameObservation(ctx: QueryCtx, alert: Doc<"alerts">) {
  if (!alert.session) return null;
  return await ctx.db
    .query("observations")
    .withIndex("by_session_t", (q) => q.eq("session", alert.session!).eq("t", alert.t))
    .first();
}

export const payload = internalQuery({
  args: { id: v.id("alerts") },
  handler: async (ctx, { id }): Promise<Payload | string> => {
    const alert = await ctx.db.get(id);
    if (!alert) return "This alert no longer exists";
    const observation = alert.confidence === undefined ? await frameObservation(ctx, alert) : null;
    const confidence = alert.confidence ?? observation?.confidence;
    if (confidence === undefined) return "The alert has no frame confidence, so Jira can't judge it";
    const frame = alert.frameId ? await ctx.db.get(alert.frameId) : null;
    return {
      alert_id: id,
      text: alert.text,
      uncertainty: alert.uncertainty,
      zone: alert.zone ?? FALLBACK_ZONE,
      counts: alert.counts ?? { person_water: 0, person_beach: observation?.counts.person ?? 0 },
      confidence,
      frame_url: frame ? await ctx.storage.getUrl(frame.storageId) : null,
      t: alert.t,
    };
  },
});

function forgeConfig(): { url: string; secret: string; header: string } | string {
  const url = process.env.FORGE_WEBTRIGGER_URL;
  const secret = process.env.FORGE_SECRET;
  if (!url || !secret) return "The Jira link isn't set up on this server (FORGE_WEBTRIGGER_URL, FORGE_SECRET)";
  return { url, secret, header: process.env.FORGE_HEADER || "X-Balloon-Secret" };
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value ? value.slice(0, MAX_TEXT) : undefined;
}

async function post(body: Payload): Promise<Result> {
  const config = forgeConfig();
  if (typeof config === "string") return { status: "failed", error: config };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(config.url, {
      method: "POST",
      headers: { "Content-Type": "application/json", [config.header]: config.secret },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const raw = await response.text();
    let parsed: Record<string, unknown> = {};
    try {
      parsed = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      // non-JSON error page; fall back to the status code below
    }
    if (!response.ok) {
      return { status: "failed", error: `Jira app answered ${response.status}: ${text(parsed.error) ?? "no details"}` };
    }
    const outcome = text(parsed.outcome);
    if (!outcome) return { status: "failed", error: "Jira app answered without an outcome" };
    return { status: "sent", outcome, issueKey: text(parsed.issueKey), reason: text(parsed.reason) };
  } catch (e) {
    const timedOut = (e as Error).name === "AbortError";
    return {
      status: "failed",
      error: timedOut ? `Jira didn't answer within ${TIMEOUT_MS / 1000} s` : `Couldn't reach Jira: ${(e as Error).message}`,
    };
  } finally {
    clearTimeout(timer);
  }
}

export const send = internalAction({
  args: { id: v.id("alerts") },
  handler: async (ctx, { id }) => {
    let result: Result;
    try {
      const body = await ctx.runQuery(internal.jira.payload, { id });
      result = typeof body === "string" ? { status: "failed", error: body } : await post(body);
    } catch (e) {
      result = { status: "failed", error: `Sending failed: ${(e as Error).message.slice(0, MAX_TEXT)}` };
    }
    if (result.status === "failed") console.error("Jira send failed", id, result.error);
    await ctx.runMutation(internal.jira.record, { id, result });
  },
});

export const record = internalMutation({
  args: {
    id: v.id("alerts"),
    result: v.object({
      status: jiraStatus,
      outcome: v.optional(v.string()),
      issueKey: v.optional(v.string()),
      reason: v.optional(v.string()),
      error: v.optional(v.string()),
    }),
  },
  handler: async (ctx, { id, result }) => {
    const alert = await ctx.db.get(id);
    if (!alert) return;
    await ctx.db.patch(id, {
      jira: { ...result, attempts: alert.jira?.attempts ?? 1, updatedAt: Date.now() / 1000 },
    });
  },
});
