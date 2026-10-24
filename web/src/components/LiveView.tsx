import { useQuery } from "convex/react";
import { BellRinging, Camera, Car } from "@phosphor-icons/react";
import { api } from "../../convex/_generated/api";
import { lotState, unreliableReason } from "../lib/data";
import { useNow } from "../lib/time";
import { CountsStrip } from "./CountsStrip";
import { FrameView } from "./FrameView";
import { LotCard } from "./LotCard";
import { Caption, EmptyState } from "./ui";

const START_STATION = "python ground/station.py --pi http://balloon.local:8080";

type Props = {
  openAlerts: number;
};

export function LiveView({ openAlerts }: Props) {
  const live = useQuery(api.live.now);
  const lots = useQuery(api.live.lots);
  const now = useNow();
  if (live === undefined) return <Caption>Connecting to the live feed…</Caption>;

  const { frame, observation, site } = live;
  const isUnreliable = observation ? unreliableReason(observation) !== null : false;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="sr-only">Live view</h1>
      {openAlerts > 0 && (
        <a href="#/alerts" className="press flex min-h-11 items-center gap-2 self-start rounded-full bg-critical/15 px-4 text-sm font-semibold text-critical">
          <BellRinging size={16} weight="bold" aria-hidden="true" />
          {openAlerts === 1 ? "1 beach alert needs review" : `${openAlerts} beach alerts need review`}
        </a>
      )}

      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        {frame ? (
          <FrameView frame={frame} observation={observation} site={site} />
        ) : (
          <EmptyState icon={<Camera size={28} aria-hidden="true" />} title="No frames yet" command={START_STATION}>
            Start the ground station on the laptop. It pulls a still from the balloon every 2 seconds and sends it here.
          </EmptyState>
        )}
        <CountsStrip observation={observation} site={site} frameT={frame?.t ?? observation?.t ?? null} now={now} />
      </div>

      <section className="flex flex-col gap-3 pt-4">
        <h2 className="font-display text-xl">Parking</h2>
        {lots === undefined ? (
          <Caption>Loading lots…</Caption>
        ) : lots.length === 0 ? (
          <EmptyState icon={<Car size={28} aria-hidden="true" />} title="No lots mapped yet">
            Draw the lot and its spaces on a reference frame in a site file (ground/sites/), and the station sends it
            here. Prices appear once the pricing agent makes its first decision.
          </EmptyState>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {lots.map((lot) => (
              <LotCard key={lot.id} lot={lot} state={lotState(lot, observation)} isUnreliable={isUnreliable} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
