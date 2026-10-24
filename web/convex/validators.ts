import { v } from "convex/values";

const point = v.array(v.number());
const polygon = v.array(point);

export const observationFields = {
  t: v.number(),
  session: v.string(),
  frame: v.string(),
  alt_m: v.optional(v.number()),
  tilt_deg: v.optional(v.number()),
  model: v.optional(v.string()),
  aligned: v.boolean(),
  confidence: v.number(),
  counts: v.record(v.string(), v.number()),
  zones: v.optional(v.record(v.string(), v.record(v.string(), v.number()))),
  spaces: v.optional(v.record(v.string(), v.boolean())),
  rip: v.optional(v.array(v.object({ xyxy: v.array(v.number()), conf: v.number() }))),
};

export const frameFields = {
  session: v.string(),
  t: v.number(),
  name: v.string(),
  storageId: v.id("_storage"),
  width: v.number(),
  height: v.number(),
  bytes: v.number(),
};

export const zoneKind = v.union(
  v.literal("lot"),
  v.literal("beach"),
  v.literal("water"),
  v.literal("crossing"),
  v.literal("other"),
);

export const siteFields = {
  site: v.string(),
  name: v.optional(v.string()),
  reference_frame: v.optional(v.string()),
  image_size: v.optional(v.array(v.number())),
  zones: v.array(
    v.object({
      id: v.string(),
      kind: zoneKind,
      name: v.optional(v.string()),
      polygon,
      capacity: v.optional(v.number()),
    }),
  ),
  spaces: v.array(v.object({ id: v.string(), zone: v.string(), polygon })),
};

export const priceFields = {
  zone: v.string(),
  price: v.number(),
  t: v.number(),
  unit: v.optional(v.string()),
};

export const decisionFields = {
  t: v.number(),
  zone: v.string(),
  action: v.union(v.literal("raise"), v.literal("lower"), v.literal("hold")),
  price_before: v.optional(v.number()),
  price_after: v.number(),
  inputs: v.record(v.string(), v.union(v.number(), v.string(), v.boolean(), v.null())),
  outputs: v.optional(v.record(v.string(), v.union(v.number(), v.string(), v.boolean(), v.null()))),
  explanation: v.string(),
  model: v.optional(v.string()),
};

export const severity = v.union(v.literal("info"), v.literal("warning"), v.literal("critical"));

export const alertStatus = v.union(
  v.literal("needs_review"),
  v.literal("confirmed"),
  v.literal("dismissed"),
);

export const alertInputFields = {
  t: v.number(),
  session: v.optional(v.string()),
  text: v.string(),
  uncertainty: v.string(),
  severity: v.optional(severity),
  frame: v.optional(v.string()),
  model: v.optional(v.string()),
  zone: v.optional(v.string()),
  confidence: v.optional(v.number()),
  counts: v.optional(v.object({ person_water: v.number(), person_beach: v.number() })),
};

// After this long in "sending" the send is presumed lost and the patrol can retry it.
export const JIRA_STALLED_AFTER_S = 90;

export const jiraStatus = v.union(v.literal("sending"), v.literal("sent"), v.literal("failed"));

// Where a confirmed alert stands in the patrol's Jira (Balloon Patrol web trigger, atlassian/README.md).
export const jiraFields = v.object({
  status: jiraStatus,
  attempts: v.number(),
  updatedAt: v.number(),
  outcome: v.optional(v.string()),
  issueKey: v.optional(v.string()),
  reason: v.optional(v.string()),
  error: v.optional(v.string()),
});
