/**
 * The one place that knows how to talk to FastAPI. Every function in
 * lib/api/*.ts calls one of get/post/patch here instead of using `fetch`
 * directly, so error handling (turning a non-2xx response into a typed
 * ApiError with the backend's actual message) only has to exist once.
 *
 * Called directly from the browser (Client Components), not through a
 * Next.js server proxy -- see the root README for why, and
 * backend/app/main.py for the CORS configuration that makes this work.
 */
// Trailing slash stripped -- every call site passes `path` starting
// with "/" (e.g. apiGet("/admins")), and api_stack.py's ApiGatewayUrl
// output (what NEXT_PUBLIC_API_BASE_URL is built from in production)
// always ends in "/" itself (HTTP API's default-stage URL format is
// always `https://<id>.execute-api.<region>.amazonaws.com/`) -- left
// un-stripped, every real request became a literal double slash
// (".../admins" -> ".../\/admins"), which API Gateway's routing treats
// as a different, unmatched path and returns a 404 for.
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!res.ok) {
    // FastAPI's error responses (both our own NotFoundError/ConflictError
    // handlers and Pydantic's automatic 422s) put the message in `detail`.
    const body = await res.json().catch(() => null);
    const message =
      (body && typeof body.detail === "string" && body.detail) ||
      `Request failed with status ${res.status}`;
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export function apiGet<T>(path: string, headers?: HeadersInit): Promise<T> {
  return request<T>(path, { method: "GET", headers });
}

export function apiPost<T>(path: string, body?: unknown, headers?: HeadersInit): Promise<T> {
  return request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined, headers });
}

export function apiPatch<T>(path: string, body?: unknown, headers?: HeadersInit): Promise<T> {
  return request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined, headers });
}

export function apiDelete<T>(path: string, headers?: HeadersInit): Promise<T> {
  return request<T>(path, { method: "DELETE", headers });
}

/**
 * Multipart form upload -- distinct from apiPost() because a FormData
 * body must NOT get the `Content-Type: application/json` header
 * request() otherwise always sets; the browser needs to set its own
 * `multipart/form-data; boundary=...` Content-Type, which only happens
 * if this code never sets Content-Type at all. Used by the knowledge
 * base's small-file/non-browser upload path (lib/api/knowledge.ts's
 * uploadDocumentDirect) -- the browser's primary upload path
 * (uploadDocumentViaPresignedUrl) doesn't go through this API's
 * `request()` at all, since its file PUT goes straight to S3.
 */
export async function apiPostForm<T>(path: string, formData: FormData, headers?: HeadersInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { method: "POST", body: formData, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const message =
      (body && typeof body.detail === "string" && body.detail) || `Request failed with status ${res.status}`;
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

/** Builds a query string from an object, dropping null/undefined/empty values.
 * Generic (rather than `Record<string, ...>`) so callers can pass a plain
 * interface without an index signature, e.g. `TicketListFilters`. */
export function toQueryString<T extends object>(params: T): string {
  const entries = Object.entries(params as Record<string, unknown>).filter(
    ([, value]) => value !== undefined && value !== null && value !== ""
  );
  if (entries.length === 0) return "";
  const search = new URLSearchParams(entries.map(([k, v]) => [k, String(v)]));
  return `?${search.toString()}`;
}
