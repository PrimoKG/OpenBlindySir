// Minimal i18n: typed keys, {name} placeholders. French in V0.1 (spec patch 2);
// "?lang=en" is accepted for development only.
import { en } from "./en";
import { fr, type MessageKey } from "./fr";

export type { MessageKey } from "./fr";

export type Params = Readonly<Record<string, string | number>>;
export type Dictionary = { readonly [K in MessageKey]: string };

const dictionaries: Readonly<Record<"fr" | "en", Dictionary>> = { fr, en };

function currentLanguage(): "fr" | "en" {
  if (
    typeof location !== "undefined" &&
    new URLSearchParams(location.search).get("lang") === "en"
  ) {
    return "en";
  }
  return "fr";
}

let language: "fr" | "en" = currentLanguage();

export function setLanguage(lang: "fr" | "en"): void {
  language = lang;
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

/** Translation of a protocol code (error, start blocker, host warning). */
export function tCode(prefix: "error" | "blocker" | "warning", code: string): string {
  const key = `${prefix}.${code}`;
  if (key in fr) {
    return t(key as MessageKey);
  }
  return code;
}
