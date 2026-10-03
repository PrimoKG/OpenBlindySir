// HTTP API (spec §8.1). The session cookie is HttpOnly: the client never sees the token.
import type {
  Compatibility,
  DiagnosticsResponse,
  ErrorCode,
  GameRecord,
  HistoryResponse,
  HostElevateResponse,
  JoinResponse,
  LibraryResponse,
  LibrarySearch,
  MetadataEdit,
  SessionResponse,
} from "../protocol";

export type ApiResult<T> =
  | { ok: true; data: T; headers?: Headers }
  | { ok: false; error: ErrorCode | "network" };

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<ApiResult<T>> {
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
    if (signal) init.signal = signal;
    response = await fetch(path, init);
  } catch {
    return { ok: false, error: "network" };
  }
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    return { ok: false, error: "network" };
  }
  if (response.ok) {
    return { ok: true, data: payload as T, headers: response.headers };
  }
  const code = (payload as { error?: ErrorCode } | null)?.error ?? "network";
  return { ok: false, error: code };
}

export const api = {
  compatibility: () => request<Compatibility>("GET", "/api/compatibility"),
  history: () => request<HistoryResponse>("GET", "/api/host/history"),
  historyRecord: (id: string) =>
    request<GameRecord>("GET", `/api/host/history/${encodeURIComponent(id)}`),
  deleteHistory: (id?: string) =>
    request<{ ok: true }>(
      "DELETE",
      id ? `/api/host/history/${encodeURIComponent(id)}` : "/api/host/history",
      { confirm: true },
    ),
  revokeBridge: (id: string) =>
    request<{ ok: true }>("POST", `/api/host/bridges/${encodeURIComponent(id)}/revoke`, {
      confirm: true,
    }),
  join: (password: string, nickname: string) =>
    request<JoinResponse>("POST", "/api/session/join", { password, nickname }),
  session: () => request<SessionResponse>("GET", "/api/session"),
  elevate: (hostPassword: string) =>
    request<HostElevateResponse>("POST", "/api/session/host", { host_password: hostPassword }),
  leave: () => request<{ ok: true }>("POST", "/api/session/leave", {}),
  library: (signal?: AbortSignal) =>
    request<LibraryResponse>("GET", "/api/host/library", undefined, signal),
  diagnostics: () => request<DiagnosticsResponse>("GET", "/api/host/diagnostics"),
  search: (params: URLSearchParams) =>
    request<LibrarySearch>("GET", `/api/host/library/search?${params}`),
  sources: (bridge_id: string, folders: string[] | null) =>
    request<{ ok: true; scan_revision: number }>("POST", "/api/host/library/sources", {
      bridge_id,
      folders,
    }),
  editMetadata: (body: MetadataEdit) => request<{ ok: true }>("PUT", "/api/host/metadata", body),
  importMetadata: (body: unknown) =>
    request<{ accepted: number; issues: { row: number; code: string }[] }>(
      "POST",
      "/api/host/metadata/import",
      body,
    ),
  metadata: () => request<{ version: 1; rows: unknown[] }>("GET", "/api/host/metadata"),
  recoveryCode: () => request<{ code: string }>("POST", "/api/session/recovery-code", {}),
  recover: (password: string, code: string) =>
    request<SessionResponse>("POST", "/api/session/recover", { password, code }),
};
