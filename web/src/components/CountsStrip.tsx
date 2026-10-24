import type { ReactNode } from "react";
import type { Observation, Site } from "../lib/data";
import { CONFIDENCE_MIN, OFFLINE_AFTER_S, STALE_AFTER_S, zonePeople } from "../lib/data";
import { ago } from "../lib/time";

type Props = {
  observation: Observation | null;
  site: Site | null;
  frameT: number | null;
  now: number;
};

function Tile({ label, children, note, className = "" }: { label: string; children: ReactNode; note?: ReactNode; className?: string }) {
  return (
    <div className={`flex min-w-0 flex-col gap-1 rounded-[16px] bg-surface p-3 shadow-soft ${className}`}>
      <span className="text-xs font-semibold text-muted">{label}</span>
      <span className="nums text-2xl leading-none font-bold">{children}</span>
      {note && <span className="font-mono text-xs text-muted">{note}</span>}
    </div>
  );
}

function freshness(age: number | null): { tone: string; note: string } {
  if (age === null) return { tone: "text-muted", note: "no frames yet" };
  if (age > OFFLINE_AFTER_S) return { tone: "text-critical", note: "station quiet" };
  if (age > STALE_AFTER_S) return { tone: "text-warning", note: "frames are late" };
  return { tone: "text-free", note: "live" };
}

function people(n: number | null): ReactNode {
  return n === null ? <span className="text-muted">–</span> : n;
}

export function CountsStrip({ observation, site, frameT, now }: Props) {
  const beach = zonePeople(observation, site, "beach");
  const water = zonePeople(observation, site, "water");
  const conf = observation?.confidence ?? null;
  const isLow = conf !== null && conf < CONFIDENCE_MIN;
  const age = frameT === null ? null : now - frameT;
  const fresh = freshness(age);

  return (
    <div className="@container">
      <div className="grid grid-cols-2 gap-2 @lg:grid-cols-3 @3xl:grid-cols-5">
      <Tile label="Cars" note={observation ? "whole frame" : undefined}>{observation?.counts.car ?? <span className="text-muted">–</span>}</Tile>
      <Tile label="On the beach" note={beach === null ? "no beach in view" : undefined}>{people(beach)}</Tile>
      <Tile label="In the water" note={water === null ? "no water in view" : undefined}>{people(water)}</Tile>
      <Tile label="Frame confidence" note={isLow ? "below 0.5, prices hold" : conf !== null ? "good enough to price" : undefined}>
        {conf === null ? <span className="text-muted">–</span> : <span className={isLow ? "text-warning" : ""}>{Math.round(conf * 100)}%</span>}
      </Tile>
      <Tile label="Updated" className="col-span-2 @lg:col-span-1" note={<span className={fresh.tone}>{fresh.note}</span>}>
        <span className="font-mono text-xl">{age === null ? "–" : ago(age)}</span>
      </Tile>
      </div>
    </div>
  );
}
