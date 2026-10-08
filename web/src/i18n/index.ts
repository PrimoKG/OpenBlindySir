// Typed messages and a browser-local language preference, shared by all screens.

import { useCallback, useState, useSyncExternalStore } from "react";
import { readLocal, writeLocal } from "../storage";
import { en } from "./en";
import { fr, type MessageKey } from "./fr";

export type { MessageKey } from "./fr";

export type Params = Readonly<Record<string, string | number>>;
export type Dictionary = { readonly [K in MessageKey]: string };

const dictionaries: Readonly<Record<"fr" | "en", Dictionary>> = { fr, en };

function currentLanguage(): "fr" | "en" {
  const requested =
    typeof location === "undefined" ? null : new URLSearchParams(location.search).get("lang");
  if (requested === "fr" || requested === "en") {
    writeLocal("language", requested);
    return requested;
  }
  if (readLocal("language") === "en") return "en";
  return "fr";
}

let language: "fr" | "en" = currentLanguage();
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Subscribe without remounting game/audio controllers or discarding form drafts. */
export function useLanguage(): "fr" | "en" {
  return useSyncExternalStore(subscribe, getLanguage);
}

export function setLanguage(lang: "fr" | "en"): void {
  const changed = language !== lang;
  language = lang;
  writeLocal("language", lang);
  if (typeof document !== "undefined") document.documentElement.lang = lang;
  // A link's initial language must not override the user's choice on refresh.
  if (typeof location !== "undefined" && typeof history !== "undefined") {
    const url = new URL(location.href);
    if (url.searchParams.has("lang")) {
      url.searchParams.delete("lang");
      history.replaceState(history.state, "", url.href);
    }
  }
  if (changed) for (const listener of listeners) listener();
}

export function getLanguage(): "fr" | "en" {
  return language;
}

/** Retain message data in state; resolve it in the currently selected language. */
export function useMessage(initial: string | null) {
  const [value, setValue] = useState<string | null | (() => string)>(initial);
  const setMessage = useCallback(
    (next: string | null | (() => string)) => setValue(() => next),
    [],
  );
  return [typeof value === "function" ? value() : value, setMessage] as const;
}

export function format(template: string, params?: Params): string {
  if (!params) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = params[name];
    return value === undefined ? match : String(value);
  });
}

export function t(key: MessageKey, params?: Params): string {
  return format(dictionaries[language][key], params);
}

/** Recognise an unchanged generated preset even after switching languages. */
export function isTranslation(key: MessageKey, value: string | undefined): boolean {
  return Object.values(dictionaries).some((dictionary) => dictionary[key] === value);
}

/** Translation of a protocol code (error, start blocker, host warning). */
export function tCode(prefix: "error" | "blocker" | "warning", code: string): string {
  const key = `${prefix}.${code}`;
  if (key in fr) {
    return t(key as MessageKey);
  }
  return code;
}
