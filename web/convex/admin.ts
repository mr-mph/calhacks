import { v } from "convex/values";
import { internalMutation, type MutationCtx } from "./_generated/server";

// Internal: only the CLI can run these (npx convex run admin:purgeSession '{"session": "..."}' [--prod]).
// Each call deletes up to BATCH rows per table and returns how many it deleted; run it again until all are 0.
const BATCH = 500;

async function sessionWindow(ctx: MutationCtx, session: string): Promise<[number, number] | null> {
  const byT = (order: "asc" | "desc") =>
    ctx.db
      .query("observations")
      .withIndex("by_session_t", (q) => q.eq("session", session))
      .order(order)
      .first();
  const [first, last] = await Promise.all([byT("asc"), byT("desc")]);
  return first && last ? [first.t, last.t] : null;
}

export const purgeSession = internalMutation({
  args: { session: v.string() },
  handler: async (ctx, { session }) => {
    const window = await sessionWindow(ctx, session);
    const decisions = window
      ? await ctx.db
          .query("decisions")
          .withIndex("by_t", (q) => q.gte("t", window[0]).lte("t", window[1]))
          .take(BATCH)
      : [];
    const zones = new Set(decisions.map((d) => d.zone));
    const prices = window
      ? (
          await Promise.all(
            [...zones].map((zone) =>
              ctx.db
                .query("prices")
                .withIndex("by_zone_t", (q) => q.eq("zone", zone).gte("t", window[0]).lte("t", window[1]))
                .take(BATCH),
            ),
          )
        ).flat()
      : [];
    const alerts = (await ctx.db.query("alerts").withIndex("by_t").collect()).filter((a) => a.session === session);
    const frames = await ctx.db
      .query("frames")
      .withIndex("by_session_t", (q) => q.eq("session", session))
      .take(BATCH);
    const observations = await ctx.db
      .query("observations")
      .withIndex("by_session_t", (q) => q.eq("session", session))
      .take(BATCH);

    for (const alert of alerts.slice(0, BATCH)) if (alert.audioId) await ctx.storage.delete(alert.audioId);
    for (const doc of [...decisions, ...prices, ...alerts.slice(0, BATCH)]) await ctx.db.delete(doc._id);
    for (const f of frames) {
      await ctx.storage.delete(f.storageId);
      await ctx.db.delete(f._id);
    }
    const watchHours = await ctx.db
      .query("watchHours")
      .withIndex("by_session_hour", (q) => q.eq("session", session))
      .take(BATCH);
    for (const w of watchHours) await ctx.db.delete(w._id);
    // Observations last: they define the window the decisions and prices are found in.
    const observationsDone = decisions.length < BATCH && prices.length < BATCH;
    if (observationsDone) for (const o of observations) await ctx.db.delete(o._id);

    return {
      decisions: decisions.length,
      prices: prices.length,
      alerts: Math.min(alerts.length, BATCH),
      frames: frames.length,
      watchHours: watchHours.length,
      observations: observationsDone ? observations.length : 0,
    };
  },
});

export const purgeSite = internalMutation({
  args: { site: v.string() },
  handler: async (ctx, { site }) => {
    const rows = await ctx.db
      .query("sites")
      .withIndex("by_site", (q) => q.eq("site", site))
      .collect();
    for (const row of rows) await ctx.db.delete(row._id);
    return { sites: rows.length };
  },
});
