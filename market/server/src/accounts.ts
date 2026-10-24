import { SenderError, t } from 'spacetimedb/server';
import spacetimedb from './schema';
import { MIN_SECRET_LENGTH, requireText, secretsMatch } from './guards';
import { MICRO_PER_CREDIT } from './lmsr';

const STARTING_CREDITS = 1000n;
const MAX_NAME_LENGTH = 24;

export const register = spacetimedb.reducer({ name: t.string() }, (ctx, { name }) => {
  if (ctx.db.account.identity.find(ctx.sender)) throw new SenderError('already registered');
  ctx.db.account.insert({
    identity: ctx.sender,
    name: requireText(name, 'name', MAX_NAME_LENGTH),
    balanceMicro: STARTING_CREDITS * MICRO_PER_CREDIT,
    createdAt: ctx.timestamp,
  });
});

export const claimOracle = spacetimedb.reducer({ secret: t.string() }, (ctx, { secret }) => {
  const expected = ctx.env.ORACLE_SECRET;
  if (expected.length < MIN_SECRET_LENGTH) throw new SenderError('oracle secret is not configured');
  if (!secretsMatch(secret, expected)) throw new SenderError('wrong oracle secret');
  if (ctx.db.oracle.identity.find(ctx.sender)) return;
  ctx.db.oracle.insert({ identity: ctx.sender, addedAt: ctx.timestamp });
});
