import { assertIssue, assertProject } from "../domain/scope";
import type { JiraPort } from "../ports";

// Every write the agent makes goes through here, so the BPAT boundary holds no matter what the
// caller passes. Reads are scoped too, so the agent can't be used to peek at other projects.
export function scopedJira(inner: JiraPort): JiraPort {
  return {
    createIssue: async (issue) => {
      assertProject(issue.projectKey);
      const key = await inner.createIssue(issue);
      assertIssue(key);
      return key;
    },
    addComment: async (key, body) => {
      assertIssue(key);
      return inner.addComment(key, body);
    },
    deleteComment: async (key, commentId) => {
      assertIssue(key);
      return inner.deleteComment(key, commentId);
    },
    assign: async (key, accountId) => {
      assertIssue(key);
      return inner.assign(key, accountId);
    },
    setPriority: async (key, priority) => {
      assertIssue(key);
      return inner.setPriority(key, priority);
    },
    getIssue: async (key) => {
      assertIssue(key);
      return inner.getIssue(key);
    },
  };
}
