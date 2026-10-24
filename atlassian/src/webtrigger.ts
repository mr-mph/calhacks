import type { WebTriggerRequest, WebTriggerResponse } from "@forge/api";
import { handleAlert } from "./agent";
import { MAX_BODY_BYTES, parseAlert } from "./domain/alert";
import { ScopeError } from "./domain/scope";
import { header, SECRET_HEADER, secretMatches } from "./domain/secret";
import { AGENT, type Deps } from "./ports";
import { agentJira } from "./services/jira";
import { kvsStore } from "./services/store";
import { ensureProject, saveRoster } from "./setup";

const deps: Deps = { jira: agentJira, store: kvsStore, now: () => new Date() };

const respond = (statusCode: number, body: unknown): WebTriggerResponse => ({
  statusCode,
  headers: { "Content-Type": ["application/json"] },
  body: JSON.stringify(body),
});

async function ingest(raw: string): Promise<WebTriggerResponse> {
  const parsed = parseAlert(raw);
  if (!parsed.ok) return respond(400, { error: parsed.error });
  try {
    return respond(200, await handleAlert(deps, parsed.alert));
  } catch (err) {
    const blocked = err instanceof ScopeError;
    console.error("Alert handling failed", parsed.alert.alertId, err);
    await kvsStore.appendAudit({
      action: blocked ? "blocked" : "error",
      actor: AGENT,
      alertId: parsed.alert.alertId,
      reason: (err as Error).message.slice(0, 300),
      inputs: { zone: parsed.alert.zone },
    });
    return respond(blocked ? 403 : 502, { error: blocked ? "Action outside project BPAT was blocked" : "Jira call failed; see the Balloon Patrol audit log" });
  }
}

async function bootstrap(raw: string): Promise<WebTriggerResponse> {
  const body = JSON.parse(raw) as { lead_account_id?: unknown; roster?: unknown };
  if (typeof body.lead_account_id !== "string") return respond(400, { error: "lead_account_id is required" });
  const project = await ensureProject(body.lead_account_id, "station");
  const roster = body.roster === undefined ? undefined : await saveRoster(body.roster, "station");
  return respond(200, { project, roster });
}

export async function handleWebTrigger(request: WebTriggerRequest): Promise<WebTriggerResponse> {
  if (request.method !== "POST") return respond(405, { error: "POST only" });
  if (!secretMatches(header(request.headers, SECRET_HEADER), process.env.INGEST_SECRET)) {
    return respond(401, { error: "unauthorized" });
  }
  const raw = request.body ?? "";
  if (Buffer.byteLength(raw, "utf8") > MAX_BODY_BYTES) return respond(413, { error: "body too large" });
  const action = request.queryParameters?.action?.[0];
  try {
    return action === "bootstrap" ? await bootstrap(raw) : await ingest(raw);
  } catch (err) {
    console.error("Web trigger failed", err);
    return respond(500, { error: (err as Error).message.slice(0, 200) });
  }
}
