import type { FunctionReturnType } from "convex/server";
import type { api } from "../../convex/_generated/api";

export type Now = FunctionReturnType<typeof api.live.now>;
export type Observation = NonNullable<Now["observation"]>;
export type Frame = NonNullable<Now["frame"]>;
export type Site = NonNullable<Now["site"]>;
export type Lot = FunctionReturnType<typeof api.live.lots>[number];
export type Decision = Lot["decisions"][number];
export type Alerts = FunctionReturnType<typeof api.live.alerts>;
export type Alert = Alerts["open"][number];

export const CONFIDENCE_MIN = 0.5;
const TILT_MAX_DEG = 15;
export const STALE_AFTER_S = 15;
export const OFFLINE_AFTER_S = 60;

export function unreliableReason(obs: Observation): string | null {
  if (obs.confidence >= CONFIDENCE_MIN) return null;
  if (!obs.aligned) return "not lined up with the lot map";
  if (obs.tilt_deg !== undefined && obs.tilt_deg > TILT_MAX_DEG) return `tilted ${Math.round(obs.tilt_deg)} degrees`;
  return "counts jumped between frames";
}

export function zonePeople(obs: Observation | null, site: Site | null, kind: "beach" | "water"): number | null {
  const ids = (site?.zones ?? []).filter((z) => z.kind === kind).map((z) => z.id);
  if (!obs || ids.length === 0) return null;
  return ids.reduce((sum, id) => sum + (obs.zones?.[id]?.person ?? 0), 0);
}

export interface LotState {
  free: number | null;
  total: number | null;
}

export function lotState(lot: Lot, obs: Observation | null): LotState {
  const spaces = obs?.aligned ? obs.spaces : undefined;
  const known = spaces ? lot.spaceIds.filter((id) => id in spaces) : [];
  if (spaces && known.length > 0) {
    return { free: known.filter((id) => !spaces[id]).length, total: known.length };
  }
  const occupancy = obs?.aligned ? obs.zones?.[lot.id]?.occupancy : undefined;
  if (occupancy !== undefined && lot.capacity) {
    const free = Math.round(lot.capacity * (1 - Math.min(1, Math.max(0, occupancy))));
    return { free, total: lot.capacity };
  }
  return { free: null, total: lot.capacity };
}

export function money(n: number): string {
  return `$${n.toFixed(2)}`;
}
