import { ConvexError, v } from "convex/values";
import { mutation } from "./_generated/server";
import { startSend } from "./jira";
import { requireEnvSecret } from "./secrets";
import { JIRA_STALLED_AFTER_S } from "./validators";

const WRONG_PATROL_CODE = "Wrong patrol code";

export const review = mutation({
  args: {
    id: v.id("alerts"),
    decision: v.union(v.literal("confirmed"), v.literal("dismissed")),
    code: v.string(),
  },
  handler: async (ctx, { id, decision, code }) => {
    requireEnvSecret("PATROL_CODE", code, WRONG_PATROL_CODE);
    const alert = await ctx.db.get(id);
    if (!alert) throw new ConvexError("This alert no longer exists");
    if (alert.status !== "needs_review") {
      throw new ConvexError(`Someone already marked this alert ${alert.status}`);
    }
    await ctx.db.patch(id, { status: decision, reviewedAt: Date.now() / 1000 });
    if (decision === "confirmed") await startSend(ctx, alert);
  },
});

export const retryJira = mutation({
  args: { id: v.id("alerts"), code: v.string() },
  handler: async (ctx, { id, code }) => {
    requireEnvSecret("PATROL_CODE", code, WRONG_PATROL_CODE);
    const alert = await ctx.db.get(id);
    if (!alert) throw new ConvexError("This alert no longer exists");
    if (alert.status !== "confirmed") throw new ConvexError("Only confirmed alerts go to Jira");
    const jira = alert.jira;
    const isStalled = jira?.status === "sending" && Date.now() / 1000 - jira.updatedAt > JIRA_STALLED_AFTER_S;
    if (jira && jira.status !== "failed" && !isStalled) {
      throw new ConvexError(jira.status === "sent" ? "Already sent to Jira" : "Still sending to Jira");
    }
    await startSend(ctx, alert);
  },
});
