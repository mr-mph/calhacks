export const MAX_BODY_BYTES = 16_384;
const MAX_TEXT_CHARS = 2_000;
const MAX_COUNT = 10_000;
const ALERT_ID = /^[A-Za-z0-9._:-]{1,80}$/;
const ZONE = /^[a-z0-9][a-z0-9-]{0,39}$/;

export interface Alert {
  alertId: string;
  text: string;
  uncertainty: string;
  zone: string;
  personWater: number;
  personBeach: number;
  confidence: number;
  frameUrl: string | null;
  observedAt: number;
}

export type ParseResult = { ok: true; alert: Alert } | { ok: false; error: string };

type Json = Record<string, unknown>;

const isObject = (v: unknown): v is Json => typeof v === "object" && v !== null && !Array.isArray(v);

function str(v: unknown, field: string, max = MAX_TEXT_CHARS): string {
  if (typeof v !== "string" || v.trim() === "") throw new Error(`${field} must be a non-empty string`);
  return v.trim().slice(0, max);
}

function count(v: unknown, field: string): number {
  if (!Number.isInteger(v) || (v as number) < 0 || (v as number) > MAX_COUNT) {
    throw new Error(`counts.${field} must be an integer from 0 to ${MAX_COUNT}`);
  }
  return v as number;
}

function confidence(v: unknown): number {
  if (typeof v !== "number" || !Number.isFinite(v) || v < 0 || v > 1) {
    throw new Error("confidence must be a number from 0 to 1");
  }
  return v;
}

function zone(v: unknown): string {
  const z = str(v, "zone", 80).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  if (!ZONE.test(z)) throw new Error("zone must contain letters or digits (max 40)");
  return z;
}

function alertId(v: unknown): string {
  const id = str(v, "alert_id", 80);
  if (!ALERT_ID.test(id)) throw new Error("alert_id may only contain letters, digits, '.', '_', ':' and '-'");
  return id;
}

// The station posts epoch seconds; ISO strings are accepted for hand-written test alerts.
function observedAt(v: unknown): number {
  const ms = typeof v === "number" ? v * 1000 : typeof v === "string" ? Date.parse(v) : NaN;
  if (!Number.isFinite(ms) || ms <= 0) throw new Error("t must be epoch seconds or an ISO timestamp");
  return Math.round(ms);
}

export function frameUrl(v: unknown): string | null {
  if (typeof v !== "string" || v.trim() === "") return null;
  try {
    const url = new URL(v.trim());
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}

function build(body: Json): Alert {
  const counts = isObject(body.counts) ? body.counts : {};
  return {
    alertId: alertId(body.alert_id),
    text: str(body.text, "text"),
    uncertainty: typeof body.uncertainty === "string" ? body.uncertainty.trim().slice(0, MAX_TEXT_CHARS) : "",
    zone: zone(body.zone),
    personWater: count(counts.person_water ?? 0, "person_water"),
    personBeach: count(counts.person_beach ?? 0, "person_beach"),
    confidence: confidence(body.confidence),
    frameUrl: frameUrl(body.frame_url),
    observedAt: observedAt(body.t),
  };
}

export function parseAlert(raw: string): ParseResult {
  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return { ok: false, error: "body must be JSON" };
  }
  if (!isObject(body)) return { ok: false, error: "body must be a JSON object" };
  try {
    return { ok: true, alert: build(body) };
  } catch (err) {
    return { ok: false, error: (err as Error).message };
  }
}
