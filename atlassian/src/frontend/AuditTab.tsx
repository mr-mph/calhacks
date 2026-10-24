import { Button, DynamicTable, Lozenge, Stack, Text } from "@forge/react";
import type { AuditEntry } from "../ports";
import { ActionLozenge, actorLabel, when } from "./shared";

type Props = {
  entries: AuditEntry[];
  busyId: string | null;
  onRevert: (id: string) => void;
};

const head = {
  cells: [
    { key: "when", content: "When" },
    { key: "action", content: "Action" },
    { key: "issue", content: "Issue" },
    { key: "who", content: "By" },
    { key: "why", content: "Why" },
    { key: "undo", content: "" },
  ],
};

function UndoCell({ entry, busyId, onRevert }: { entry: AuditEntry; busyId: string | null; onRevert: (id: string) => void }) {
  if (entry.revertedAt) return <Lozenge>Reverted</Lozenge>;
  if (!entry.revert) return null;
  return (
    <Button appearance="subtle" isDisabled={busyId !== null} onClick={() => onRevert(entry.id)}>
      {busyId === entry.id ? "Reverting..." : "Revert"}
    </Button>
  );
}

export function AuditTab({ entries, busyId, onRevert }: Props) {
  const rows = entries.map((e) => ({
    key: e.id,
    isHighlighted: e.action === "flag" || e.action === "blocked",
    cells: [
      { key: "when", content: when(e.at) },
      { key: "action", content: <ActionLozenge action={e.action} /> },
      { key: "issue", content: e.issueKey ?? "" },
      { key: "who", content: actorLabel(e) },
      { key: "why", content: e.reason },
      { key: "undo", content: <UndoCell entry={e} busyId={busyId} onRevert={onRevert} /> },
    ],
  }));
  return (
    <Stack space="space.100">
      <Text>
        Newest first. Revert undoes one agent change (its comment, its assignment or its priority change) and refuses if a person has
        changed that field since.
      </Text>
      <DynamicTable head={head} rows={rows} rowsPerPage={20} emptyView={<Text>The agent hasn't done anything yet.</Text>} />
    </Stack>
  );
}
