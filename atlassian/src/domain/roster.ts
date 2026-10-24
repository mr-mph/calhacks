export const SHIFT_TIME_ZONE = "America/Los_Angeles";
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;
const ACCOUNT_ID = /^[A-Za-z0-9:-]{1,128}$/;
const MAX_ROSTER = 50;

export interface RosterEntry {
  name: string;
  accountId: string;
  start: string;
  end: string;
}

const minutes = (hhmm: string): number => {
  const [h, m] = hhmm.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
};

export function localMinutes(now: Date, timeZone = SHIFT_TIME_ZONE): number {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(now);
  const get = (type: string): number => Number(parts.find((p) => p.type === type)?.value ?? 0);
  return get("hour") * 60 + get("minute");
}

// Shifts may cross midnight (22:00 to 06:00).
export function isOnShift(entry: RosterEntry, nowMinutes: number): boolean {
  const start = minutes(entry.start);
  const end = minutes(entry.end);
  if (start === end) return true;
  return start < end ? nowMinutes >= start && nowMinutes < end : nowMinutes >= start || nowMinutes < end;
}

export function onShift(roster: readonly RosterEntry[], now: Date): RosterEntry | null {
  const m = localMinutes(now);
  return roster.find((entry) => isOnShift(entry, m)) ?? null;
}

export function validateRoster(input: unknown): RosterEntry[] {
  if (!Array.isArray(input) || input.length > MAX_ROSTER) throw new Error(`Roster must be a list of at most ${MAX_ROSTER} people`);
  return input.map((raw, i) => {
    const row = (raw ?? {}) as Record<string, unknown>;
    const name = typeof row.name === "string" ? row.name.trim().slice(0, 80) : "";
    const accountId = typeof row.accountId === "string" ? row.accountId.trim() : "";
    const start = typeof row.start === "string" ? row.start.trim() : "";
    const end = typeof row.end === "string" ? row.end.trim() : "";
    if (!name) throw new Error(`Row ${i + 1}: add a name`);
    if (!ACCOUNT_ID.test(accountId)) throw new Error(`Row ${i + 1}: pick an Atlassian account`);
    if (!HHMM.test(start) || !HHMM.test(end)) throw new Error(`Row ${i + 1}: shift times use 24-hour HH:MM, like 08:00`);
    return { name, accountId, start, end };
  });
}
