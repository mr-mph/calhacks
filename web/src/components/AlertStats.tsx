import { useEffect, useState, type ReactNode } from "react";
import { useQuery } from "convex/react";
import { Check, Copy } from "@phosphor-icons/react";
import { api } from "../../convex/_generated/api";
import type { AlertStats as Stats } from "../lib/data";
import { Button, Caption, StatTile } from "./ui";

const COPIED_FOR_MS = 2000;
const DASH = <span className="text-muted">–</span>;

const SHORT_UNITS = { h: "h", min: "min", s: "s" };
const LONG_UNITS = { h: "hours", min: "minutes", s: "seconds" };

function duration(s: number, units = SHORT_UNITS): string {
  const total = Math.round(s);
  if (total < 60) return `${total} ${units.s}`;
  const m = Math.floor(total / 60);
  if (m < 60) return total % 60 ? `${m} ${units.min} ${total % 60} ${units.s}` : `${m} ${units.min}`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h} ${units.h} ${m % 60} ${units.min}` : `${h} ${units.h}`;
}

function count(n: number): string {
  return n.toLocaleString("en-US");
}

function plural(n: number, one: string, many: string): string {
  return `${count(n)} ${n === 1 ? one : many}`;
}

function confirmSentence(stats: Stats): string | null {
  if (stats.medianToConfirmS === null || stats.worstToConfirmS === null) return null;
  return (
    `The median time from the camera frame to a patrol member's confirmation was ` +
    `${duration(stats.medianToConfirmS, LONG_UNITS)}, and the slowest was ${duration(stats.worstToConfirmS, LONG_UNITS)}.`
  );
}

function devpostSummary(stats: Stats): string {
  const sentences = [
    `In the last 24 hours, Overhead watched ${plural(stats.framesWatched, "aerial frame", "aerial frames")} of the beach.`,
    `Claude drafted ${plural(stats.drafted, "beach alert", "beach alerts")}; patrol members confirmed ` +
      `${count(stats.confirmed)} and dismissed ${count(stats.dismissed)}, and nothing went out without a person's confirmation.`,
    confirmSentence(stats),
    `The most people counted in the water with a rip current in view, in a single frame, was ${count(stats.peakNearRip)}.`,
    `${plural(stats.jiraFiled, "confirmed alert was filed as an incident", "confirmed alerts were filed as incidents")} ` +
      `in the patrol's Jira.`,
  ];
  return sentences.filter(Boolean).join(" ");
}

type CopyState = "idle" | "copied" | "failed";

function CopyForDevpost({ stats }: { stats: Stats }) {
  const [state, setState] = useState<CopyState>("idle");
  const text = devpostSummary(stats);

  useEffect(() => {
    if (state !== "copied") return;
    const id = setTimeout(() => setState("idle"), COPIED_FOR_MS);
    return () => clearTimeout(id);
  }, [state]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
  }

  return (
    <>
      <Button onClick={handleCopy} className="min-h-9 px-4">
        {state === "copied" ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
        {state === "copied" ? "Copied" : "Copy for Devpost"}
      </Button>
      <span role="status" className="sr-only">
        {state === "copied" ? "Summary copied" : ""}
      </span>
      {state === "failed" && (
        <p className="w-full max-w-[65ch] text-sm text-muted select-all">
          This browser blocked copying. Select the summary and copy it yourself: {text}
        </p>
      )}
    </>
  );
}

function orDash(isEmpty: boolean, value: ReactNode): ReactNode {
  return isEmpty ? DASH : value;
}

function Tiles({ stats }: { stats: Stats }) {
  const hasAlerts = stats.drafted > 0;
  const hasConfirmed = stats.medianToConfirmS !== null && stats.worstToConfirmS !== null;
  const hasFrames = stats.framesWatched > 0;
  return (
    <div className="@container">
      <div className="grid grid-cols-2 gap-2 @3xl:grid-cols-4">
        <StatTile
          label="Alerts drafted"
          note={hasAlerts ? `${count(stats.confirmed)} confirmed, ${count(stats.dismissed)} dismissed` : "none in the last 24 h"}
        >
          {orDash(!hasAlerts, count(stats.drafted))}
        </StatTile>
        <StatTile
          label="Frame to confirmed"
          note={hasConfirmed ? `median; slowest ${duration(stats.worstToConfirmS!)}` : "none confirmed yet"}
        >
          {orDash(!hasConfirmed, duration(stats.medianToConfirmS!))}
        </StatTile>
        <StatTile
          label="In the water near a rip"
          note={hasFrames ? `most in one frame, of ${count(stats.framesWatched)} watched` : "no frames yet"}
        >
          {orDash(!hasFrames, count(stats.peakNearRip))}
        </StatTile>
        <StatTile
          label="Jira incidents filed"
          note={hasAlerts ? `from ${plural(stats.confirmed, "confirmed alert", "confirmed alerts")}` : "filed on confirm"}
        >
          {orDash(!hasAlerts, count(stats.jiraFiled))}
        </StatTile>
      </div>
    </div>
  );
}

export function AlertStats() {
  const stats = useQuery(api.stats.lastDay);
  if (stats === undefined) return null;
  return (
    <section aria-labelledby="alert-stats-heading" className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="alert-stats-heading" className="text-sm font-semibold text-muted">
          Last 24 hours <Caption className="font-normal">ending at the newest frame</Caption>
        </h2>
        {stats.drafted > 0 && <CopyForDevpost stats={stats} />}
      </div>
      <Tiles stats={stats} />
    </section>
  );
}
