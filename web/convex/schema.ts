import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";
import {
  alertInputFields,
  alertStatus,
  decisionFields,
  frameFields,
  jiraFields,
  observationFields,
  priceFields,
  siteFields,
} from "./validators";

export default defineSchema({
  observations: defineTable(observationFields)
    .index("by_t", ["t"])
    .index("by_session_t", ["session", "t"]),

  frames: defineTable({ ...frameFields, pinned: v.boolean() })
    .index("by_t", ["t"])
    .index("by_session_t", ["session", "t"])
    .index("by_name", ["name"])
    .index("by_pinned_t", ["pinned", "t"]),

  sites: defineTable({ ...siteFields, updatedAt: v.number() })
    .index("by_site", ["site"])
    .index("by_updated", ["updatedAt"]),

  prices: defineTable(priceFields).index("by_zone_t", ["zone", "t"]),

  decisions: defineTable(decisionFields)
    .index("by_t", ["t"])
    .index("by_zone_t", ["zone", "t"]),

  alerts: defineTable({
    ...alertInputFields,
    status: alertStatus,
    frameId: v.optional(v.id("frames")),
    reviewedAt: v.optional(v.number()),
    jira: v.optional(jiraFields),
  })
    .index("by_t", ["t"])
    .index("by_status_t", ["status", "t"]),
});
