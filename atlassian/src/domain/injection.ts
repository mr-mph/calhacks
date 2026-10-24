export interface InjectionFinding {
  rule: string;
  match: string;
}

const RULES: ReadonlyArray<{ rule: string; pattern: RegExp }> = [
  { rule: "override-instructions", pattern: /\b(ignore|disregard|forget|override)\b[^.]{0,40}\b(instructions?|rules?|prompts?|guardrails?)\b/i },
  { rule: "role-change", pattern: /\b(you are now|act as|system prompt|developer mode|new instructions?)\b/i },
  { rule: "assign-request", pattern: /\b(re)?assign\b[^.]{0,40}\b(to|me)\b/i },
  { rule: "visibility-change", pattern: /\b(make|set|share)\b[^.]{0,30}\b(public|everyone|anonymous|external)\b/i },
  { rule: "priority-change", pattern: /\b(set|change|raise|lower|drop|bump)\b[^.]{0,25}\bpriority\b/i },
  { rule: "destructive-request", pattern: /\b(delete|remove|close|resolve|transition|archive)\b[^.]{0,30}\b(issues?|tickets?|comments?|projects?|incidents?)\b/i },
  { rule: "other-project", pattern: /\b[Pp]roject\s*(key)?\s*[=:]?\s*(?!BPAT\b)[A-Z][A-Z0-9]{1,9}\b/ },
  { rule: "credential-request", pattern: /\b(api[\s_-]?key|token|password|secret|credentials?)\b/i },
  { rule: "jira-markup", pattern: /\[~[^\]]*\]|\{\{|<\s*\/?\s*(script|a|img|iframe)\b/i },
  { rule: "link-in-text", pattern: /\bhttps?:\/\/\S+/i },
];

export function detectInjection(...texts: string[]): InjectionFinding[] {
  return texts.flatMap((text) =>
    RULES.flatMap(({ rule, pattern }) => {
      const m = pattern.exec(text);
      return m ? [{ rule, match: m[0].slice(0, 80) }] : [];
    }),
  );
}
