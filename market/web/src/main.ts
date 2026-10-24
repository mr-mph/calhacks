import type { Side } from '../../server/src/lmsr';
import { openCard, resolvedCard, type Actions, type UiState } from './cards';
import { connect } from './connection';
import { byId, h } from './dom';
import { credits, errorText } from './format';
import type { DbConnection } from './module_bindings';
import { buildView, marketKey, type View } from './view';

const CLOCK_TICK_MS = 15_000;
const TOAST_MS = 3500;

const ui: UiState = { shares: new Map(), busy: false };
let conn: DbConnection | undefined;
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

async function runReducer(call: () => Promise<void>, done: string): Promise<void> {
  ui.busy = true;
  scheduleRender();
  try {
    await call();
    toast(done);
  } catch (error: unknown) {
    toast(errorText(error), 'error');
  } finally {
    ui.busy = false;
    scheduleRender();
  }
}

const actions: Actions = {
  pickShares(marketId, shares) {
    ui.shares.set(marketKey(marketId), shares);
    scheduleRender();
  },
  buy(marketId, side: Side, shares) {
    if (!conn) return;
    const c = conn;
    void runReducer(
      () => c.reducers.buy({ marketId, side, shares: BigInt(shares) }),
      `Bought ${shares} ${side.toUpperCase()}`
    );
  },
};

function renderWallet(view: View): void {
  const wallet = byId('wallet');
  wallet.replaceChildren(
    ...(view.account
      ? [h('span', { class: 'muted' }, view.account.name), h('span', { class: 'num' }, `${credits(view.account.balanceMicro)} credits`)]
      : [])
  );
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
  renderWallet(view);
  renderList('open', view.open.map(m => openCard(m, view, ui, actions)), 'No open markets right now.');
  renderList('resolved', view.resolved.map(m => resolvedCard(m, view)), 'Nothing resolved yet.');
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
    if (!conn || !name) return;
    const c = conn;
    void runReducer(() => c.reducers.register({ name }), `Welcome, ${name}. You have 1000 credits.`);
  });
}

function setLink(state: 'live' | 'down'): void {
  byId('live').dataset.state = state;
  if (state === 'down') toast('Lost the connection. Reconnecting.', 'error');
}

wireRegister();
conn = connect({
  onReady: scheduleRender,
  onLinkChange: setLink,
});
watchTables(conn);
window.setInterval(scheduleRender, CLOCK_TICK_MS);
