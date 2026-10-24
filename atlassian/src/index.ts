import { writeShiftReport } from "./shiftReport";

export { handleWebTrigger as ingest } from "./webtrigger";
export { handler as resolver } from "./resolvers";

// Installed in both Jira and Confluence, but the roster, audit log and queue live in the Jira
// installation's storage, so only that installation writes the report.
export async function shiftReport({ context }: { context?: { installContext?: string } }): Promise<void> {
  if (!context?.installContext?.startsWith("ari:cloud:jira:")) return;
  await writeShiftReport("agent");
}
