import type { Identity } from 'spacetimedb';
import type { DbConnection } from './module_bindings';
import type { Account, LatestObservation, Market, Position, Trade } from './module_bindings/types';

export interface View {
  account: Account | undefined;
  markets: Map<string, Market>;
  open: Market[];
  resolved: Market[];
  positions: Map<string, Position>;
  volumeMicro: Map<string, bigint>;
  latest: Map<string, LatestObservation>;
  now: Date;
}

export const marketKey = (id: bigint): string => id.toString();
export const readingKey = (m: Pick<Market, 'zone' | 'metric'>): string => `${m.zone}/${m.metric}`;

function isResolved(m: Market): boolean {
  return m.status === 'settled' || m.status === 'void';
}

function byClose(a: Market, b: Market): number {
  return Number(a.closeAt.microsSinceUnixEpoch - b.closeAt.microsSinceUnixEpoch);
}

function byResolvedDesc(a: Market, b: Market): number {
  const at = (m: Market) => (m.resolvedAt ?? m.closeAt).microsSinceUnixEpoch;
  return Number(at(b) - at(a));
}

function volumes(trades: Iterable<Trade>): Map<string, bigint> {
  const out = new Map<string, bigint>();
  for (const t of trades) {
    const key = marketKey(t.marketId);
    out.set(key, (out.get(key) ?? 0n) + t.costMicro);
  }
  return out;
}

export function buildView(conn: DbConnection, me: Identity | undefined): View {
  const markets = [...conn.db.market.iter()];
  const mine = [...conn.db.position.iter()].filter(p => me !== undefined && p.owner.isEqual(me));
  return {
    account: me ? [...conn.db.account.iter()].find(a => a.identity.isEqual(me)) : undefined,
    markets: new Map(markets.map(m => [marketKey(m.id), m])),
    open: markets.filter(m => !isResolved(m)).sort(byClose),
    resolved: markets.filter(isResolved).sort(byResolvedDesc),
    positions: new Map(mine.map(p => [marketKey(p.marketId), p])),
    volumeMicro: volumes(conn.db.trade.iter()),
    latest: new Map([...conn.db.latestObservation.iter()].map(o => [readingKey(o), o])),
    now: new Date(),
  };
}

export function isTradable(m: Market, now: Date): boolean {
  return m.status === 'open' && m.closeAt.toDate() > now;
}
