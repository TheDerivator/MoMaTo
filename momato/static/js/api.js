// The JSON API client: paths are relative to the page's base, writes carry the CSRF header (AUTH-1).

const CSRF_COOKIE = "momato_csrf";

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function csrfToken() {
  const pair = document.cookie.split("; ").find((c) => c.startsWith(`${CSRF_COOKIE}=`));
  return pair ? decodeURIComponent(pair.slice(CSRF_COOKIE.length + 1)) : "";
}

/** `api("projects", { params: { q: "x" } })`; resolves to the JSON body, null for 204. */
export async function api(path, { method = "GET", body, params, signal } = {}) {
  const url = new URL(`api/${path}`, document.baseURI);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== null && value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  const response = await fetch(url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "same-origin",
    signal,
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, data?.error ?? "error", data?.message ?? response.statusText);
  }
  return data;
}

/** Fire a write that must outlive the page (it is being closed): no answer is waited for. */
export function sendOnExit(path, { method = "PUT", body } = {}) {
  try {
    fetch(new URL(`api/${path}`, document.baseURI), {
      method,
      keepalive: true,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken(),
      },
      body: JSON.stringify(body),
      credentials: "same-origin",
    }).catch(() => undefined);
  } catch {
    // nothing more can be done while the page goes away
  }
}

/** Upload one file (multipart) to `path`; resolves to the JSON body (RM-2). */
export async function upload(path, file, name) {
  const form = new FormData();
  form.append("file", file, name || file.name || "image.png");
  const response = await fetch(new URL(`api/${path}`, document.baseURI), {
    method: "POST",
    headers: { Accept: "application/json", "X-CSRF-Token": csrfToken() },
    body: form,
    credentials: "same-origin",
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, data?.error ?? "error", data?.message ?? response.statusText);
  }
  return data;
}

/** A readable message for any thrown thing. */
export function messageOf(error) {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Please try again.";
}
