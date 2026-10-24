import { ConvexError, v } from "convex/values";
import { mutation } from "./_generated/server";

export const review = mutation({
  args: {
    id: v.id("alerts"),
    decision: v.union(v.literal("confirmed"), v.literal("dismissed")),
  },
  handler: async (ctx, { id, decision }) => {
    const alert = await ctx.db.get(id);
    if (!alert) throw new ConvexError("This alert no longer exists");
    if (alert.status !== "needs_review") {
      throw new ConvexError(`Someone already marked this alert ${alert.status}`);
    }
    await ctx.db.patch(id, { status: decision, reviewedAt: Date.now() / 1000 });
  },
});
