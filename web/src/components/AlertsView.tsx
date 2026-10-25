import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "convex/react";
import { BellSimple, Check, LockSimple, X } from "@phosphor-icons/react";
import { api } from "../../convex/_generated/api";
import type { Alert } from "../lib/data";
import { usePatrolCode, WRONG_PATROL_CODE } from "../lib/patrol";
import { ago, clock, useNow } from "../lib/time";
import { AlertStats } from "./AlertStats";
import { PlayAlertButton, ReadAloudSwitch } from "./AlertVoice";
import { JiraStatus } from "./JiraStatus";
import { Button, Caption, Card, Chip, EmptyState, type Tone } from "./ui";

const SEVERITY: Record<NonNullable<Alert["severity"]>, { tone: Tone; label: string }> = {
  info: { tone: "neutral", label: "Info" },
  warning: { tone: "warning", label: "Warning" },
  critical: { tone: "critical", label: "Critical" },
};

function errorData(e: unknown): string | null {
  const data = (e as { data?: unknown }).data;
  return typeof data === "string" ? data : null;
}

type PatrolCodeFormProps = {
  wasWrong: boolean;
  onSave: (code: string) => void;
};

function PatrolCodeForm({ wasWrong, onSave }: PatrolCodeFormProps) {
  const [value, setValue] = useState("");
  const code = value.trim();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (code) onSave(code);
  }

  return (
    <Card className="flex flex-col gap-3">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        <LockSimple size={20} aria-hidden="true" />
        Patrol code
      </h2>
      <p className="max-w-[65ch] text-sm text-muted">
        Anyone can read alerts. To confirm or dismiss one, enter the code your patrol lead gave you. This phone
        remembers it.
      </p>
      <form onSubmit={handleSubmit} className="flex flex-wrap gap-2">
        <label htmlFor="patrol-code" className="sr-only">
          Patrol code
        </label>
        <input
          id="patrol-code"
          type="password"
          autoComplete="off"
          autoFocus={wasWrong}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="min-h-11 min-w-0 flex-1 rounded-full bg-surface-2 px-4 font-mono text-sm"
          aria-invalid={wasWrong}
          aria-describedby={wasWrong ? "patrol-code-error" : undefined}
        />
        <Button type="submit" variant="primary" disabled={!code}>
          Save code
        </Button>
      </form>
      {wasWrong && (
        <p id="patrol-code-error" role="alert" className="text-sm text-critical">
          That code didn't work. Check it with your patrol lead and enter it again.
        </p>
      )}
    </Card>
  );
}

type OpenAlertProps = {
  alert: Alert;
  now: number;
  code: string | null;
  onWrongCode: () => void;
};

function OpenAlert({ alert, now, code, onWrongCode }: OpenAlertProps) {
  const review = useMutation(api.alerts.review);
  const [busy, setBusy] = useState<"confirmed" | "dismissed" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sev = SEVERITY[alert.severity ?? "warning"];
  const isLocked = busy !== null || !code;

  async function handleReview(decision: "confirmed" | "dismissed") {
    if (!code) return;
    setBusy(decision);
    setError(null);
    try {
      await review({ id: alert._id, decision, code });
    } catch (e) {
      const data = errorData(e);
      if (data === WRONG_PATROL_CODE) onWrongCode();
      else setError(data ?? "Could not save. Check your connection and try again.");
    } finally {
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
          <PlayAlertButton alert={alert} />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" onClick={() => handleReview("confirmed")} disabled={isLocked}>
          <Check size={16} weight="bold" aria-hidden="true" />
          {busy === "confirmed" ? "Confirming…" : "Confirm alert"}
        </Button>
        <Button onClick={() => handleReview("dismissed")} disabled={isLocked}>
          <X size={16} weight="bold" aria-hidden="true" />
          {busy === "dismissed" ? "Dismissing…" : "Dismiss"}
        </Button>
      </div>
      {error && <p role="alert" className="text-sm text-critical">{error}</p>}
    </Card>
  );
}

type ReviewedAlertProps = {
  alert: Alert;
  now: number;
  code: string | null;
  onWrongCode: () => void;
};

function ReviewedAlert({ alert, now, code, onWrongCode }: ReviewedAlertProps) {
  const isConfirmed = alert.status === "confirmed";
  return (
    <li className="flex flex-col gap-1 rounded-[16px] bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <Chip tone={isConfirmed ? "free" : "neutral"}>{isConfirmed ? "Confirmed" : "Dismissed"}</Chip>
        <Caption>{clock(alert.reviewedAt ?? alert.t)}</Caption>
      </div>
      <p className="text-sm text-muted">{alert.text}</p>
      <JiraStatus alert={alert} now={now} code={code} onWrongCode={onWrongCode} />
    </li>
  );
}

export function AlertsView() {
  const alerts = useQuery(api.live.alerts);
  const now = useNow();
  const patrol = usePatrolCode();
  const [wasWrong, setWasWrong] = useState(false);
  if (alerts === undefined) return <Caption>Loading alerts…</Caption>;

  function handleSaveCode(code: string) {
    setWasWrong(false);
    patrol.save(code);
  }

  function handleWrongCode() {
    setWasWrong(true);
    patrol.forget();
  }

  const hasUnsent = alerts.reviewed.some((a) => a.status === "confirmed" && a.jira?.status !== "sent");
  const showCodeForm = !patrol.code && (alerts.open.length > 0 || hasUnsent);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="font-display text-2xl">Beach alerts</h1>
        <p className="max-w-[65ch] text-sm text-muted">
          Claude drafts these from the frame and the counts. Nothing goes out until a patrol member confirms it;
          a confirmed alert opens or updates an incident in the patrol's Jira.
        </p>
      </div>
      <AlertStats />
      <ReadAloudSwitch />
      {showCodeForm && <PatrolCodeForm wasWrong={wasWrong} onSave={handleSaveCode} />}
      {alerts.open.length === 0 ? (
        <EmptyState icon={<BellSimple size={28} aria-hidden="true" />} title="No alerts to review">
          When the camera sees a possible rip current or people in the water near one, a drafted alert shows up here
          for you to confirm or dismiss.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-3">
          {alerts.open.map((a) => (
            <OpenAlert key={a._id} alert={a} now={now} code={patrol.code} onWrongCode={handleWrongCode} />
          ))}
        </div>
      )}
      {alerts.reviewed.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold text-muted">Recently reviewed</h2>
          <ul className="flex flex-col gap-2">
            {alerts.reviewed.map((a) => (
              <ReviewedAlert key={a._id} alert={a} now={now} code={patrol.code} onWrongCode={handleWrongCode} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
