import { byId, h } from './dom';
import { icon, type IconName } from './icons';

interface NavItem {
  label: string;
  icon: IconName;
  href: string | undefined;
  current?: boolean;
}

// Live view and alerts live in the map app; their URLs come from the build so this page works without them.
const ITEMS: NavItem[] = [
  { label: 'Live', icon: 'broadcast', href: import.meta.env.VITE_LIVE_URL },
  { label: 'Markets', icon: 'chartLineUp', href: './', current: true },
  { label: 'Alerts', icon: 'bell', href: import.meta.env.VITE_ALERTS_URL },
];

function navLink(item: NavItem): HTMLElement {
  const attrs: Record<string, string> = item.current ? { 'aria-current': 'page' } : {};
  if (item.href) return h('a', { class: 'nav-item', attrs: { ...attrs, href: item.href } }, icon(item.icon), item.label);
  return h('span', { class: 'nav-item', attrs: { 'aria-disabled': 'true', title: `${item.label} is not connected yet` } }, icon(item.icon), item.label);
}

export function renderNav(): void {
  for (const id of ['topnav', 'tabbar']) byId(id).replaceChildren(...ITEMS.map(navLink));
}
