import type { Identity } from 'spacetimedb';
import type { DbConnection } from './module_bindings';
import type { Account, LatestObservation, Market, Position, Trade } from './module_bindings/types';

export interface View {
  account: Account | undefined;
  open: Market[];
  resolved: Market[];
  positions: Map<string, Position>;
  trades: Map<string, Trade[]>;
  names: Map<string, string>;
  latest: Map<string, LatestObservation>;
  now: Date;
}

const TAPE_LENGTH = 3;

export const marketKey = (id: bigint): string => id.toString();
export const readingKey = (m: Pick<Market, 'zone' | 'metric'>): string => `${m.zone}/${m.metric}`;

function isResolved(m: Market): boolean {
  return m.status === 'settled' || m.status === 'void';
}

function micros(m: Market, field: 'closeAt' | 'resolvedAt'): bigint {
  return (field === 'closeAt' ? m.closeAt : m.resolvedAt ?? m.closeAt).microsSinceUnixEpoch;
}

function recentTradesByMarket(trades: Trade[]): Map<string, Trade[]> {
  const sorted = [...trades].sort((a, b) => Number(b.at.microsSinceUnixEpoch - a.at.microsSinceUnixEpoch));
  const out = new Map<string, Trade[]>();
  for (const t of sorted) {
    const list = out.get(marketKey(t.marketId)) ?? [];
    if (list.length < TAPE_LENGTH) out.set(marketKey(t.marketId), [...list, t]);
  }
  return out;
}

export function buildView(conn: DbConnection, me: Identity | undefined): View {
  const markets = [...conn.db.market.iter()];
  const accounts = [...conn.db.account.iter()];
  const mine = [...conn.db.position.iter()].filter(p => me !== undefined && p.owner.isEqual(me));
  return {
    account: me ? accounts.find(a => a.identity.isEqual(me)) : undefined,
    open: markets.filter(m => !isResolved(m)).sort((a, b) => Number(micros(a, 'closeAt') - micros(b, 'closeAt'))),
    resolved: markets.filter(isResolved).sort((a, b) => Number(micros(b, 'resolvedAt') - micros(a, 'resolvedAt'))),
    positions: new Map(mine.map(p => [marketKey(p.marketId), p])),
    trades: recentTradesByMarket([...conn.db.trade.iter()]),
    names: new Map(accounts.map(a => [a.identity.toHexString(), a.name])),
    latest: new Map([...conn.db.latestObservation.iter()].map(o => [readingKey(o), o])),
    now: new Date(),
  };
}
