import { ALERTS_URL, LIVE_URL } from './config';
import { byId, h } from './dom';
import { icon, type IconName } from './icons';

interface NavItem {
  label: string;
  icon: IconName;
  href: string;
  current?: boolean;
}

// Live view and alerts live in the map app (web/); config.ts sets its URL for each build.
const ITEMS: NavItem[] = [
  { label: 'Live', icon: 'broadcast', href: LIVE_URL },
  { label: 'Markets', icon: 'chartLineUp', href: './', current: true },
  { label: 'Alerts', icon: 'bell', href: ALERTS_URL },
];

function navLink(item: NavItem): HTMLElement {
  const attrs: Record<string, string> = item.current ? { 'aria-current': 'page' } : {};
  return h('a', { class: 'nav-item', attrs: { ...attrs, href: item.href } }, icon(item.icon), item.label);
}

export function renderNav(): void {
  for (const id of ['topnav', 'tabbar']) byId(id).replaceChildren(...ITEMS.map(navLink));
}
