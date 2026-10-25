import { query, type QueryCtx } from "./_generated/server";
import type { Doc } from "./_generated/dataModel";
import { HOUR_S } from "./watch";

const WINDOW_S = 24 * HOUR_S;
const ALERT_SCAN = 1000;

async function windowEnd(ctx: QueryCtx): Promise<number | null> {
  const [frame, alert] = await Promise.all([
    ctx.db.query("frames").withIndex("by_t").order("desc").first(),
    ctx.db.query("alerts").withIndex("by_t").order("desc").first(),
  ]);
  const end = Math.max(frame?.t ?? 0, alert?.t ?? 0);
  return end > 0 ? end : null;
}

function median(sorted: number[]): number | null {
  const mid = Math.floor(sorted.length / 2);
  const upper = sorted[mid];
  if (upper === undefined) return null;
  return sorted.length % 2 ? upper : ((sorted[mid - 1] ?? upper) + upper) / 2;
}

function confirmSeconds(alerts: Doc<"alerts">[]): number[] {
  return alerts
    .filter((a) => a.status === "confirmed" && a.reviewedAt !== undefined)
    .map((a) => Math.max(0, a.reviewedAt! - a.t))
    .sort((a, b) => a - b);
}

// The 24 hours up to the newest frame (or alert), so a replay of an older flight still shows its numbers.
export const lastDay = query({
  args: {},
  handler: async (ctx) => {
    const end = await windowEnd(ctx);
    const start = (end ?? 0) - WINDOW_S;
    const alerts = end
      ? await ctx.db
          .query("alerts")
          .withIndex("by_t", (q) => q.gte("t", start))
          .take(ALERT_SCAN)
      : [];
    const hours = end
      ? await ctx.db
          .query("watchHours")
          .withIndex("by_hour", (q) => q.gte("hour", Math.floor(start / HOUR_S) * HOUR_S))
          .collect()
      : [];
    const seconds = confirmSeconds(alerts);
    return {
      windowEnd: end,
      drafted: alerts.length,
      confirmed: alerts.filter((a) => a.status === "confirmed").length,
      dismissed: alerts.filter((a) => a.status === "dismissed").length,
      medianToConfirmS: median(seconds),
      worstToConfirmS: seconds.at(-1) ?? null,
      jiraFiled: alerts.filter((a) => a.jira?.status === "sent").length,
      framesWatched: hours.reduce((sum, h) => sum + h.frames, 0),
      peakNearRip: hours.reduce((peak, h) => Math.max(peak, h.peakNearRip), 0),
    };
  },
});
