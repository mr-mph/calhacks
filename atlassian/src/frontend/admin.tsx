import ForgeReconciler, {
  Button, Heading, Inline, Lozenge, SectionMessage, Spinner, Stack, Tab, TabList, TabPanel, Tabs, Text,
} from "@forge/react";
import { useEffect, useState } from "react";
import type { RosterEntry } from "../domain/roster";
import type { AuditEntry, QueueItem } from "../ports";
import { AuditTab } from "./AuditTab";
import { QueueTab } from "./QueueTab";
import { RosterTab } from "./RosterTab";
import { call } from "./shared";

interface Overview {
  projectExists: boolean;
  roster: RosterEntry[];
  onShift: string | null;
  queue: QueueItem[];
  audit: AuditEntry[];
}

type Notice = { tone: "success" | "error"; text: string } | null;

function StatusBar({ data }: { data: Overview }) {
  return (
    <Inline space="space.200" alignBlock="center">
      <Lozenge appearance={data.projectExists ? "success" : "removed"}>{data.projectExists ? "BPAT ready" : "No BPAT project"}</Lozenge>
      <Lozenge appearance={data.onShift ? "inprogress" : "moved"}>{data.onShift ? `On shift: ${data.onShift}` : "No one on shift"}</Lozenge>
      <Lozenge appearance={data.queue.length ? "new" : "default"}>{`${data.queue.length} waiting for a human look`}</Lozenge>
    </Inline>
  );
}

function Admin() {
  const [data, setData] = useState<Overview | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  const load = () => call<Overview>("overview").then(setData).catch((e: Error) => setNotice({ tone: "error", text: e.message }));
  useEffect(() => { load(); }, []);

  const run = async (key: string, name: string, payload: Record<string, unknown>, done: (r: unknown) => string) => {
    setBusy(key);
    try {
      setNotice({ tone: "success", text: done(await call(name, payload)) });
      await load();
    } catch (e) {
      setNotice({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  if (!data) return notice ? <SectionMessage appearance="error"><Text>{notice.text}</Text></SectionMessage> : <Spinner label="Loading Balloon Patrol" />;

  return (
    <Stack space="space.300">
      <Heading size="large">Balloon Patrol</Heading>
      <Text>Confirmed balloon alerts become Beach Patrol incidents. Everything the agent does is listed here and can be undone.</Text>
      <StatusBar data={data} />
      {notice && <SectionMessage appearance={notice.tone}><Text>{notice.text}</Text></SectionMessage>}
      {!data.projectExists && (
        <SectionMessage appearance="warning" title="Create the Beach Patrol project">
          <Text>The agent only works in project BPAT. You'll be the project lead.</Text>
          <Button appearance="primary" isDisabled={busy !== null} onClick={() => run("setup", "setupProject", {}, () => "Created project BPAT")}>
            Create project BPAT
          </Button>
        </SectionMessage>
      )}
      <Tabs id="balloon-patrol-tabs">
        <TabList>
          <Tab>Agent actions</Tab>
          <Tab>{`Needs a human look (${data.queue.length})`}</Tab>
          <Tab>Roster</Tab>
          <Tab>Shift report</Tab>
        </TabList>
        <TabPanel>
          <AuditTab entries={data.audit} busyId={busy} onRevert={(id) => run(id, "revert", { id }, (r) => (r as AuditEntry).reason)} />
        </TabPanel>
        <TabPanel>
          <QueueTab
            items={data.queue}
            busyId={busy}
            onPromote={(id) => run(id, "promote", { id }, (r) => (r as { reason: string }).reason)}
            onDismiss={(id) => run(id, "dismiss", { id }, () => "Dismissed")}
          />
        </TabPanel>
        <TabPanel>
          <RosterTab roster={data.roster} isSaving={busy === "roster"} onSave={(roster) => run("roster", "saveRoster", { roster }, (n) => `Saved roster (${n} people)`)} />
        </TabPanel>
        <TabPanel>
          <Stack space="space.200">
            <Text>A report is written every day automatically: today's incidents, how fast they were raised and resolved, and what is still open.</Text>
            <Button isDisabled={busy !== null} onClick={() => run("report", "runReport", {}, (r) => {
              const { where, url } = r as { where: string; url: string };
              return `Report written to ${where === "confluence" ? "Confluence" : "Jira"}: ${url}`;
            })}>
              {busy === "report" ? "Writing..." : "Write today's report now"}
            </Button>
          </Stack>
        </TabPanel>
      </Tabs>
    </Stack>
  );
}

ForgeReconciler.render(<Admin />);
