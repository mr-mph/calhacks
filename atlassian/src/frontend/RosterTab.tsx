import { Button, DynamicTable, Inline, Stack, Text, Textfield, UserPicker } from "@forge/react";
import { useState } from "react";
import type { RosterEntry } from "../domain/roster";

type Props = {
  roster: RosterEntry[];
  isSaving: boolean;
  onSave: (roster: RosterEntry[]) => void;
};

const EMPTY = { name: "", accountId: "", start: "08:00", end: "16:00" };

const head = {
  cells: [
    { key: "name", content: "Name" },
    { key: "shift", content: "Shift (Pacific time)" },
    { key: "remove", content: "" },
  ],
};

export function RosterTab({ roster, isSaving, onSave }: Props) {
  const [draft, setDraft] = useState<RosterEntry[]>(roster);
  const [row, setRow] = useState<RosterEntry>(EMPTY);
  const canAdd = row.name !== "" && row.accountId !== "";

  const rows = draft.map((r, i) => ({
    key: `${r.accountId}-${i}`,
    cells: [
      { key: "name", content: r.name },
      { key: "shift", content: `${r.start} to ${r.end}` },
      { key: "remove", content: <Button appearance="subtle" onClick={() => setDraft(draft.filter((_, j) => j !== i))}>Remove</Button> },
    ],
  }));

  return (
    <Stack space="space.200">
      <Text>The agent assigns each new incident to the first person whose shift covers the time of the alert.</Text>
      <DynamicTable head={head} rows={rows} emptyView={<Text>No one on the roster yet. New incidents stay unassigned.</Text>} />
      <UserPicker
        label="Atlassian account"
        name="accountId"
        onChange={(u) => setRow({ ...row, accountId: u?.id ?? "", name: row.name || (u?.name ?? "") })}
      />
      <Inline space="space.100" alignBlock="end">
        <Textfield name="name" placeholder="Name" value={row.name} onChange={(e) => setRow({ ...row, name: String(e.target.value ?? "") })} />
        <Textfield name="start" placeholder="Start HH:MM" value={row.start} onChange={(e) => setRow({ ...row, start: String(e.target.value ?? "") })} />
        <Textfield name="end" placeholder="End HH:MM" value={row.end} onChange={(e) => setRow({ ...row, end: String(e.target.value ?? "") })} />
        <Button isDisabled={!canAdd} onClick={() => { setDraft([...draft, row]); setRow(EMPTY); }}>Add to roster</Button>
      </Inline>
      <Button appearance="primary" isDisabled={isSaving} onClick={() => onSave(draft)}>
        {isSaving ? "Saving..." : "Save roster"}
      </Button>
    </Stack>
  );
}
