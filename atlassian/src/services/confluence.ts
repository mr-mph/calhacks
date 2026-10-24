import api, { route } from "@forge/api";

const json = { Accept: "application/json", "Content-Type": "application/json" };

interface Space {
  id: string;
  key: string;
}

export async function firstSpace(): Promise<Space | null> {
  const res = await api.asApp().requestConfluence(route`/wiki/api/v2/spaces?type=global&status=current&limit=1`, { headers: json });
  if (!res.ok) return null;
  const body = (await res.json()) as { results?: Space[] };
  return body.results?.[0] ?? null;
}

export async function createPage(spaceId: string, title: string, storage: string): Promise<string> {
  const res = await api.asApp().requestConfluence(route`/wiki/api/v2/pages`, {
    method: "POST",
    headers: json,
    body: JSON.stringify({ spaceId, status: "current", title, body: { representation: "storage", value: storage } }),
  });
  if (!res.ok) throw new Error(`Create Confluence page failed: HTTP ${res.status} ${(await res.text()).slice(0, 300)}`);
  const page = (await res.json()) as { _links?: { base?: string; webui?: string } };
  return `${page._links?.base ?? ""}${page._links?.webui ?? ""}`;
}
