import { ScheduleAt, Timestamp } from 'spacetimedb';
import { SenderError, t } from 'spacetimedb/server';
import spacetimedb, { closeTimer, type Ctx } from './schema';
import { requireAccount, requireFinite, requireMarket, requireOracle, requireText } from './guards';
import { afterBuy, buyCost, MAX_SHARES_PER_TRADE, maxSubsidy, priceYes, toMicroCeil, type Book, type Side } from './lmsr';

const COMPARATORS = ['>=', '>', '<=', '<'];
const MIN_B = 10;
const MAX_B = 10_000;
const MICROS_PER_SECOND = 1_000_000;
const MAX_MARKET_LIFETIME_SECONDS = 7 * 24 * 3600;

function bookOf(row: { qYes: bigint; qNo: bigint; b: number }): Book {
  return { qYes: Number(row.qYes), qNo: Number(row.qNo), b: row.b };
}

function parseSide(side: string): Side {
  if (side !== 'yes' && side !== 'no') throw new SenderError("side must be 'yes' or 'no'");
  return side;
}

function closeTimestamp(ctx: Ctx, seconds: number): Timestamp {
  const nowSeconds = Number(ctx.timestamp.microsSinceUnixEpoch) / MICROS_PER_SECOND;
  const at = requireFinite(seconds, 'close_at');
  if (at <= nowSeconds) throw new SenderError('close_at must be in the future');
  if (at > nowSeconds + MAX_MARKET_LIFETIME_SECONDS) throw new SenderError('close_at must be within 7 days');
  return new Timestamp(BigInt(Math.round(at * MICROS_PER_SECOND)));
}

export const createMarket = spacetimedb.reducer(
  {
    question: t.string(),
    zone: t.string(),
    metric: t.string(),
    comparator: t.string(),
    threshold: t.f64(),
    closeAtUnix: t.f64(),
    b: t.u32(),
    rationale: t.string(),
  },
  (ctx, args) => {
    requireOracle(ctx);
    if (!COMPARATORS.includes(args.comparator)) {
      throw new SenderError(`comparator must be one of ${COMPARATORS.join(' ')}`);
    }
    if (args.b < MIN_B || args.b > MAX_B) throw new SenderError(`b must be ${MIN_B} to ${MAX_B}`);
    const closeAt = closeTimestamp(ctx, args.closeAtUnix);
    const subsidyMicro = toMicroCeil(maxSubsidy(args.b));
    const row = ctx.db.market.insert({
      id: 0n,
      question: requireText(args.question, 'question', 200),
      zone: requireText(args.zone, 'zone', 64),
      metric: requireText(args.metric, 'metric', 64),
      comparator: args.comparator,
      threshold: requireFinite(args.threshold, 'threshold'),
      closeAt,
      b: args.b,
      qYes: 0n,
      qNo: 0n,
      status: 'open',
      outcome: '',
      settledValue: undefined,
      explanation: '',
      subsidyMicro,
      poolMicro: subsidyMicro,
      createdBy: ctx.sender,
      createdAt: ctx.timestamp,
      resolvedAt: undefined,
      rationale: requireText(args.rationale, 'rationale', 300),
    });
    ctx.db.closeTimer.insert({
      scheduledId: 0n,
      scheduledAt: ScheduleAt.time(closeAt.microsSinceUnixEpoch),
      marketId: row.id,
    });
  }
);

export const closeMarket = spacetimedb.reducer(
  { onSchedule: closeTimer },
  { timer: closeTimer.rowType },
  (ctx, { timer }) => {
    const row = ctx.db.market.id.find(timer.marketId);
    if (!row || row.status !== 'open') return;
    ctx.db.market.id.update({ ...row, status: 'closed' });
  }
);

function addToPosition(ctx: Ctx, marketId: bigint, side: Side, shares: bigint, costMicro: bigint): void {
  const existing = [...ctx.db.position.byMarketOwner.filter([marketId, ctx.sender])][0];
  const base = existing ?? { id: 0n, marketId, owner: ctx.sender, yes: 0n, no: 0n, spentMicro: 0n };
  const next = {
    ...base,
    yes: side === 'yes' ? base.yes + shares : base.yes,
    no: side === 'no' ? base.no + shares : base.no,
    spentMicro: base.spentMicro + costMicro,
  };
  if (existing) ctx.db.position.id.update(next);
  else ctx.db.position.insert(next);
}

export const buy = spacetimedb.reducer(
  { marketId: t.u64(), side: t.string(), shares: t.u64() },
  (ctx, { marketId, side, shares }) => {
    // Oracles report the value that settles markets, so they may not hold positions in them.
    if (ctx.db.oracle.identity.find(ctx.sender)) throw new SenderError('oracles cannot trade');
    const buyer = requireAccount(ctx);
    const row = requireMarket(ctx, marketId);
    const chosen = parseSide(side);
    if (row.status !== 'open') throw new SenderError(`market is ${row.status}`);
    if (ctx.timestamp.microsSinceUnixEpoch >= row.closeAt.microsSinceUnixEpoch) {
      throw new SenderError('market has closed');
    }
    if (shares < 1n || shares > BigInt(MAX_SHARES_PER_TRADE)) {
      throw new SenderError(`shares must be 1 to ${MAX_SHARES_PER_TRADE}`);
    }
    const book = bookOf(row);
    const costMicro = toMicroCeil(buyCost(book, chosen, Number(shares)));
    if (costMicro > buyer.balanceMicro) throw new SenderError('not enough credits');

    const next = afterBuy(book, chosen, Number(shares));
    ctx.db.account.identity.update({ ...buyer, balanceMicro: buyer.balanceMicro - costMicro });
    ctx.db.market.id.update({
      ...row,
      qYes: BigInt(next.qYes),
      qNo: BigInt(next.qNo),
      poolMicro: row.poolMicro + costMicro,
    });
    addToPosition(ctx, marketId, chosen, shares, costMicro);
    ctx.db.trade.insert({
      id: 0n,
      marketId,
      trader: ctx.sender,
      side: chosen,
      shares,
      costMicro,
      priceYesAfter: priceYes(next),
      at: ctx.timestamp,
    });
  }
);
