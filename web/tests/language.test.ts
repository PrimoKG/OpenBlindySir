import { afterEach, describe, expect, it, vi } from "vitest";
import { en } from "../src/i18n/en";
import { formatCount, formatSeconds } from "../src/i18n/format";
import { fr } from "../src/i18n/fr";
import { setLanguage, t, tCode } from "../src/i18n/index";

afterEach(() => {
  setLanguage("fr");
  vi.unstubAllGlobals();
});

describe("French and English interface", () => {
  it("has a non-empty translation for every interface message", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(fr).sort());
    for (const [key, value] of Object.entries(en)) expect(value.trim(), key).not.toBe("");
  });

  it("translates feedback and formats numbers in the selected language", () => {
    setLanguage("en");
    expect(tCode("error", "bad_password")).toBe("Wrong password");
    expect(t("finale.reveal", { number: 8 })).toBe("Present round 8");
    expect(formatSeconds(4237)).toBe("4.2 s");
    expect(formatCount(5273)).toBe("5,273");
    setLanguage("fr");
    expect(tCode("error", "bad_password")).toBe("Mot de passe incorrect");
    expect(formatSeconds(4237)).toBe("4,2 s");
    expect(formatCount(5273)).toBe("5 273");
  });

  it("keeps switching usable when browser storage is unavailable", () => {
    vi.stubGlobal("localStorage", {
      setItem() {
        throw new Error("storage unavailable");
      },
    });
    expect(() => setLanguage("en")).not.toThrow();
    expect(t("round.answerLabel")).toBe("Your answer");
  });
});
