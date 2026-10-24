import { buyCost, MAX_SHARES_PER_TRADE, MICRO_PER_CREDIT, priceYes, toMicroCeil, type Book, type Side } from '../../server/src/lmsr';
import { bookOf } from './cards';
import { byId, h } from './dom';
import { credits, eyebrowText, percent } from './format';
import { icon } from './icons';
import type { Market } from './module_bindings/types';
import { isTradable, marketKey, type View } from './view';

export interface SheetDeps {
  buy: (marketId: bigint, side: Side, shares: number) => Promise<boolean>;
}

interface Quote {
  shares: number;
  costMicro: bigint;
}

// Largest whole number of shares whose cost fits the budget; cost grows with shares, so bisect.
function quoteFor(book: Book, side: Side, budgetMicro: bigint): Quote {
  let lo = 0;
  let hi = MAX_SHARES_PER_TRADE;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (toMicroCeil(buyCost(book, side, mid)) <= budgetMicro) lo = mid;
    else hi = mid - 1;
  }
  return { shares: lo, costMicro: lo === 0 ? 0n : toMicroCeil(buyCost(book, side, lo)) };
}

function parseAmountMicro(raw: string): bigint {
  const value = Number.parseFloat(raw.replace(',', '.'));
  return Number.isFinite(value) && value > 0 ? BigInt(Math.floor(value * Number(MICRO_PER_CREDIT))) : 0n;
}

const label = (side: Side): string => (side === 'yes' ? 'Yes' : 'No');

export function createSheet(deps: SheetDeps) {
  const dialog = byId<HTMLDialogElement>('sheet');
  const amount = byId<HTMLInputElement>('amount');
  const submit = byId<HTMLButtonElement>('sheet-buy');
  const toggles = [...dialog.querySelectorAll<HTMLButtonElement>('[data-side]')];
  let marketId: bigint | undefined;
  let side: Side = 'yes';
  let view: View | undefined;
  let busy = false;

  byId('sheet-close').append(icon('x'));

  function quoteRows(q: Quote): HTMLElement[] {
    const payout = BigInt(q.shares) * MICRO_PER_CREDIT;
    const row = (term: string, detail: string, cls = '') => [h('dt', {}, term), h('dd', { class: cls }, detail)];
    return [
      ...row('Shares', String(q.shares)),
      ...row('Avg price', q.shares ? credits(q.costMicro / BigInt(q.shares)) : '-'),
      ...row(`Payout if ${label(side)}`, credits(payout)),
      ...row('Profit if right', `+${credits(payout - q.costMicro)}`, 'gain'),
    ];
  }

  function blockedReason(m: Market, budget: bigint, q: Quote): string | null {
    if (!view?.account) return 'Pick a name first';
    if (!isTradable(m, view.now)) return 'Trading closed';
    if (budget === 0n) return 'Enter an amount';
    if (budget > view.account.balanceMicro) return 'Not enough credits';
    if (q.shares === 0) return 'Too small for 1 share';
    return null;
  }

  function refresh(next?: View): void {
    view = next ?? view;
    const m = marketId === undefined ? undefined : view?.markets.get(marketKey(marketId));
    if (!dialog.open || !m) return;
    const book = bookOf(m);
    const p = priceYes(book);
    byId('sheet-eyebrow').textContent = eyebrowText(m.metric, m.zone);
    byId('sheet-title').textContent = m.question;
    for (const t of toggles) {
      const s = t.dataset.side as Side;
      t.setAttribute('aria-pressed', String(s === side));
      t.textContent = `${label(s)} ${percent(s === 'yes' ? p : 1 - p)}`;
    }
    const budget = parseAmountMicro(amount.value);
    const q = quoteFor(book, side, budget);
    byId('quote').replaceChildren(...quoteRows(q));
    const reason = blockedReason(m, budget, q);
    submit.textContent = reason ?? `Buy ${label(side)} for ${credits(q.costMicro)}`;
    submit.disabled = busy || reason !== null;
  }

  async function onSubmit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const m = marketId === undefined ? undefined : view?.markets.get(marketKey(marketId));
    if (!m || submit.disabled) return;
    const q = quoteFor(bookOf(m), side, parseAmountMicro(amount.value));
    busy = true;
    refresh();
    const ok = await deps.buy(m.id, side, q.shares);
    busy = false;
    if (ok) dialog.close();
    else refresh();
  }

  for (const t of toggles) {
    t.addEventListener('click', () => {
      side = t.dataset.side as Side;
      refresh();
    });
  }
  for (const b of dialog.querySelectorAll<HTMLButtonElement>('[data-add]')) {
    b.addEventListener('click', () => {
      const current = Number.parseFloat(amount.value) || 0;
      amount.value = String(current + Number(b.dataset.add));
      refresh();
    });
  }
  amount.addEventListener('input', () => refresh());
  byId('sheet-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', e => e.target === dialog && dialog.close());
  byId<HTMLFormElement>('sheet-form').addEventListener('submit', e => void onSubmit(e));

  return {
    open(id: bigint, pick: Side, current: View): void {
      marketId = id;
      side = pick;
      dialog.showModal();
      refresh(current);
      amount.focus();
      amount.select();
    },
    refresh,
  };
}
