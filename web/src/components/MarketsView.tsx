import { ArrowSquareOut, ChartLine } from "@phosphor-icons/react";
import { EmptyState } from "./ui";

const MARKET_URL = import.meta.env.VITE_MARKET_URL as string | undefined;

function safeHttpUrl(url: string | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.toString() : null;
  } catch {
    return null;
  }
}

export function MarketsView() {
  const href = safeHttpUrl(MARKET_URL);
  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl">Markets</h1>
      <EmptyState icon={<ChartLine size={28} aria-hidden="true" />} title="Markets run on their own page">
        Bet play credits on what the camera will count, such as cars in Lot A at 5:00 PM. Markets settle from the same
        frames you see on Live.
      </EmptyState>
      {href ? (
        <a href={href} className="press inline-flex min-h-11 items-center gap-2 self-start rounded-full bg-accent px-5 text-sm font-semibold text-on-accent">
          Open markets
          <ArrowSquareOut size={16} weight="bold" aria-hidden="true" />
        </a>
      ) : (
        <p className="text-sm text-muted">The market page isn't linked yet. Set VITE_MARKET_URL when you build this app.</p>
      )}
    </div>
  );
}
