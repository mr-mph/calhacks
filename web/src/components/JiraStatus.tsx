import { useState } from "react";
import { useMutation } from "convex/react";
import { ArrowClockwise, ArrowSquareOut, WarningCircle } from "@phosphor-icons/react";
import { api } from "../../convex/_generated/api";
import { JIRA_STALLED_AFTER_S } from "../../convex/validators";
import { JIRA_BROWSE_URL } from "../config";
import type { Alert } from "../lib/data";
import { WRONG_PATROL_CODE } from "../lib/patrol";
import { Button, Caption } from "./ui";

type Props = {
  alert: Alert;
  now: number;
  code: string | null;
  onWrongCode: () => void;
};

function errorData(e: unknown): string | null {
  const data = (e as { data?: unknown }).data;
  return typeof data === "string" ? data : null;
}

// "Created BPAT-3, Highest, assigned to Maya" reads as "Sent to Jira: BPAT-3, Highest, assigned to Maya".
function sentSummary(jira: NonNullable<Alert["jira"]>): string {
  const reason = jira.reason ?? jira.outcome ?? "";
  return jira.outcome === "created" ? reason.replace(/^Created\s+/, "") : reason;
}

function IssueLink({ issueKey }: { issueKey: string }) {
  return (
    <a
      href={`${JIRA_BROWSE_URL}${encodeURIComponent(issueKey)}`}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 font-semibold underline underline-offset-2"
    >
      {issueKey}
      <ArrowSquareOut size={14} aria-hidden="true" />
      <span className="sr-only">(opens Jira)</span>
    </a>
  );
}

function Sent({ jira }: { jira: NonNullable<Alert["jira"]> }) {
  const summary = sentSummary(jira);
  const key = jira.issueKey;
  const at = key ? summary.indexOf(key) : -1;
  const body =
    key && at >= 0 ? (
      <>
        {summary.slice(0, at)}
        <IssueLink issueKey={key} />
        {summary.slice(at + key.length)}
      </>
    ) : (
      <>
        {summary}
        {key && (
          <>
            {" "}
            <IssueLink issueKey={key} />
          </>
        )}
      </>
    );
  return (
    <p className="text-sm">
      <span className="font-semibold text-free">Sent to Jira: </span>
      {body}
    </p>
  );
}

export function JiraStatus({ alert, now, code, onWrongCode }: Props) {
  const retry = useMutation(api.alerts.retryJira);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const jira = alert.jira;
  if (alert.status !== "confirmed") return null;
  if (jira?.status === "sent") return <Sent jira={jira} />;

  const isStalled = jira?.status === "sending" && now - jira.updatedAt > JIRA_STALLED_AFTER_S;
  if (jira?.status === "sending" && !isStalled) return <Caption>Sending to Jira…</Caption>;

  const problem = !jira
    ? "Not sent to Jira: this alert was confirmed before the Jira link existed."
    : isStalled
      ? "Jira hasn't answered yet. The send may have been lost."
      : `Not sent to Jira: ${jira.error ?? "unknown error"}`;

  async function handleRetry() {
    if (!code) return;
    setBusy(true);
    setError(null);
    try {
      await retry({ id: alert._id, code });
    } catch (e) {
      const data = errorData(e);
      if (data === WRONG_PATROL_CODE) onWrongCode();
      else setError(data ?? "Could not retry. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2" role="alert">
      <p className="flex items-start gap-1.5 text-sm text-critical">
        <WarningCircle size={18} className="mt-px shrink-0" aria-hidden="true" />
        <span>{problem}</span>
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={handleRetry} disabled={busy || !code}>
          <ArrowClockwise size={16} weight="bold" aria-hidden="true" />
          {busy ? "Sending…" : jira ? "Retry sending to Jira" : "Send to Jira"}
        </Button>
        {!code && <Caption>Enter the patrol code above to retry.</Caption>}
        {jira && jira.attempts > 1 && <Caption>{`${jira.attempts} attempts`}</Caption>}
      </div>
      {error && <p className="text-sm text-critical">{error}</p>}
    </div>
  );
}
