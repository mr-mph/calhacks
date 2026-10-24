import { useState } from "react";
import { useMutation, useQuery } from "convex/react";
import { BellSimple, Check, X } from "@phosphor-icons/react";
import { api } from "../../convex/_generated/api";
import type { Alert } from "../lib/data";
import { ago, clock, useNow } from "../lib/time";
import { Button, Caption, Card, Chip, EmptyState, type Tone } from "./ui";

const SEVERITY: Record<NonNullable<Alert["severity"]>, { tone: Tone; label: string }> = {
  info: { tone: "neutral", label: "Info" },
  warning: { tone: "warning", label: "Warning" },
  critical: { tone: "critical", label: "Critical" },
};

function errorText(e: unknown): string {
  const data = (e as { data?: unknown }).data;
  if (typeof data === "string") return data;
  return "Could not save. Check your connection and try again.";
}

function OpenAlert({ alert, now }: { alert: Alert; now: number }) {
  const review = useMutation(api.alerts.review);
  const [busy, setBusy] = useState<"confirmed" | "dismissed" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sev = SEVERITY[alert.severity ?? "warning"];

  async function handleReview(decision: "confirmed" | "dismissed") {
    setBusy(decision);
    setError(null);
    try {
      await review({ id: alert._id, decision });
    } catch (e) {
      setError(errorText(e));
      setBusy(null);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <Chip tone={sev.tone}>{sev.label}</Chip>
        <Caption>{`${clock(alert.t)} · ${ago(now - alert.t)}`}</Caption>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row">
        {alert.frameUrl && (
          <img
            src={alert.frameUrl}
            alt="Frame the alert was written from"
            className="aspect-video w-full rounded-[8px] object-cover sm:w-48"
            style={{ outline: "1px solid var(--image-outline)", outlineOffset: "-1px" }}
            loading="lazy"
          />
        )}
        <div className="flex flex-col gap-2">
          <p className="max-w-[65ch] text-base">{alert.text}</p>
          <p className="max-w-[65ch] text-sm text-muted">
            <span className="font-semibold">Uncertainty: </span>
            {alert.uncertainty}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" onClick={() => handleReview("confirmed")} disabled={busy !== null}>
          <Check size={16} weight="bold" aria-hidden="true" />
          {busy === "confirmed" ? "Confirming…" : "Confirm alert"}
        </Button>
        <Button onClick={() => handleReview("dismissed")} disabled={busy !== null}>
          <X size={16} weight="bold" aria-hidden="true" />
          {busy === "dismissed" ? "Dismissing…" : "Dismiss"}
        </Button>
      </div>
      {error && <p role="alert" className="text-sm text-critical">{error}</p>}
    </Card>
  );
}

function ReviewedAlert({ alert }: { alert: Alert }) {
  const isConfirmed = alert.status === "confirmed";
  return (
    <li className="flex flex-col gap-1 rounded-[16px] bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <Chip tone={isConfirmed ? "free" : "neutral"}>{isConfirmed ? "Confirmed" : "Dismissed"}</Chip>
        <Caption>{clock(alert.reviewedAt ?? alert.t)}</Caption>
      </div>
      <p className="text-sm text-muted">{alert.text}</p>
    </li>
  );
}

export function AlertsView() {
  const alerts = useQuery(api.live.alerts);
  const now = useNow();
  if (alerts === undefined) return <Caption>Loading alerts…</Caption>;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="font-display text-2xl">Beach alerts</h1>
        <p className="max-w-[65ch] text-sm text-muted">
          Claude drafts these from the frame and the counts. Nothing goes out until a patrol member confirms it.
        </p>
      </div>
      {alerts.open.length === 0 ? (
        <EmptyState icon={<BellSimple size={28} aria-hidden="true" />} title="No alerts to review">
          When the camera sees a possible rip current or people in the water near one, a drafted alert shows up here
          for you to confirm or dismiss.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-3">
          {alerts.open.map((a) => (
            <OpenAlert key={a._id} alert={a} now={now} />
          ))}
        </div>
      )}
      {alerts.reviewed.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold text-muted">Recently reviewed</h2>
          <ul className="flex flex-col gap-2">
            {alerts.reviewed.map((a) => (
              <ReviewedAlert key={a._id} alert={a} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
