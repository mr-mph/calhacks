import type { Identity } from 'spacetimedb';
import { SenderError, t } from 'spacetimedb/server';
import spacetimedb, { type Ctx } from './schema';
import { requireFinite, requireMarket, requireOracle, requireText } from './guards';
import { MICRO_PER_CREDIT } from './lmsr';

const MAX_EXPLANATION_LENGTH = 1000;
const MAX_CLOCK_SKEW_SECONDS = 60;

export const postObservation = spacetimedb.reducer(
  {
    t: t.f64(),
    zone: t.string(),
    metric: t.string(),
    value: t.f64(),
    confidence: t.f64(),
    frame: t.string(),
  },
  (ctx, args) => {
    requireOracle(ctx);
    const confidence = requireFinite(args.confidence, 'confidence');
    const nowSeconds = Number(ctx.timestamp.microsSinceUnixEpoch) / 1_000_000;
    if (requireFinite(args.t, 't') > nowSeconds + MAX_CLOCK_SKEW_SECONDS) {
      throw new SenderError('t is in the future; check the station clock');
    }
    if (confidence < 0 || confidence > 1) throw new SenderError('confidence must be 0 to 1');
    const row = ctx.db.observation.insert({
      id: 0n,
      t: args.t,
      zone: requireText(args.zone, 'zone', 64),
      metric: requireText(args.metric, 'metric', 64),
      value: requireFinite(args.value, 'value'),
      confidence,
      frame: args.frame.slice(0, 256),
      postedBy: ctx.sender,
      receivedAt: ctx.timestamp,
    });
    const latest = {
      key: `${row.zone}/${row.metric}`,
      observationId: row.id,
      t: row.t,
      zone: row.zone,
      metric: row.metric,
      value: row.value,
      confidence: row.confidence,
      frame: row.frame,
    };
    const previous = ctx.db.latestObservation.key.find(latest.key);
    if (!previous) ctx.db.latestObservation.insert(latest);
    else if (previous.t <= latest.t) ctx.db.latestObservation.key.update(latest);
  }
);

function resolvesYes(value: number, comparator: string, threshold: number): boolean {
  switch (comparator) {
    case '>=': return value >= threshold;
    case '>': return value > threshold;
    case '<=': return value <= threshold;
    case '<': return value < threshold;
    default: throw new SenderError(`unknown comparator ${comparator}`);
  }
}

function credit(ctx: Ctx, owner: Identity, amountMicro: bigint): void {
  if (amountMicro === 0n) return;
  const holder = ctx.db.account.identity.find(owner);
  if (!holder) throw new SenderError('position without an account');
  ctx.db.account.identity.update({ ...holder, balanceMicro: holder.balanceMicro + amountMicro });
}

// Pays every position in the market; returns the total paid so the pool can be debited once.
function payOut(ctx: Ctx, marketId: bigint, amountFor: (p: { yes: bigint; no: bigint; spentMicro: bigint }) => bigint): bigint {
  let total = 0n;
  for (const p of [...ctx.db.position.byMarketOwner.filter(marketId)]) {
    const amount = amountFor(p);
    credit(ctx, p.owner, amount);
    total += amount;
  }
  return total;
}

function requireUnresolved(status: string): void {
  if (status === 'settled' || status === 'void') throw new SenderError(`market is already ${status}`);
}

export const settle = spacetimedb.reducer(
  { marketId: t.u64(), value: t.f64(), explanation: t.string() },
  (ctx, { marketId, value, explanation }) => {
    requireOracle(ctx);
    const row = requireMarket(ctx, marketId);
    requireUnresolved(row.status);
    if (ctx.timestamp.microsSinceUnixEpoch < row.closeAt.microsSinceUnixEpoch) {
      throw new SenderError('market has not closed yet');
    }
    const why = requireText(explanation, 'explanation', MAX_EXPLANATION_LENGTH);
    const yesWins = resolvesYes(requireFinite(value, 'value'), row.comparator, row.threshold);
    const paid = payOut(ctx, marketId, p => (yesWins ? p.yes : p.no) * MICRO_PER_CREDIT);
    // LMSR bounds the maker's loss by the subsidy, so this only fires if that invariant broke.
    if (paid > row.poolMicro) throw new SenderError('payout exceeds pool; refusing to settle');
    ctx.db.market.id.update({
      ...row,
      status: 'settled',
      outcome: yesWins ? 'yes' : 'no',
      settledValue: value,
      explanation: why,
      poolMicro: row.poolMicro - paid,
      resolvedAt: ctx.timestamp,
    });
  }
);

export const voidMarket = spacetimedb.reducer(
  { marketId: t.u64(), reason: t.string() },
  (ctx, { marketId, reason }) => {
    requireOracle(ctx);
    const row = requireMarket(ctx, marketId);
    requireUnresolved(row.status);
    const why = requireText(reason, 'reason', MAX_EXPLANATION_LENGTH);
    const refunded = payOut(ctx, marketId, p => p.spentMicro);
    ctx.db.market.id.update({
      ...row,
      status: 'void',
      explanation: why,
      poolMicro: row.poolMicro - refunded,
      resolvedAt: ctx.timestamp,
    });
  }
);
