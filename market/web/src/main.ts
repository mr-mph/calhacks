import '@fontsource/manrope/400.css';
import '@fontsource/manrope/600.css';
import '@fontsource/manrope/700.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import '@fontsource/charis-sil/400.css';
import '@fontsource/charis-sil/700.css';
import './style.css';
import type { Side } from '../../server/src/lmsr';
import { openCard, resolvedCard } from './cards';
import { connect } from './connection';
import { byId, h } from './dom';
import { credits, errorText } from './format';
import type { DbConnection } from './module_bindings';
import { renderNav } from './nav';
import { createSheet } from './sheet';
import { buildView, type View } from './view';

const CLOCK_TICK_MS = 15_000;
const TOAST_MS = 3500;

let conn: DbConnection | undefined;
let lastView: View | undefined;
let toastTimer: number | undefined;
let frame = 0;

function toast(message: string, kind: 'info' | 'error' = 'info'): void {
  const el = byId('toast');
  el.textContent = message;
  el.dataset.kind = kind;
  el.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (el.hidden = true), TOAST_MS);
}

async function runReducer(call: () => Promise<void>, done: string): Promise<boolean> {
  try {
    await call();
    toast(done);
    return true;
  } catch (error: unknown) {
    toast(errorText(error), 'error');
    return false;
  }
}

const sheet = createSheet({
  buy: (marketId: bigint, side: Side, shares: number) => {
    const c = conn;
    if (!c) return Promise.resolve(false);
    return runReducer(
      () => c.reducers.buy({ marketId, side, shares: BigInt(shares) }),
      `Bought ${shares} ${side === 'yes' ? 'Yes' : 'No'}`
    );
  },
});

function openSheet(marketId: bigint, side: Side): void {
  if (lastView) sheet.open(marketId, side, lastView);
}

function renderWallet(view: View): void {
  const wallet = byId('wallet');
  wallet.hidden = !view.account;
  if (view.account) {
    wallet.replaceChildren(h('span', { class: 'caption' }, view.account.name), h('span', { class: 'num' }, credits(view.account.balanceMicro)));
  }
  byId('register').hidden = view.account !== undefined;
}

function renderList(id: string, cards: HTMLElement[], empty: string): void {
  byId(id).replaceChildren(...(cards.length ? cards : [h('p', { class: 'empty' }, empty)]));
}

// Rebuilding the lists drops focus, so put it back on the control with the same data-key.
function render(): void {
  frame = 0;
  if (!conn) return;
  const focusedKey = document.activeElement?.getAttribute('data-key');
  const view = buildView(conn, conn.identity);
  lastView = view;
  renderWallet(view);
  renderList('open', view.open.map(m => openCard(m, view, openSheet)), 'No open markets right now. New ones open as the balloon starts counting.');
  renderList('resolved', view.resolved.map(m => resolvedCard(m, view)), 'Nothing settled yet.');
  byId('status-text').textContent = `Live · ${view.open.length} open`;
  sheet.refresh(view);
  if (focusedKey) document.querySelector<HTMLElement>(`[data-key="${focusedKey}"]`)?.focus();
}

function scheduleRender(): void {
  if (frame === 0) frame = requestAnimationFrame(render);
}

function watchTables(c: DbConnection): void {
  for (const table of [c.db.market, c.db.account, c.db.position, c.db.trade, c.db.latestObservation]) {
    table.onInsert(scheduleRender);
    table.onDelete(scheduleRender);
  }
  c.db.market.onUpdate(scheduleRender);
  c.db.account.onUpdate(scheduleRender);
  c.db.position.onUpdate(scheduleRender);
  c.db.latestObservation.onUpdate(scheduleRender);
}

function wireRegister(): void {
  byId<HTMLFormElement>('register').addEventListener('submit', event => {
    event.preventDefault();
    const name = byId<HTMLInputElement>('name').value.trim();
    const c = conn;
    if (!c || !name) return;
    void runReducer(() => c.reducers.register({ name }), `Welcome, ${name}. You have 1000 credits.`);
  });
}

function setLink(state: 'live' | 'down'): void {
  byId('live').dataset.state = state;
  if (state === 'down') {
    byId('status-text').textContent = 'Offline · reconnecting';
    toast('Lost the connection. Reconnecting.', 'error');
  }
}

renderNav();
wireRegister();
conn = connect({ onReady: scheduleRender, onLinkChange: setLink });
watchTables(conn);
window.setInterval(scheduleRender, CLOCK_TICK_MS);
