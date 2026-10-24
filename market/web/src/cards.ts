import { buyCost, MICRO_PER_CREDIT, priceYes, toMicroCeil, type Book, type Side } from '../../server/src/lmsr';
import { h } from './dom';
import { agoText, closesText, credits, metricUnit, percent, thresholdPhrase } from './format';
import type { LatestObservation, Market, Position, Trade } from './module_bindings/types';
import { marketKey, readingKey, type View } from './view';

export const SHARE_CHOICES = [1, 10, 50, 100];
const SETTLEMENT_MIN_CONFIDENCE = 0.5;

export interface Actions {
  pickShares: (marketId: bigint, shares: number) => void;
  buy: (marketId: bigint, side: Side, shares: number) => void;
}

export interface UiState {
  shares: Map<string, number>;
  busy: boolean;
}

function bookOf(m: Market): Book {
  return { qYes: Number(m.qYes), qNo: Number(m.qNo), b: m.b };
}

function oddsMeter(p: number) {
  return h(
    'div',
    { class: 'odds' },
    h('div', { class: 'odds-labels' }, h('span', { class: 'yes' }, `YES ${percent(p)}`), h('span', { class: 'no' }, `NO ${percent(1 - p)}`)),
    h(
      'div',
      { class: 'meter', attrs: { role: 'img', 'aria-label': `Market says ${percent(p)} chance of YES` } },
      h('div', { class: 'meter-fill', attrs: { style: `width:${(p * 100).toFixed(1)}%` } })
    )
  );
}

function readingLine(m: Market, latest: LatestObservation | undefined, now: Date) {
  if (!latest) return h('p', { class: 'reading muted' }, 'No count from the balloon yet.');
  const low = latest.confidence < SETTLEMENT_MIN_CONFIDENCE;
  return h(
    'p',
    { class: 'reading' },
    'Balloon sees ',
    h('strong', {}, String(Math.round(latest.value))),
    ` ${metricUnit(m.metric)}, ${agoText(latest.t, now)}. `,
    low
      ? h('span', { class: 'low' }, `Low confidence (${percent(latest.confidence)}), not used to settle.`)
      : h('span', { class: 'muted' }, `Confidence ${percent(latest.confidence)}.`)
  );
}

function holdingLine(p: Position | undefined) {
  if (!p) return null;
  return h('p', { class: 'holding num' }, `You hold ${p.yes} YES and ${p.no} NO, paid ${credits(p.spentMicro)}`);
}

function tape(trades: Trade[] | undefined, names: Map<string, string>) {
  if (!trades?.length) return null;
  return h(
    'ul',
    { class: 'tape' },
    ...trades.map(t =>
      h('li', {}, `${names.get(t.trader.toHexString()) ?? 'someone'} bought ${t.shares} ${t.side.toUpperCase()} for ${credits(t.costMicro)}, YES now ${percent(t.priceYesAfter)}`)
    )
  );
}

function shareChips(m: Market, chosen: number, actions: Actions) {
  return h(
    'div',
    { class: 'chips', attrs: { role: 'group', 'aria-label': 'Shares to buy' } },
    h('span', { class: 'small muted' }, 'Shares'),
    ...SHARE_CHOICES.map(n =>
      h('button', {
        class: 'chip',
        attrs: { type: 'button', 'aria-pressed': String(n === chosen), 'data-key': `chip-${m.id}-${n}` },
        onClick: () => actions.pickShares(m.id, n),
      }, String(n))
    )
  );
}

function buyButton(m: Market, side: Side, shares: number, balanceMicro: bigint, ui: UiState, actions: Actions) {
  const costMicro = toMicroCeil(buyCost(bookOf(m), side, shares));
  const label = side === 'yes' ? 'Buy YES' : 'Buy NO';
  const btn = h(
    'button',
    {
      class: `btn btn-${side}`,
      attrs: { type: 'button', 'data-key': `buy-${m.id}-${side}` },
      onClick: () => actions.buy(m.id, side, shares),
    },
    label,
    h('small', {}, `${shares} for ${credits(costMicro)}`)
  );
  btn.disabled = ui.busy || costMicro > balanceMicro;
  return btn;
}

function tradeControls(m: Market, view: View, ui: UiState, actions: Actions) {
  if (!view.account) return h('p', { class: 'small muted' }, 'Join above to trade.');
  if (m.closeAt.toDate() <= view.now || m.status !== 'open') {
    return h('p', { class: 'small muted' }, "Trading closed. Waiting for the balloon's count to settle.");
  }
  const shares = ui.shares.get(marketKey(m.id)) ?? SHARE_CHOICES[1];
  const balance = view.account.balanceMicro;
  return h(
    'div',
    { class: 'stack' },
    shareChips(m, shares, actions),
    h('div', { class: 'trade-row' }, buyButton(m, 'yes', shares, balance, ui, actions), buyButton(m, 'no', shares, balance, ui, actions))
  );
}

export function openCard(m: Market, view: View, ui: UiState, actions: Actions): HTMLElement {
  return h(
    'article',
    { class: 'card' },
    h('div', { class: 'eyebrow' }, h('span', {}, m.zone), h('span', {}, closesText(m.closeAt, view.now))),
    h('h3', {}, m.question),
    h('p', { class: 'small muted' }, `YES if the balloon counts ${thresholdPhrase(m.comparator, m.threshold, m.metric)} at close.`),
    readingLine(m, view.latest.get(readingKey(m)), view.now),
    oddsMeter(priceYes(bookOf(m))),
    tradeControls(m, view, ui, actions),
    holdingLine(view.positions.get(marketKey(m.id))),
    tape(view.trades.get(marketKey(m.id)), view.names)
  );
}

function resultLine(m: Market, p: Position | undefined) {
  if (!p) return null;
  const amount = m.status === 'void' ? p.spentMicro : (m.outcome === 'yes' ? p.yes : p.no) * MICRO_PER_CREDIT;
  const verb = m.status === 'void' ? 'Refunded' : 'You were paid';
  return h('p', { class: 'holding num' }, `${verb} ${credits(amount)} (you paid ${credits(p.spentMicro)})`);
}

function outcomePill(m: Market) {
  const kind = m.status === 'void' ? 'void' : m.outcome;
  return h('span', { class: `pill pill-${kind}` }, kind.toUpperCase());
}

export function resolvedCard(m: Market, view: View): HTMLElement {
  const measured =
    m.settledValue === undefined
      ? 'No reliable count, so every stake was returned.'
      : `Balloon measured ${m.settledValue} ${metricUnit(m.metric)}. YES needed ${thresholdPhrase(m.comparator, m.threshold, m.metric)}.`;
  return h(
    'article',
    { class: 'card' },
    h('div', { class: 'eyebrow' }, h('span', {}, m.zone), outcomePill(m)),
    h('h3', {}, m.question),
    h('p', {}, measured),
    h('p', { class: 'explanation small muted' }, m.explanation),
    resultLine(m, view.positions.get(marketKey(m.id)))
  );
}
