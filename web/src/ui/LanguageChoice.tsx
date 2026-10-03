import { getLanguage, setLanguage, t } from "../i18n";

export function LanguageChoice() {
  return (
    <label className="language-choice">
      <span className="sr-only">{t("settings.language")}</span>
      <select
        aria-label={t("settings.language")}
        value={getLanguage()}
        onChange={(e) => {
          const lang = e.target.value === "en" ? "en" : "fr";
          setLanguage(lang);
          const url = new URL(location.href);
          url.searchParams.set("lang", lang);
          location.assign(url.href);
        }}
      >
        <option value="fr">Français</option>
        <option value="en">English</option>
      </select>
    </label>
  );
}
