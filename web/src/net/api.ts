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
  SelectionPreview,
  SelectionPreviewRequest,
  SessionResponse,
} from "../protocol";

export type ApiResult<T> =
  | { ok: true; data: T; headers?: Headers }
  | { ok: false; error: ErrorCode | "network" | "persistence_failed" };

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
      headers:
        body === undefined
          ? {}
          : { "Content-Type": body instanceof Blob ? "application/zip" : "application/json" },
    };
    if (body !== undefined) {
      init.body = body instanceof Blob ? body : JSON.stringify(body);
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
  access: () =>
    request<{
      code: string;
      invitation: string;
      requests: readonly { request_id: string; nickname: string; reference: string }[];
    }>("GET", "/api/host/session/access"),
  rotateAccess: (code?: string) =>
    request<{ ok: true }>("POST", "/api/host/session/access", { code: code ?? null }),
  decideAccess: (request_id: string, approve: boolean) =>
    request<{ ok: true }>("POST", "/api/host/session/access/decide", { request_id, approve }),
  sharedCode: () => request<{ code: string }>("GET", "/api/session/access-code"),
  joinAccess: (nickname: string, code: string, invitation: string) =>
    request<
      SessionResponse | { status: "waiting"; request_id: string; token: string; reference: string }
    >("POST", "/api/session/access", { nickname, code, invitation }),
  pollAccess: (request_id: string, token: string) =>
    request<SessionResponse | { status: "waiting" }>("POST", "/api/session/access/poll", {
      request_id,
      token,
    }),
  finishGame: (view: { game: { game_id: string } | null; phase: string }) =>
    request<{ ok: true }>("POST", "/api/host/game/finish", {
      game_id: view.game?.game_id,
      phase: view.phase,
      confirm_unreviewed: true,
    }),
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
  session: (signal?: AbortSignal) =>
    request<SessionResponse>("GET", "/api/session", undefined, signal),
  elevate: (hostPassword: string) =>
    request<HostElevateResponse>("POST", "/api/session/host", { host_password: hostPassword }),
  leave: () => request<{ ok: true }>("POST", "/api/session/leave", {}),
  library: (signal?: AbortSignal) =>
    request<LibraryResponse>("GET", "/api/host/library", undefined, signal),
  diagnostics: () => request<DiagnosticsResponse>("GET", "/api/host/diagnostics"),
  search: (params: URLSearchParams) =>
    request<LibrarySearch>("GET", `/api/host/library/search?${params}`),
  selectionPreview: (body: SelectionPreviewRequest, signal?: AbortSignal) =>
    request<SelectionPreview>("POST", "/api/host/library/selection", body, signal),
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
  importMetadataArchive: (body: Blob) =>
    request<{ accepted: number; issues: { row: number; code: string }[] }>(
      "POST",
      "/api/host/metadata/import-archive",
      body,
    ),
  metadata: () => request<{ version: 1 | 2 | 3; rows: unknown[] }>("GET", "/api/host/metadata"),
  recoveryCode: () => request<{ code: string }>("POST", "/api/session/recovery-code", {}),
  recover: (password: string, code: string) =>
    request<SessionResponse>("POST", "/api/session/recover", { password, code }),
};
