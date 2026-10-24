import { useEffect, useState } from "react";
import { WarningCircle } from "@phosphor-icons/react";
import type { Frame, Observation, Site } from "../lib/data";
import { unreliableReason } from "../lib/data";
import { Caption, Chip } from "./ui";

type Props = {
  frame: Frame;
  observation: Observation | null;
  site: Site | null;
};

function useDecodedFrame(frame: Frame): Frame | null {
  const [shown, setShown] = useState<Frame | null>(null);
  useEffect(() => {
    let isCurrent = true;
    const img = new Image();
    img.src = frame.url;
    img
      .decode()
      .catch(() => undefined)
      .then(() => isCurrent && setShown(frame));
    return () => {
      isCurrent = false;
    };
    // Keyed on the id: every live update hands us a new object for the same frame.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame._id]);
  return shown;
}

function points(polygon: number[][]): string {
  return polygon.map(([x, y]) => `${x},${y}`).join(" ");
}

type SpaceState = "free" | "taken" | "unknown";

function spaceState(id: string, obs: Observation | null, matches: boolean): SpaceState {
  const occupied = matches && obs?.aligned ? obs.spaces?.[id] : undefined;
  if (occupied === undefined) return "unknown";
  return occupied ? "taken" : "free";
}

const SPACE_LOOK: Record<SpaceState, { className: string; fill: string; stroke: string; fillOpacity: number }> = {
  free: { className: "space space-free", fill: "var(--free)", stroke: "var(--free)", fillOpacity: 0.45 },
  taken: { className: "space", fill: "var(--taken)", stroke: "var(--taken)", fillOpacity: 0.85 },
  unknown: { className: "space", fill: "transparent", stroke: "var(--text-muted)", fillOpacity: 0 },
};

function Overlay({ site, observation, matches, width, height }: { site: Site; observation: Observation | null; matches: boolean; width: number; height: number }) {
  const [refW, refH] = site.image_size && site.image_size.length === 2 ? site.image_size : [width, height];
  const label = Math.max(12, (refW ?? width) / 90);
  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      viewBox={`0 0 ${refW} ${refH}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {site.zones.map((z) => (
        <g key={z.id}>
          <polygon
            points={points(z.polygon)}
            fill="none"
            stroke="var(--text)"
            strokeOpacity={0.55}
            strokeWidth={2}
            strokeDasharray="10 8"
            vectorEffect="non-scaling-stroke"
          />
          {z.polygon[0] && (
            <text x={z.polygon[0][0]} y={(z.polygon[0][1] ?? 0) - label / 2} fill="var(--text)" fontSize={label} fontFamily="IBM Plex Mono, monospace" paintOrder="stroke" stroke="var(--bg)" strokeWidth={label / 4}>
              {z.name ?? z.id}
            </text>
          )}
        </g>
      ))}
      {site.spaces.map((s) => {
        const look = SPACE_LOOK[spaceState(s.id, observation, matches)];
        return (
          <polygon
            key={s.id}
            className={look.className}
            points={points(s.polygon)}
            fill={look.fill}
            fillOpacity={look.fillOpacity}
            stroke={look.stroke}
            strokeWidth={2}
            strokeDasharray={look.fill === "transparent" ? "4 4" : undefined}
            vectorEffect="non-scaling-stroke"
          />
        );
      })}
    </svg>
  );
}

export function FrameView({ frame: latest, observation, site }: Props) {
  const shown = useDecodedFrame(latest);
  const frame = shown ?? latest;
  const matches = observation?.frame === frame.name;
  const reason = observation && matches ? unreliableReason(observation) : null;
  const spaces = site?.spaces ?? [];
  const states = spaces.map((s) => spaceState(s.id, observation, matches));
  const free = states.filter((s) => s === "free").length;
  const taken = states.filter((s) => s === "taken").length;

  return (
    <figure className="flex flex-col gap-2">
      <div
        className="relative w-full overflow-hidden rounded-[16px] bg-surface-2 shadow-soft"
        style={{ aspectRatio: `${frame.width} / ${frame.height}`, outline: "1px solid var(--image-outline)", outlineOffset: "-1px" }}
      >
        {shown && (
          <img src={shown.url} alt={`Aerial frame ${frame.name}`} width={frame.width} height={frame.height} className="absolute inset-0 h-full w-full object-cover" fetchPriority="high" />
        )}
        {site && <Overlay site={site} observation={observation} matches={matches} width={frame.width} height={frame.height} />}
        {reason && (
          <Chip tone="warning" className="absolute top-3 left-3 bg-[color-mix(in_srgb,var(--bg)_80%,transparent)] backdrop-blur">
            <WarningCircle size={16} weight="bold" aria-hidden="true" />
            Frame unreliable: {reason}
          </Chip>
        )}
      </div>
      <figcaption className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        {spaces.length > 0 ? (
          <span className="flex items-center gap-4 text-sm">
            <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-free" />{free} free</span>
            <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-taken" />{taken} taken</span>
            {free + taken < spaces.length && (
              <span className="flex items-center gap-1.5 text-muted"><span className="size-2.5 rounded-full ring-1 ring-muted ring-inset" />{spaces.length - free - taken} unknown</span>
            )}
          </span>
        ) : (
          <span className="text-sm text-muted">No parking map for this site yet.</span>
        )}
        <Caption>
          {frame.name}
          {observation?.alt_m !== undefined && matches ? ` · ${Math.round(observation.alt_m)} m up` : ""}
        </Caption>
      </figcaption>
    </figure>
  );
}
