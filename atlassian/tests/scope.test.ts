import { describe, expect, it } from "vitest";
import { doc } from "../src/domain/adf";
import { assertIssue, ScopeError } from "../src/domain/scope";
import { fakeJira } from "./fakes";

describe("BPAT-only guard", () => {
  const { jira, calls } = fakeJira();

  it.each(["OPS-1", "bpat-1", "BPAT-0", "BPAT-1 OR 1=1", "BPATX-1", "../BPAT-1"])("rejects %s", (key) => {
    expect(() => assertIssue(key)).toThrow(ScopeError);
  });

  it("blocks every write outside BPAT before reaching Jira", async () => {
    await expect(jira.addComment("OPS-7", doc())).rejects.toThrow(ScopeError);
    await expect(jira.deleteComment("OPS-7", "1")).rejects.toThrow(ScopeError);
    await expect(jira.assign("OPS-7", "x")).rejects.toThrow(ScopeError);
    await expect(jira.setPriority("OPS-7", "Highest")).rejects.toThrow(ScopeError);
    await expect(jira.getIssue("OPS-7")).rejects.toThrow(ScopeError);
    await expect(
      jira.createIssue({ projectKey: "OPS", summary: "x", description: doc(), priority: "High", labels: [] }),
    ).rejects.toThrow(ScopeError);
    expect(calls).toEqual([]);
  });

  it("rejects an issue created outside BPAT even if Jira returns it", async () => {
    const other = fakeJira("OPS");
    await expect(
      other.jira.createIssue({ projectKey: "BPAT", summary: "x", description: doc(), priority: "High", labels: [] }),
    ).rejects.toThrow(ScopeError);
  });
});
