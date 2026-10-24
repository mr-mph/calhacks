import api, { route, type APIResponse } from "@forge/api";
import { PROJECT_KEY, PROJECT_NAME } from "../domain/scope";
import type { IssueState, JiraPort } from "../ports";
import { scopedJira } from "./scopedJira";

const ISSUE_FIELDS = "summary,status,assignee,priority,created,resolutiondate";
const KANBAN_TEMPLATE = "com.pyxis.greenhopper.jira:gh-simplified-kanban-classic";

const json = { Accept: "application/json", "Content-Type": "application/json" };
const jira = () => api.asApp();

async function ok(res: APIResponse, what: string): Promise<APIResponse> {
  if (res.ok) return res;
  const detail = (await res.text()).slice(0, 300);
  throw new Error(`${what} failed: HTTP ${res.status} ${detail}`);
}

interface RawIssue {
  key: string;
  fields: {
    summary?: string;
    status?: { name?: string; statusCategory?: { key?: string } };
    assignee?: { accountId?: string; displayName?: string } | null;
    priority?: { name?: string } | null;
    created?: string;
    resolutiondate?: string | null;
  };
}

const toState = ({ key, fields: f }: RawIssue): IssueState => ({
  key,
  summary: f.summary ?? "",
  status: f.status?.name ?? "Unknown",
  isDone: f.status?.statusCategory?.key === "done",
  assigneeAccountId: f.assignee?.accountId ?? null,
  assigneeName: f.assignee?.displayName ?? null,
  priority: f.priority?.name ?? null,
  created: f.created ? Date.parse(f.created) : 0,
  resolved: f.resolutiondate ? Date.parse(f.resolutiondate) : null,
});

const restJira: JiraPort = {
  async createIssue({ projectKey, summary, description, priority, labels }) {
    const res = await jira().requestJira(route`/rest/api/3/issue`, {
      method: "POST",
      headers: json,
      body: JSON.stringify({
        fields: { project: { key: projectKey }, issuetype: { name: "Task" }, summary, description, priority: { name: priority }, labels },
      }),
    });
    return ((await (await ok(res, "Create issue")).json()) as { key: string }).key;
  },
  async addComment(issueKey, body) {
    const res = await jira().requestJira(route`/rest/api/3/issue/${issueKey}/comment`, {
      method: "POST",
      headers: json,
      body: JSON.stringify({ body }),
    });
    return ((await (await ok(res, `Comment on ${issueKey}`)).json()) as { id: string }).id;
  },
  async deleteComment(issueKey, commentId) {
    const res = await jira().requestJira(route`/rest/api/3/issue/${issueKey}/comment/${commentId}`, { method: "DELETE" });
    await ok(res, `Delete comment ${commentId}`);
  },
  async assign(issueKey, accountId) {
    const res = await jira().requestJira(route`/rest/api/3/issue/${issueKey}/assignee`, {
      method: "PUT",
      headers: json,
      body: JSON.stringify({ accountId }),
    });
    await ok(res, `Assign ${issueKey}`);
  },
  async setPriority(issueKey, priority) {
    const res = await jira().requestJira(route`/rest/api/3/issue/${issueKey}`, {
      method: "PUT",
      headers: json,
      body: JSON.stringify({ fields: { priority: { name: priority } } }),
    });
    await ok(res, `Set priority on ${issueKey}`);
  },
  async getIssue(issueKey) {
    const res = await jira().requestJira(route`/rest/api/3/issue/${issueKey}?fields=${ISSUE_FIELDS}`, { headers: json });
    if (res.status === 404) return null;
    return toState((await (await ok(res, `Read ${issueKey}`)).json()) as RawIssue);
  },
};

export const agentJira: JiraPort = scopedJira(restJira);

export async function projectExists(): Promise<boolean> {
  const res = await jira().requestJira(route`/rest/api/3/project/${PROJECT_KEY}`, { headers: json });
  if (res.status === 404) return false;
  await ok(res, "Read project");
  return true;
}

export async function createProject(leadAccountId: string): Promise<void> {
  const res = await jira().requestJira(route`/rest/api/3/project`, {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      key: PROJECT_KEY,
      name: PROJECT_NAME,
      projectTypeKey: "software",
      projectTemplateKey: KANBAN_TEMPLATE,
      leadAccountId,
      assigneeType: "UNASSIGNED",
      description: "Beach incidents raised by Balloon Patrol from confirmed balloon alerts.",
    }),
  });
  await ok(res, "Create project");
}

export async function isJiraAdmin(accountId: string): Promise<boolean> {
  const res = await jira().requestJira(route`/rest/api/3/permissions/check`, {
    method: "POST",
    headers: json,
    body: JSON.stringify({ accountId, globalPermissions: ["ADMINISTER"] }),
  });
  if (!res.ok) return false;
  const body = (await res.json()) as { globalPermissions?: string[] };
  return body.globalPermissions?.includes("ADMINISTER") ?? false;
}

export async function openIncidents(): Promise<IssueState[]> {
  const jql = `project = ${PROJECT_KEY} AND statusCategory != Done AND labels = balloon-patrol ORDER BY created ASC`;
  const res = await jira().requestJira(route`/rest/api/3/search/jql`, {
    method: "POST",
    headers: json,
    body: JSON.stringify({ jql, fields: ISSUE_FIELDS.split(","), maxResults: 100 }),
  });
  const body = (await (await ok(res, "Search issues")).json()) as { issues?: RawIssue[] };
  return (body.issues ?? []).map(toState);
}
