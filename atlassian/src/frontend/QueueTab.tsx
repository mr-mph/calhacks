import { Button, ButtonGroup, DynamicTable, Link, Stack, Text } from "@forge/react";
import type { QueueItem } from "../ports";
import { when } from "./shared";

type Props = {
  items: QueueItem[];
  busyId: string | null;
  onPromote: (id: string) => void;
  onDismiss: (id: string) => void;
};

const head = {
  cells: [
    { key: "when", content: "Received" },
    { key: "zone", content: "Zone" },
    { key: "alert", content: "Alert" },
    { key: "why", content: "Why it is waiting" },
    { key: "frame", content: "Frame" },
    { key: "act", content: "" },
  ],
};

export function QueueTab({ items, busyId, onPromote, onDismiss }: Props) {
  const rows = items.map((q) => ({
    key: q.id,
    cells: [
      { key: "when", content: when(q.at) },
      { key: "zone", content: q.alert.zone },
      { key: "alert", content: `${q.alert.text} (${q.alert.personWater} in water, ${q.alert.personBeach} on beach)` },
      { key: "why", content: q.reason },
      { key: "frame", content: q.alert.frameUrl ? <Link href={q.alert.frameUrl} openNewTab>Open frame</Link> : "Missing" },
      {
        key: "act",
        content: (
          <ButtonGroup>
            <Button appearance="primary" isDisabled={busyId !== null} onClick={() => onPromote(q.id)}>Open incident</Button>
            <Button appearance="subtle" isDisabled={busyId !== null} onClick={() => onDismiss(q.id)}>Dismiss</Button>
          </ButtonGroup>
        ),
      },
    ],
  }));
  return (
    <Stack space="space.100">
      <Text>Alerts from low-confidence frames don't page anyone. Look at the frame, then open an incident or dismiss it.</Text>
      <DynamicTable head={head} rows={rows} emptyView={<Text>Nothing is waiting for a human look.</Text>} />
    </Stack>
  );
}
