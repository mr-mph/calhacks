import { SenderError } from 'spacetimedb/server';
import type { Ctx } from './schema';

export const MIN_SECRET_LENGTH = 24;

export function requireOracle(ctx: Ctx): void {
  if (!ctx.db.oracle.identity.find(ctx.sender)) throw new SenderError('only an oracle can do this');
}

export function requireAccount(ctx: Ctx) {
  const row = ctx.db.account.identity.find(ctx.sender);
  if (!row) throw new SenderError('register a name first');
  return row;
}

export function requireMarket(ctx: Ctx, marketId: bigint) {
  const row = ctx.db.market.id.find(marketId);
  if (!row) throw new SenderError(`market ${marketId} does not exist`);
  return row;
}

export function requireText(value: string, field: string, maxLength: number): string {
  const trimmed = value.trim();
  if (trimmed.length === 0 || trimmed.length > maxLength) {
    throw new SenderError(`${field} must be 1 to ${maxLength} characters`);
  }
  return trimmed;
}

export function requireFinite(value: number, field: string): number {
  if (!Number.isFinite(value)) throw new SenderError(`${field} must be a finite number`);
  return value;
}

// Constant-time so response timing does not leak how much of a guessed secret matched.
export function secretsMatch(given: string, expected: string): boolean {
  if (given.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= given.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}
