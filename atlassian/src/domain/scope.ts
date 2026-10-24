export const PROJECT_KEY = "BPAT";
export const PROJECT_NAME = "Beach Patrol";
const ISSUE_KEY = new RegExp(`^${PROJECT_KEY}-[1-9]\\d*$`);

export class ScopeError extends Error {}

export function assertProject(projectKey: string): void {
  if (projectKey !== PROJECT_KEY) throw new ScopeError(`Agent may only act in project ${PROJECT_KEY}, not ${projectKey}`);
}

export function assertIssue(issueKey: string): void {
  if (!ISSUE_KEY.test(issueKey)) throw new ScopeError(`Agent may only act on ${PROJECT_KEY} issues, not ${issueKey}`);
}
