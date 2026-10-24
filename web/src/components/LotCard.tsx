import { useState } from "react";
import { CaretDown, TrendDown, TrendUp, Pause } from "@phosphor-icons/react";
import type { Decision, Lot, LotState } from "../lib/data";
import { money } from "../lib/data";
import { clock } from "../lib/time";
import { Caption, Card, Chip } from "./ui";

type Props = {
  lot: Lot;
  state: LotState;
  isUnreliable: boolean;
};

const SPARK_W = 120;
const DECISIONS_SHOWN = 5;
const SPARK_H = 36;

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const xy = values.map((v, i) => [(i / (values.length - 1)) * SPARK_W, SPARK_H - 3 - ((v - lo) / span) * (SPARK_H - 6)] as const);
  const last = xy[xy.length - 1]!;
  return (
    <svg width={SPARK_W} height={SPARK_H} viewBox={`0 0 ${SPARK_W} ${SPARK_H}`} className="overflow-visible" role="img" aria-label={`Price history, ${values.length} points, ${money(lo)} to ${money(hi)}`}>
      <polyline points={xy.map(([x, y]) => `${x},${y}`).join(" ")} fill="none" stroke="var(--text-muted)" strokeWidth={1.5} strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r={3} fill="var(--text)" />
    </svg>
  );
}

const ACTION: Record<Decision["action"], { label: string; icon: typeof TrendUp }> = {
  raise: { label: "Raised", icon: TrendUp },
  lower: { label: "Lowered", icon: TrendDown },
  hold: { label: "Held", icon: Pause },
};

function DecisionRow({ d }: { d: Decision }) {
  const { label, icon: Icon } = ACTION[d.action];
  const inputs = Object.entries(d.inputs).filter(([, v]) => v !== null);
  return (
    <li className="flex flex-col gap-2 rounded-[8px] bg-surface-2 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-semibold">
          <Icon size={16} aria-hidden="true" />
          {label}
          <span className="nums font-normal text-muted">
            {d.price_before !== undefined && d.price_before !== d.price_after ? `${money(d.price_before)} to ` : ""}
            {money(d.price_after)}
          </span>
        </span>
        <Caption>{clock(d.t)}</Caption>
      </div>
      <p className="max-w-[65ch] text-sm">{d.explanation}</p>
      {inputs.length > 0 && (
        <dl className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-muted">
          {inputs.map(([k, v]) => (
            <div key={k} className="flex gap-1">
              <dt>{k}</dt>
              <dd className="text-text">{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
    </li>
  );
}

function DecisionLog({ decisions }: { decisions: Decision[] }) {
  const [isShowingAll, setIsShowingAll] = useState(false);
  const shown = isShowingAll ? decisions : decisions.slice(0, DECISIONS_SHOWN);
  const hidden = decisions.length - shown.length;
  return (
    <details className="group">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 text-sm font-semibold [&::-webkit-details-marker]:hidden">
        <CaretDown size={16} className="transition-transform group-open:rotate-180 motion-reduce:transition-none" aria-hidden="true" />
        Why did the price change?
      </summary>
      <ol className="mt-2 flex flex-col gap-2">
        {shown.map((d) => (
          <DecisionRow key={d._id} d={d} />
        ))}
      </ol>
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setIsShowingAll(true)}
          className="press mt-2 inline-flex min-h-11 items-center rounded-full bg-surface-2 px-4 text-sm font-semibold hover:bg-hairline"
        >
          Show all {decisions.length} decisions
        </button>
      )}
    </details>
  );
}

export function LotCard({ lot, state, isUnreliable }: Props) {
  const prices = lot.prices.map((p) => p.price);
  const current = lot.prices[lot.prices.length - 1];
  const previous = lot.prices[lot.prices.length - 2];
  const change = current && previous && previous.price > 0 ? (current.price - previous.price) / previous.price : 0;
  const { free, total } = state;
  const freePct = free !== null && total ? (free / total) * 100 : null;

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="text-lg font-semibold">{lot.name}</h3>
          <span className="nums text-sm text-muted">
            {free === null ? "Free spaces unknown" : `${free} of ${total} spaces free`}
          </span>
        </div>
        <div className="flex flex-col items-end gap-1">
          {current ? (
            <span className="nums text-2xl leading-none font-bold">
              {money(current.price)}
              <span className="text-sm font-medium text-muted">/{current.unit}</span>
            </span>
          ) : (
            <span className="text-sm text-muted">No price yet</span>
          )}
          {change !== 0 && <Caption>{`${change > 0 ? "+" : ""}${Math.round(change * 100)}% last change`}</Caption>}
        </div>
      </div>

      <div className="flex items-end justify-between gap-4">
        <div className="flex flex-1 flex-col gap-1.5">
          <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-taken" role="img" aria-label={freePct === null ? "Occupancy unknown" : `${Math.round(100 - freePct)}% full`}>
            {freePct !== null && <div className="bar h-full bg-free" style={{ width: `${freePct}%` }} />}
          </div>
          {isUnreliable && <Chip tone="warning" className="self-start">From an unreliable frame</Chip>}
        </div>
        <Sparkline values={prices} />
      </div>

      {lot.decisions.length > 0 && <DecisionLog decisions={lot.decisions} />}
    </Card>
  );
}
