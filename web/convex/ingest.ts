import { ConvexError, v, type Infer } from "convex/values";
import { mutation, type MutationCtx } from "./_generated/server";
import {
  alertInputFields,
  decisionFields,
  frameFields,
  observationFields,
  priceFields,
  siteFields,
} from "./validators";
import { requireEnvSecret } from "./secrets";

const FRAMES_KEPT = 30;
const MAX_BATCH = 200;

const alertInput = v.object(alertInputFields);
const decisionInput = v.object(decisionFields);
const frameInput = v.object(frameFields);

function checkSecret(given: string): void {
  requireEnvSecret("INGEST_SECRET", given, "Wrong ingest secret");
}

function checkSize(name: string, items: unknown[] | undefined): void {
  if (items && items.length > MAX_BATCH) {
    throw new ConvexError(`Too many ${name} in one batch (max ${MAX_BATCH})`);
  }
}

async function insertFrame(ctx: MutationCtx, frame: Infer<typeof frameInput>): Promise<void> {
  await ctx.db.insert("frames", { ...frame, pinned: false });
  const old = await ctx.db
    .query("frames")
    .withIndex("by_pinned_t", (q) => q.eq("pinned", false))
    .order("desc")
    .take(FRAMES_KEPT + 20);
  for (const f of old.slice(FRAMES_KEPT)) {
    await ctx.storage.delete(f.storageId);
    await ctx.db.delete(f._id);
  }
}

async function insertDecision(ctx: MutationCtx, d: Infer<typeof decisionInput>): Promise<void> {
  await ctx.db.insert("decisions", d);
  await ctx.db.insert("prices", { zone: d.zone, price: d.price_after, t: d.t });
}

async function insertAlert(ctx: MutationCtx, a: Infer<typeof alertInput>): Promise<void> {
  const frame = a.frame
    ? await ctx.db
        .query("frames")
        .withIndex("by_name", (q) => q.eq("name", a.frame!))
        .order("desc")
        .first()
    : null;
  if (frame && !frame.pinned) await ctx.db.patch(frame._id, { pinned: true });
  // Only an uploaded MP3 may be published as the alert's audio, never another stored file such as a frame.
  const audio = a.audioId ? await ctx.db.system.get(a.audioId) : null;
  const isAudio = audio?.contentType === "audio/mpeg";
  await ctx.db.insert("alerts", {
    ...a,
    audioId: isAudio ? a.audioId : undefined,
    voice: isAudio ? a.voice : undefined,
    severity: a.severity ?? "warning",
    status: "needs_review",
    frameId: frame?._id,
  });
}

export const generateUploadUrl = mutation({
  args: { secret: v.string() },
  handler: async (ctx, { secret }) => {
    checkSecret(secret);
    return await ctx.storage.generateUploadUrl();
  },
});

export const batch = mutation({
  args: {
    secret: v.string(),
    frame: v.optional(frameInput),
    observations: v.optional(v.array(v.object(observationFields))),
    decisions: v.optional(v.array(decisionInput)),
    prices: v.optional(v.array(v.object(priceFields))),
    alerts: v.optional(v.array(alertInput)),
  },
  handler: async (ctx, args) => {
    checkSecret(args.secret);
    checkSize("observations", args.observations);
    checkSize("decisions", args.decisions);
    checkSize("prices", args.prices);
    checkSize("alerts", args.alerts);

    if (args.frame) await insertFrame(ctx, args.frame);
    for (const o of args.observations ?? []) await ctx.db.insert("observations", o);
    for (const p of args.prices ?? []) await ctx.db.insert("prices", p);
    for (const d of args.decisions ?? []) await insertDecision(ctx, d);
    for (const a of args.alerts ?? []) await insertAlert(ctx, a);

    return {
      frame: args.frame ? 1 : 0,
      observations: args.observations?.length ?? 0,
      decisions: args.decisions?.length ?? 0,
      prices: args.prices?.length ?? 0,
      alerts: args.alerts?.length ?? 0,
    };
  },
});

export const setSite = mutation({
  args: { secret: v.string(), site: v.object(siteFields) },
  handler: async (ctx, { secret, site }) => {
    checkSecret(secret);
    const existing = await ctx.db
      .query("sites")
      .withIndex("by_site", (q) => q.eq("site", site.site))
      .first();
    const doc = { ...site, updatedAt: Date.now() / 1000 };
    if (existing) {
      await ctx.db.replace(existing._id, doc);
      return existing._id;
    }
    return await ctx.db.insert("sites", doc);
  },
});
