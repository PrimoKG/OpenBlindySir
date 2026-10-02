// Local preferences only (volume, drawer, debug); never a token nor an answer.
const PREFIX = "openblindysir:";

export function readLocal(key: string): string | null {
  try {
    return localStorage.getItem(PREFIX + key);
  } catch {
    return null;
  }
}

export function writeLocal(key: string, value: string): void {
  try {
    localStorage.setItem(PREFIX + key, value);
  } catch {
    // storage unavailable (private mode): preferences are simply not remembered
  }
}

export function readSession(key: string): string | null {
  try {
    return sessionStorage.getItem(PREFIX + key);
  } catch {
    return null;
  }
}

export function writeSession(key: string, value: string): void {
  try {
    sessionStorage.setItem(PREFIX + key, value);
  } catch {
    // ignored
  }
}
