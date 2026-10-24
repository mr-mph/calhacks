import { validateRoster } from "./domain/roster";
import { PROJECT_KEY } from "./domain/scope";
import { createProject, projectExists } from "./services/jira";
import { kvsStore as store } from "./services/store";

export async function ensureProject(leadAccountId: string, actor: string): Promise<"created" | "exists"> {
  if (await projectExists()) return "exists";
  await createProject(leadAccountId);
  await store.appendAudit({
    action: "setup",
    actor,
    reason: `Created Jira project ${PROJECT_KEY} (Beach Patrol)`,
    inputs: { leadAccountId },
  });
  return "created";
}

export async function saveRoster(input: unknown, actor: string): Promise<number> {
  const roster = validateRoster(input);
  await store.setRoster(roster);
  await store.appendAudit({
    action: "roster",
    actor,
    reason: `Roster updated (${roster.length} people)`,
    inputs: { roster: roster.map((r) => `${r.name} ${r.start}-${r.end}`) },
  });
  return roster.length;
}
