const API_BASE = "";

export async function apiJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* body wasn't JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}
