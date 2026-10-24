import { schema, table, t, type InferSchema, type ReducerCtx } from 'spacetimedb/server';

export const account = table(
  { name: 'account', public: true },
  {
    identity: t.identity().primaryKey(),
    name: t.string(),
    balanceMicro: t.u64(),
    createdAt: t.timestamp(),
  }
);

export const oracle = table(
  { name: 'oracle', public: true },
  {
    identity: t.identity().primaryKey(),
    addedAt: t.timestamp(),
  }
);

// poolMicro is the cash the market holds: the maker's subsidy plus every trader payment.
// Winners are paid from it; whatever is left after settlement is the maker's result.
export const market = table(
  { name: 'market', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    question: t.string(),
    zone: t.string(),
    metric: t.string(),
    comparator: t.string(),
    threshold: t.f64(),
    closeAt: t.timestamp(),
    b: t.u32(),
    qYes: t.u64(),
    qNo: t.u64(),
    status: t.string(),
    outcome: t.string(),
    settledValue: t.option(t.f64()),
    explanation: t.string(),
    subsidyMicro: t.u64(),
    poolMicro: t.u64(),
    createdBy: t.identity(),
    createdAt: t.timestamp(),
    resolvedAt: t.option(t.timestamp()),
  }
);

export const position = table(
  {
    name: 'position',
    public: true,
    indexes: [{ accessor: 'byMarketOwner', algorithm: 'btree', columns: ['marketId', 'owner'] }],
  },
  {
    id: t.u64().primaryKey().autoInc(),
    marketId: t.u64(),
    owner: t.identity(),
    yes: t.u64(),
    no: t.u64(),
    spentMicro: t.u64(),
  }
);

export const trade = table(
  { name: 'trade', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    marketId: t.u64().index('btree'),
    trader: t.identity(),
    side: t.string(),
    shares: t.u64(),
    costMicro: t.u64(),
    priceYesAfter: t.f64(),
    at: t.timestamp(),
  }
);

export const observation = table(
  { name: 'observation', public: true },
  {
    id: t.u64().primaryKey().autoInc(),
    t: t.f64(),
    zone: t.string(),
    metric: t.string(),
    value: t.f64(),
    confidence: t.f64(),
    frame: t.string(),
    postedBy: t.identity(),
    receivedAt: t.timestamp(),
  }
);

export const closeTimer = table(
  { name: 'close_timer' },
  {
    scheduledId: t.u64().primaryKey().autoInc(),
    scheduledAt: t.scheduleAt(),
    marketId: t.u64(),
  }
);

const spacetimedb = schema(
  { account, oracle, market, position, trade, observation, closeTimer },
  { env: { ORACLE_SECRET: t.string() } }
);

export default spacetimedb;

export type Ctx = ReducerCtx<InferSchema<typeof spacetimedb>>;
