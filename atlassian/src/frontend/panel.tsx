import ForgeReconciler, { DynamicTable, SectionMessage, Spinner, Stack, Text } from "@forge/react";
import { useEffect, useState } from "react";
import type { AuditEntry } from "../ports";
import { ActionLozenge, actorLabel, call, when } from "./shared";

const head = {
  cells: [
    { key: "when", content: "When" },
    { key: "action", content: "Action" },
    { key: "who", content: "By" },
    { key: "why", content: "Why" },
  ],
};

const row = (e: AuditEntry) => ({
  key: e.id,
  isHighlighted: e.action === "flag",
  cells: [
    { key: "when", content: when(e.at) },
    { key: "action", content: <ActionLozenge action={e.action} /> },
    { key: "who", content: actorLabel(e) },
    { key: "why", content: e.revertedAt ? `${e.reason} (reverted ${when(e.revertedAt)})` : e.reason },
  ],
});

function Panel() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    call<AuditEntry[]>("issueLog").then(setEntries).catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <SectionMessage appearance="error" title="Couldn't load the agent log"><Text>{error}</Text></SectionMessage>;
  if (!entries) return <Spinner label="Loading agent actions" />;
  if (!entries.length) return <Text>Balloon Patrol hasn't acted on this issue.</Text>;
  return (
    <Stack space="space.100">
      <Text>Every change Balloon Patrol made here, oldest last. Jira admins can revert these from Apps, Balloon Patrol.</Text>
      <DynamicTable head={head} rows={entries.map(row)} rowsPerPage={10} />
    </Stack>
  );
}

ForgeReconciler.render(<Panel />);
