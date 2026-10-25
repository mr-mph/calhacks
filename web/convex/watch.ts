import type { Infer } from "convex/values";
import type { MutationCtx } from "./_generated/server";
import { v } from "convex/values";
import { observationFields } from "./validators";

const observation = v.object(observationFields);
type Observation = Infer<typeof observation>;

export const HOUR_S = 3600;

function peopleNearRip(obs: Observation, waterZones: string[]): number {
  if (obs.rip === undefined || obs.rip.length === 0) return 0;
  return waterZones.reduce((sum, id) => sum + (obs.zones?.[id]?.person ?? 0), 0);
}

async function waterZoneIds(ctx: MutationCtx): Promise<string[]> {
  const site = await ctx.db.query("sites").withIndex("by_updated").order("desc").first();
  return (site?.zones ?? []).filter((z) => z.kind === "water").map((z) => z.id);
}

type Bucket = { session: string; hour: number; frames: number; lastT: number; peakNearRip: number };

function bucketize(observations: Observation[], waterZones: string[]): Bucket[] {
  const buckets = new Map<string, Bucket>();
  for (const obs of observations) {
    const hour = Math.floor(obs.t / HOUR_S) * HOUR_S;
    const key = `${obs.session}\u0000${hour}`;
    const prev = buckets.get(key) ?? { session: obs.session, hour, frames: 0, lastT: obs.t, peakNearRip: 0 };
    buckets.set(key, {
      ...prev,
      frames: prev.frames + 1,
      lastT: Math.max(prev.lastT, obs.t),
      peakNearRip: Math.max(prev.peakNearRip, peopleNearRip(obs, waterZones)),
    });
  }
  return [...buckets.values()];
}

// People near a rip = people in the site's water zones in a frame where the detector flagged a rip.
export async function recordWatch(ctx: MutationCtx, observations: Observation[]): Promise<void> {
  if (observations.length === 0) return;
  const waterZones = await waterZoneIds(ctx);
  for (const b of bucketize(observations, waterZones)) {
    const row = await ctx.db
      .query("watchHours")
      .withIndex("by_session_hour", (q) => q.eq("session", b.session).eq("hour", b.hour))
      .first();
    if (!row) {
      await ctx.db.insert("watchHours", b);
      continue;
    }
    await ctx.db.patch(row._id, {
      frames: row.frames + b.frames,
      lastT: Math.max(row.lastT, b.lastT),
      peakNearRip: Math.max(row.peakNearRip, b.peakNearRip),
    });
  }
}
