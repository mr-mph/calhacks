import { createHash, timingSafeEqual } from "node:crypto";

export const SECRET_HEADER = "x-balloon-secret";
const MIN_SECRET_LENGTH = 32;

const digest = (value: string): Buffer => createHash("sha256").update(value, "utf8").digest();

// Hashing first gives equal-length buffers, so the comparison time doesn't leak the secret's length.
export function secretMatches(given: string | undefined, expected: string | undefined): boolean {
  if (!expected || expected.length < MIN_SECRET_LENGTH || !given) return false;
  return timingSafeEqual(digest(given), digest(expected));
}

export function header(headers: Record<string, string[] | undefined>, name: string): string | undefined {
  const match = Object.entries(headers).find(([key]) => key.toLowerCase() === name);
  return match?.[1]?.[0];
}
