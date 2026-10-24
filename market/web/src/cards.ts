import { MICRO_PER_CREDIT, priceYes, type Book, type Side } from '../../server/src/lmsr';
import { h } from './dom';
import { agoText, closesText, credits, eyebrowText, metricUnit, paysText, percent, thresholdPhrase, wholeCredits } from './format';
import { icon } from './icons';
import type { LatestObservation, Market, Position } from './module_bindings/types';
import { isTradable, marketKey, readingKey, type View } from './view';

const SETTLEMENT_MIN_CONFIDENCE = 0.5;
const SIDES: Side[] = ['yes', 'no'];

export type OpenSheet = (marketId: bigint, side: Side) => void;

export function bookOf(m: Market): Book {
  return { qYes: Number(m.qYes), qNo: Number(m.qNo), b: m.b };
}

function cardHead(m: Market, rightCaption: Node | string) {
  return h(
    'div',
    { class: 'card-head' },
    h('div', { class: 'eyebrow' }, h('span', { class: 'cat' }, eyebrowText(m.metric, m.zone)), rightCaption),
    h('h3', {}, m.question)
  );
}

function readingLine(m: Market, latest: LatestObservation | undefined, now: Date) {
  if (!latest) return h('p', { class: 'reading muted' }, 'Waiting for the first count from the balloon.');
  return h(
    'p',
    { class: 'reading' },
    h('span', { class: 'muted' }, 'Balloon sees'),
    h('strong', {}, `${Math.round(latest.value)} ${metricUnit(m.metric)}`),
    h('span', { class: 'caption' }, `Updated ${agoText(latest.t, now)}`),
    latest.confidence < SETTLEMENT_MIN_CONFIDENCE &&
      h('span', { class: 'chip-warning' }, icon('warning'), `Unreliable frame (${percent(latest.confidence)}), not used to settle`)
  );
}

function sideLabel(side: Side): string {
  return side === 'yes' ? 'Yes' : 'No';
}

function outcomeRow(side: Side, p: number, pillText: string, opts: { onPick?: () => void; pillClass?: string; pays?: string; key?: string }) {
  const children = [
    h('span', { class: 'outcome-label' }, sideLabel(side)),
    h('span', { class: 'outcome-pays' }, opts.pays ?? ''),
    h('span', { class: `pill ${opts.pillClass ?? ''}` }, pillText),
    h('span', { class: 'line', attrs: { 'aria-hidden': 'true' } }, h('span', { class: 'line-fill', attrs: { style: `display:block;width:${(p * 100).toFixed(1)}%` } })),
  ];
  if (!opts.onPick) return h('div', { class: `outcome ${side}` }, ...children);
  return h(
    'button',
    {
      class: `outcome ${side}`,
      attrs: { type: 'button', 'data-key': `pick-${opts.key}-${side}`, 'aria-label': `Buy ${sideLabel(side)}, ${percent(p)} chance, ${opts.pays}` },
      onClick: opts.onPick,
    },
    ...children
  );
}

function positionText(p: Position | undefined): string | null {
  if (!p) return null;
  const held = [p.yes > 0n && `${p.yes} Yes`, p.no > 0n && `${p.no} No`].filter(Boolean).join(' and ');
  return `You hold ${held} (paid ${credits(p.spentMicro)})`;
}

function why(label: string, text: string) {
  return text ? h('p', { class: 'why' }, h('b', {}, `${label} `), text) : null;
}

function meta(volumeMicro: bigint, mine: string | null) {
  return h(
    'p',
    { class: 'meta' },
    h('span', { class: 'num' }, `${wholeCredits(volumeMicro)} credits traded`),
    mine && h('span', { class: 'mine' }, mine)
  );
}

export function openCard(m: Market, view: View, openSheet: OpenSheet): HTMLElement {
  const p = priceYes(bookOf(m));
  const canTrade = view.account !== undefined && isTradable(m, view.now);
  const key = marketKey(m.id);
  const rows = SIDES.map(side => {
    const ps = side === 'yes' ? p : 1 - p;
    return outcomeRow(side, ps, percent(ps), { pays: paysText(ps), key, onPick: canTrade ? () => openSheet(m.id, side) : undefined });
  });
  const closedNote = !isTradable(m, view.now) && h('p', { class: 'muted' }, "Trading closed. Waiting for the balloon's count to settle.");
  const joinNote = !view.account && isTradable(m, view.now) && h('p', { class: 'muted' }, 'Pick a name above to trade.');
  const card = h(
    'article',
    { class: 'card' },
    cardHead(m, h('span', { class: 'caption' }, closesText(m.closeAt, view.now))),
    readingLine(m, view.latest.get(readingKey(m)), view.now),
    h('div', { class: 'outcomes' }, ...rows),
    h(
      'div',
      { class: 'card-foot' },
      closedNote,
      joinNote,
      meta(view.volumeMicro.get(key) ?? 0n, positionText(view.positions.get(key))),
      why('Why', m.rationale)
    )
  );
  card.dataset.market = key;
  return card;
}

function resultText(m: Market, p: Position | undefined): string | null {
  if (!p) return null;
  if (m.status === 'void') return `Refunded ${credits(p.spentMicro)}`;
  const paid = (m.outcome === 'yes' ? p.yes : p.no) * MICRO_PER_CREDIT;
  return `You were paid ${credits(paid)} (staked ${credits(p.spentMicro)})`;
}

function settledRows(m: Market) {
  if (m.status === 'void') {
    return SIDES.map(side => outcomeRow(side, 0, 'Void', { pillClass: 'pill-void' }));
  }
  return SIDES.map(side => {
    const won = m.outcome === side;
    return outcomeRow(side, won ? 1 : 0, won ? 'Won' : 'Lost', { pillClass: won ? '' : 'pill-muted' });
  });
}

export function resolvedCard(m: Market, view: View): HTMLElement {
  const key = marketKey(m.id);
  const observed =
    m.settledValue === undefined
      ? 'No reliable count, so every stake was returned.'
      : `Observed ${m.settledValue} ${metricUnit(m.metric)}. Yes needed ${thresholdPhrase(m.comparator, m.threshold, m.metric)}.`;
  return h(
    'article',
    { class: 'card' },
    cardHead(m, h('span', { class: 'caption' }, m.status === 'void' ? 'Void' : 'Settled')),
    h('div', { class: 'outcomes' }, ...settledRows(m)),
    h(
      'div',
      { class: 'card-foot' },
      h('p', {}, observed),
      meta(view.volumeMicro.get(key) ?? 0n, resultText(m, view.positions.get(key))),
      why('Why', m.explanation)
    )
  );
}
