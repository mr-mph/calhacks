import Resolver from "@forge/resolver";
import { onShift } from "./domain/roster";
import { assertIssue } from "./domain/scope";
import { dismissQueued, promoteQueued, revertAction } from "./humanActions";
import type { Deps } from "./ports";
import { agentJira, isJiraAdmin, projectExists } from "./services/jira";
import { kvsStore as store } from "./services/store";
import { ensureProject, saveRoster } from "./setup";
import { writeShiftReport } from "./shiftReport";

const AUDIT_PAGE = 100;
const deps: Deps = { jira: agentJira, store, now: () => new Date() };

interface Ctx {
  accountId?: string;
  extension?: { issue?: { key?: string } };
}
type Payload = Record<string, unknown>;
type Result<T> = { ok: true; data: T } | { ok: false; error: string };

async function attempt<T>(fn: () => Promise<T>): Promise<Result<T>> {
  try {
    return { ok: true, data: await fn() };
  } catch (err) {
    console.error("Resolver failed", err);
    return { ok: false, error: (err as Error).message };
  }
}

async function adminId(context: Ctx): Promise<string> {
  const id = context.accountId;
  if (!id || !(await isJiraAdmin(id))) throw new Error("Only Jira admins can do this");
  return id;
}

const asId = (payload: Payload): string => {
  if (typeof payload.id !== "string" || payload.id.length > 64) throw new Error("Missing id");
  return payload.id;
};

const admin = <T>(fn: (actor: string, payload: Payload) => Promise<T>) =>
  ({ payload, context }: { payload: Payload; context: Ctx }) => attempt(async () => fn(await adminId(context), payload ?? {}));

const resolver = new Resolver();

resolver.define(
  "overview",
  admin(async () => {
    const [exists, roster, queue, audit] = await Promise.all([projectExists(), store.getRoster(), store.listQueue(), store.listAudit(AUDIT_PAGE)]);
    return { projectExists: exists, roster, onShift: onShift(roster, new Date())?.name ?? null, queue: queue.filter((q) => q.status === "open"), audit };
  }),
);
resolver.define("saveRoster", admin((actor, p) => saveRoster(p.roster, actor)));
resolver.define("setupProject", admin((actor) => ensureProject(actor, actor)));
resolver.define("revert", admin((actor, p) => revertAction(deps, asId(p), actor)));
resolver.define("promote", admin((actor, p) => promoteQueued(deps, asId(p), actor)));
resolver.define("dismiss", admin((actor, p) => dismissQueued(deps, asId(p), actor)));
resolver.define("runReport", admin(async (actor) => {
  const { where, url, report } = await writeShiftReport(actor);
  return { where, url, incidents: report.incidents.length };
}));

// The issue key comes from the panel's own context, never from the payload.
resolver.define("issueLog", ({ context }: { context: Ctx }) =>
  attempt(async () => {
    const key = context.extension?.issue?.key ?? "";
    try {
      assertIssue(key);
    } catch {
      return [];
    }
    return store.auditForIssue(key);
  }),
);

export const handler = resolver.getDefinitions();
