// HTTP API (spec §8.1). The session cookie is HttpOnly: the client never sees the token.
import type {
  DiagnosticsResponse,
  ErrorCode,
  HostElevateResponse,
  JoinResponse,
  LibraryResponse,
  SessionResponse,
} from "../protocol";

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ErrorCode | "network" };

async function request<T>(method: string, path: string, body?: unknown): Promise<ApiResult<T>> {
  let response: Response;
  try {
    const init: RequestInit = {
      method,
      credentials: "same-origin",
      cache: "no-store",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
    };
    if (body !== undefined) {
      init.body = JSON.stringify(body);
    }
    response = await fetch(path, init);
  } catch {
    return { ok: false, error: "network" };
  }
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (response.ok) {
    return { ok: true, data: payload as T };
  }
  const code = (payload as { error?: ErrorCode } | null)?.error ?? "network";
  return { ok: false, error: code };
}

export const api = {
  join: (password: string, nickname: string) =>
    request<JoinResponse>("POST", "/api/session/join", { password, nickname }),
  session: () => request<SessionResponse>("GET", "/api/session"),
  elevate: (hostPassword: string) =>
    request<HostElevateResponse>("POST", "/api/session/host", { host_password: hostPassword }),
  leave: () => request<{ ok: true }>("POST", "/api/session/leave", {}),
  library: () => request<LibraryResponse>("GET", "/api/host/library"),
  diagnostics: () => request<DiagnosticsResponse>("GET", "/api/host/diagnostics"),
};
