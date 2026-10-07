import { setLanguage, t, useLanguage } from "../i18n";

export function LanguageChoice() {
  const language = useLanguage();
  return (
    <fieldset className="language-choice" aria-label={t("settings.language")}>
      <legend className="sr-only">{t("settings.language")}</legend>
      <button
        type="button"
        lang="fr"
        aria-label="Français"
        aria-pressed={language === "fr"}
        onClick={() => setLanguage("fr")}
      >
        FR
      </button>
      <button
        type="button"
        lang="en"
        aria-label="English"
        aria-pressed={language === "en"}
        onClick={() => setLanguage("en")}
      >
        EN
      </button>
    </fieldset>
  );
}
