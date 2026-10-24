// Atlassian Document Format. Untrusted strings only ever become plain text nodes, so they can't
// produce mentions, macros or links.

export type AdfNode = { type: string; [key: string]: unknown };
export type Inline = string | AdfNode;

export const text = (value: string, marks?: AdfNode[]): AdfNode =>
  marks ? { type: "text", text: value, marks } : { type: "text", text: value };

export const strong = (value: string): AdfNode => text(value, [{ type: "strong" }]);

export const link = (href: string, label = href): AdfNode => text(label, [{ type: "link", attrs: { href } }]);

const inline = (parts: Inline[]): AdfNode[] =>
  parts.filter((p) => p !== "").map((p) => (typeof p === "string" ? text(p) : p));

export const paragraph = (...parts: Inline[]): AdfNode => ({ type: "paragraph", content: inline(parts) });

export const bullets = (items: Inline[][]): AdfNode => ({
  type: "bulletList",
  content: items.map((parts) => ({ type: "listItem", content: [paragraph(...parts)] })),
});

export const panel = (panelType: "info" | "warning" | "error" | "note", ...blocks: AdfNode[]): AdfNode => ({
  type: "panel",
  attrs: { panelType },
  content: blocks,
});

export const doc = (...blocks: AdfNode[]): AdfNode => ({ type: "doc", version: 1, content: blocks });
