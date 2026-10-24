import { query, type QueryCtx } from "./_generated/server";
import type { Doc } from "./_generated/dataModel";

const PRICE_POINTS = 30;
const DECISIONS_PER_LOT = 50;
const OPEN_ALERTS = 20;
const REVIEWED_ALERTS = 6;
const CONFIRMED_SCAN = 50;

async function latestSite(ctx: QueryCtx): Promise<Doc<"sites"> | null> {
  return await ctx.db.query("sites").withIndex("by_updated").order("desc").first();
}

export const now = query({
  args: {},
  handler: async (ctx) => {
    const [observation, frame, site] = await Promise.all([
      ctx.db.query("observations").withIndex("by_t").order("desc").first(),
      ctx.db.query("frames").withIndex("by_t").order("desc").first(),
      latestSite(ctx),
    ]);
    const frameUrl = frame ? await ctx.storage.getUrl(frame.storageId) : null;
    return {
      observation,
      frame: frame && frameUrl ? { ...frame, url: frameUrl } : null,
      site,
    };
  },
});

export const lots = query({
  args: {},
  handler: async (ctx) => {
    const site = await latestSite(ctx);
    const recent = await ctx.db.query("decisions").withIndex("by_t").order("desc").take(50);
    const siteLots = (site?.zones ?? []).filter((z) => z.kind === "lot");
    const ids = [...new Set([...siteLots.map((z) => z.id), ...recent.map((d) => d.zone)])];

    return await Promise.all(
      ids.map(async (id) => {
        const zone = siteLots.find((z) => z.id === id);
        const prices = await ctx.db
          .query("prices")
          .withIndex("by_zone_t", (q) => q.eq("zone", id))
          .order("desc")
          .take(PRICE_POINTS);
        const decisions = await ctx.db
          .query("decisions")
          .withIndex("by_zone_t", (q) => q.eq("zone", id))
          .order("desc")
          .take(DECISIONS_PER_LOT);
        return {
          id,
          name: zone?.name ?? id,
          capacity: zone?.capacity ?? null,
          spaceIds: (site?.spaces ?? []).filter((s) => s.zone === id).map((s) => s.id),
          prices: prices.reverse().map((p) => ({ t: p.t, price: p.price, unit: p.unit ?? "hr" })),
          decisions,
        };
      }),
    );
  },
});

async function withFrameUrl(ctx: QueryCtx, alert: Doc<"alerts">) {
  const frame = alert.frameId ? await ctx.db.get(alert.frameId) : null;
  const frameUrl = frame ? await ctx.storage.getUrl(frame.storageId) : null;
  const audioUrl = alert.audioId ? await ctx.storage.getUrl(alert.audioId) : null;
  return { ...alert, frameUrl, audioUrl };
}

export const alerts = query({
  args: {},
  handler: async (ctx) => {
    const open = await ctx.db
      .query("alerts")
      .withIndex("by_status_t", (q) => q.eq("status", "needs_review"))
      .order("desc")
      .take(OPEN_ALERTS);
    const confirmed = await ctx.db
      .query("alerts")
      .withIndex("by_status_t", (q) => q.eq("status", "confirmed"))
      .order("desc")
      .take(CONFIRMED_SCAN);
    const dismissed = await ctx.db
      .query("alerts")
      .withIndex("by_status_t", (q) => q.eq("status", "dismissed"))
      .order("desc")
      .take(REVIEWED_ALERTS);
    const recent = [...confirmed, ...dismissed]
      .sort((a, b) => (b.reviewedAt ?? b.t) - (a.reviewedAt ?? a.t))
      .slice(0, REVIEWED_ALERTS);
    // A confirmed alert that hasn't reached Jira stays listed until it does, so a failure is never hidden.
    const unsent = confirmed.filter((a) => a.jira && a.jira.status !== "sent" && !recent.includes(a));
    const reviewed = [...unsent, ...recent];
    return {
      open: await Promise.all(open.map((a) => withFrameUrl(ctx, a))),
      reviewed: await Promise.all(reviewed.map((a) => withFrameUrl(ctx, a))),
    };
  },
});
