import { useState } from "react";
import { BellSimple, ChartLine, MapTrifold, Moon, Sun } from "@phosphor-icons/react";
import { MARKET_URL } from "../config";

export type Tab = "live" | "alerts";

// Markets is the other app (market/web); Live and Alerts are hash routes in this one.
// Hidden for now (SHOW_MARKETS); flip to true to bring the tab back.
const SHOW_MARKETS = false;
const TABS: { id: Tab | "markets"; label: string; icon: typeof MapTrifold; href: string }[] = [
  { id: "live", label: "Live", icon: MapTrifold, href: "#/live" },
  ...(SHOW_MARKETS ? [{ id: "markets" as const, label: "Markets", icon: ChartLine, href: MARKET_URL }] : []),
  { id: "alerts", label: "Alerts", icon: BellSimple, href: "#/alerts" },
];

type Props = {
  tab: Tab;
  openAlerts: number;
};

function Badge({ n }: { n: number }) {
  if (n === 0) return null;
  return (
    <span className="nums rounded-full bg-critical px-1.5 text-[11px] leading-[18px] font-bold text-white">
      {n}
      <span className="sr-only"> need review</span>
    </span>
  );
}

function ThemeToggle() {
  const [isLight, setIsLight] = useState(() => document.documentElement.dataset.theme === "light");
  function handleToggle() {
    const next = isLight ? "dark" : "light";
    const root = document.documentElement;
    root.classList.add("theme-switching");
    root.dataset.theme = next;
    requestAnimationFrame(() => root.classList.remove("theme-switching"));
    try {
      localStorage.setItem("overhead-theme", next);
    } catch {
      // private mode: theme just won't persist
    }
    setIsLight(!isLight);
  }
  const Icon = isLight ? Moon : Sun;
  return (
    <button
      type="button"
      onClick={handleToggle}
      className="press grid size-11 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-text"
      aria-label={isLight ? "Switch to dark mode" : "Switch to light mode"}
    >
      <Icon size={20} aria-hidden="true" />
    </button>
  );
}

export function TopBar({ tab, openAlerts }: Props) {
  return (
    <header className="sticky top-0 z-20 bg-bg pt-[env(safe-area-inset-top)] shadow-[0_1px_0_var(--hairline)]">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-4">
        <a href="#/live" className="font-display text-xl font-bold">
          Overhead<span className="text-accent">.</span>
        </a>
        <nav aria-label="Sections" className="hidden items-center gap-1 md:flex">
          {TABS.map(({ id, label, href }) => (
            <a
              key={id}
              href={href}
              aria-current={tab === id ? "page" : undefined}
              className="press flex min-h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold text-muted hover:text-text aria-[current=page]:bg-surface-2 aria-[current=page]:text-text"
            >
              {label}
              {id === "alerts" && <Badge n={openAlerts} />}
            </a>
          ))}
        </nav>
        <ThemeToggle />
      </div>
    </header>
  );
}

export function BottomTabs({ tab, openAlerts }: Props) {
  return (
    <nav aria-label="Sections" className="fixed inset-x-0 bottom-0 z-20 bg-surface pb-[env(safe-area-inset-bottom)] shadow-[0_-1px_0_var(--hairline)] md:hidden">
      <ul className="grid grid-cols-3">
        {TABS.map(({ id, label, icon: Icon, href }) => (
          <li key={id}>
            <a
              href={href}
              aria-current={tab === id ? "page" : undefined}
              className="flex min-h-14 flex-col items-center justify-center gap-0.5 text-xs font-semibold text-muted aria-[current=page]:text-text"
            >
              <span className="relative">
                <Icon size={22} weight={tab === id ? "fill" : "regular"} aria-hidden="true" />
                {id === "alerts" && openAlerts > 0 && (
                  <span className="absolute -top-1 -right-3">
                    <Badge n={openAlerts} />
                  </span>
                )}
              </span>
              {label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
