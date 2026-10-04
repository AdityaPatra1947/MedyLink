export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}
let csrfToken = "";
let csrfPending: Promise<void> | undefined;
let refreshPending: Promise<Response> | undefined;

async function csrf() {
  if (csrfToken) return;
  if (!csrfPending) csrfPending = fetch("/api/v1/auth/csrf/", { credentials: "same-origin", cache: "no-store" })
    .then(async response => { if (!response.ok) throw new ApiError("The service is unavailable. Please try again.", response.status); csrfToken = (await response.json()).csrfToken; })
    .finally(() => { csrfPending = undefined; });
  await csrfPending;
}

function errorText(body: unknown): string {
  if (typeof body === "string") return body;
  if (Array.isArray(body)) return body.map(errorText).join(" ");
  if (body && typeof body === "object") {
    const data = body as Record<string, unknown>;
    if (data.errors) return errorText(data.errors);
    if (data.detail) return errorText(data.detail);
    return Object.entries(data).filter(([key]) => !["code", "request_id"].includes(key))
      .map(([key, value]) => `${key.replaceAll("_", " ")}: ${errorText(value)}`).join(" ");
  }
  return "The request could not be completed. Please try again.";
}

export async function api<T = Record<string, unknown>>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const method = options.method || "GET";
  const mutation = !["GET", "HEAD", "OPTIONS"].includes(method);
  if (mutation) await csrf();
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (mutation) headers.set("X-CSRFToken", csrfToken);
  let response: Response;
  try { response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: "same-origin", cache: "no-store" }); }
  catch { throw new ApiError("Cannot reach MedyLink. Check your connection and try again.", 0); }
  const canRefresh = !path.startsWith("/auth/") || path === "/auth/me/";
  if (response.status === 401 && retry && canRefresh) {
    await csrf();
    if (!refreshPending) refreshPending = fetch("/api/v1/auth/refresh/", {
      method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrfToken }, cache: "no-store",
    }).finally(() => { refreshPending = undefined; });
    const refreshed = await refreshPending;
    if (refreshed.ok) return api<T>(path, options, false);
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && canRefresh && typeof window !== "undefined") window.dispatchEvent(new Event("medylink:session-expired"));
    throw new ApiError(body ? errorText(body) : `Request failed (${response.status}). Please try again.`, response.status);
  }
  return body as T;
}
export function post<T = Record<string, unknown>>(path: string, data: unknown = {}) {
  return api<T>(path, { method: "POST", body: JSON.stringify(data) });
}
export function list<T>(data: T[] | { results: T[] } | null | undefined): T[] {
  return Array.isArray(data) ? data : data?.results || [];
}
export function message(error: unknown) { return error instanceof Error ? error.message : "Something went wrong. Please try again."; }
export function values(form: HTMLFormElement): Record<string, string> {
  return Object.fromEntries(Array.from(new FormData(form).entries()).filter(([, value]) => typeof value === "string")) as Record<string, string>;
}
export function date(value?: string | null) {
  return value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(new Date(value)) : "—";
}
export function dateTime(value?: string | null) {
  return value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}
