// What to do when the game socket closes (spec §8.2 close codes).
import { CloseCode, type ErrorCode } from "../protocol";

export type CloseAction =
  | "reconnect"
  | "superseded"
  | "kicked"
  | "session_ended"
  | "reload"
  | "check";

const POLICY = 1008;

export function closeAction(code: number, lastError: ErrorCode | null): CloseAction {
  if (code === CloseCode.SUPERSEDED) {
    return "superseded";
  }
  if (code === CloseCode.KICKED) {
    return "kicked";
  }
  if (code === CloseCode.SESSION_ENDED) {
    return "session_ended";
  }
  if (code === POLICY && lastError === "protocol_mismatch") {
    return "reload";
  }
  if (code === POLICY) {
    return "check"; // GET /api/session decides: 401 → join screen, else reconnect
  }
  return "reconnect";
}
