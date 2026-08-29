export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

export async function api<T = any>(
  path: string,
  opts: { method?: string; body?: unknown } = {},
): Promise<T> {
  const res = await fetch(path, {
    method: opts.method ?? "GET",
    credentials: "same-origin",
    headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    /* пустое тело */
  }
  if (!res.ok) {
    throw new ApiError(res.status, data?.detail ?? res.statusText);
  }
  return data as T;
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const d: any = e.detail;
    if (typeof d === "string") return d;
    if (d?.warnings) return (d.warnings as string[]).join("; ");
    if (Array.isArray(d)) return d.map((x: any) => x.msg ?? String(x)).join("; ");
    return JSON.stringify(d);
  }
  return String(e);
}
