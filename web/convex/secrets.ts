import { ConvexError } from "convex/values";

// Constant-time so response timing does not leak how much of a guess matched.
function matches(given: string, expected: string): boolean {
  let diff = given.length ^ expected.length;
  for (let i = 0; i < expected.length; i++) {
    diff |= expected.charCodeAt(i) ^ given.charCodeAt(i % Math.max(given.length, 1));
  }
  return diff === 0;
}

export function requireEnvSecret(envVar: string, given: string, message: string): void {
  const expected = process.env[envVar];
  if (!expected || !matches(given, expected)) throw new ConvexError(message);
}
