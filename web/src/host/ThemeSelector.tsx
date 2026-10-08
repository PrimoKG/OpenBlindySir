import { useEffect, useId, useState } from "react";
import { getLanguage, t, tCode } from "../i18n";
import { api } from "../net/api";
import type { GameSettings, SelectionPreview, ThemeFilter } from "../protocol";
import { Button } from "../ui/components";

export function emptyTheme(): ThemeFilter {
  return {
    query: "",
    genres: [],
    languages: [],
    tags: [],
    linked_to: [],
    year_min: null,
    year_max: null,
  };
}

// Browser-local presets may predate themes or contain damaged data.
export function readTheme(value: unknown): ThemeFilter | null {
  if (value === undefined) return emptyTheme();
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = value as Record<string, unknown>;
  const query = candidate.query ?? "";
  if (typeof query !== "string" || query.length > 256 || /[\p{C}]/u.test(query)) return null;
  let result = { ...emptyTheme(), query };
  for (const field of ["genres", "languages", "tags", "linked_to"] as const) {
    const labels = candidate[field] ?? [];
    if (
      !Array.isArray(labels) ||
      labels.length > 16 ||
      labels.some(
        (label) =>
          typeof label !== "string" ||
          !label.trim() ||
          label.length > 128 ||
          /[\p{C}]/u.test(label),
      )
    )
      return null;
    result = { ...result, [field]: labels };
  }
  for (const field of ["year_min", "year_max"] as const) {
    const year = candidate[field] ?? null;
    if (
      year !== null &&
      (typeof year !== "number" || !Number.isInteger(year) || year < 1000 || year > 9999)
    )
      return null;
    result = { ...result, [field]: year };
  }
  if (result.year_min != null && result.year_max != null && result.year_min > result.year_max)
    return null;
  return result;
}

export function languageLabel(value: string): string {
  if (value === "und") return t("theme.unknownLanguage");
  if (value === "zxx") return t("theme.instrumental");
  try {
    return new Intl.DisplayNames([getLanguage()], { type: "language" }).of(value) ?? value;
  } catch {
    return value;
  }
}

export function useSelectionPreview(draft: GameSettings, revision: string) {
  const [result, setResult] = useState<SelectionPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const payload = JSON.stringify({
    sources: draft.sources,
    selection_filter: draft.selection_filter ?? emptyTheme(),
  });
  // biome-ignore lint/correctness/useExhaustiveDependencies: catalogue events invalidate the same draft selection.
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    const timer = window.setTimeout(async () => {
      for (let attempt = 0; attempt < 3; attempt++) {
        const response = await api.selectionPreview(JSON.parse(payload), controller.signal);
        if (!active) return;
        if (response.ok) {
          setResult(response.data);
          setError(null);
          setLoading(false);
          return;
        }
        if (response.error !== "rate_limited" || attempt === 2) {
          setResult(null);
          setError(response.error);
          setLoading(false);
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 450));
      }
    }, 350);
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [payload, revision]);
  return { result, loading, error };
}

export function ThemeSelector({
  value,
  facets,
  loading,
  error,
  onChange,
  onQuickTheme,
}: {
  readonly value: ThemeFilter;
  readonly facets: SelectionPreview | null;
  readonly loading: boolean;
  readonly error: string | null;
  readonly onChange: (value: ThemeFilter) => void;
  readonly onQuickTheme: (value: ThemeFilter, cartoons: boolean) => void;
}) {
  const id = useId();
  const [labels, setLabels] = useState<Record<string, string>>({});
  const set = <K extends keyof ThemeFilter>(field: K, next: ThemeFilter[K]) =>
    onChange({ ...value, [field]: next });
  const validRange =
    value.year_min == null || value.year_max == null || value.year_min <= value.year_max;
  const quick = (patch: Partial<ThemeFilter>, cartoons = false) =>
    onQuickTheme({ ...emptyTheme(), ...patch }, cartoons);
  return (
    <section className="theme-selector stack" aria-label={t("theme.title")}>
      <div>
        <h3>{t("theme.title")}</h3>
        <p className="muted">{t("theme.hint")}</p>
      </div>
      <div className="row wrap theme-shortcuts">
        <Button onClick={() => quick({ tags: ["Génériques"] }, true)}>{t("theme.cartoons")}</Button>
        <Button onClick={() => quick({ genres: ["Pop"] })}>Pop</Button>
        <Button onClick={() => quick({ genres: ["Rap"] })}>Rap</Button>
        <Button onClick={() => quick({ languages: ["fr"] })}>{t("theme.french")}</Button>
        <Button onClick={() => quick({ languages: ["en"] })}>{t("theme.english")}</Button>
        <Button onClick={() => quick({ year_min: 2012, year_max: 2012 })}>2012</Button>
        <Button onClick={() => quick({ year_min: 2010, year_max: 2019 })}>
          {t("theme.2010s")}
        </Button>
        <Button onClick={() => onChange(emptyTheme())}>{t("theme.clear")}</Button>
      </div>
      <label>
        {t("theme.query")}
        <input
          type="search"
          value={value.query ?? ""}
          maxLength={256}
          onChange={(e) => set("query", e.target.value)}
        />
      </label>
      <div className="theme-fields">
        {(["genres", "languages", "tags", "linked_to"] as const).map((field) => {
          const selected = value[field] ?? [];
          const add = (label: string) => {
            const next = label.trim();
            if (
              !next ||
              selected.length >= 16 ||
              selected.some((v) => v.toLocaleLowerCase() === next.toLocaleLowerCase())
            )
              return;
            set(field, [...selected, next]);
            setLabels((old) => ({ ...old, [field]: "" }));
          };
          return (
            <div className="stack theme-category" key={field}>
              <label>
                {t(`theme.${field}`)}
                <select
                  value=""
                  onChange={(e) => add(e.target.value)}
                  disabled={(facets?.[field]?.length ?? 0) === 0 || selected.length >= 16}
                >
                  <option value="">{t("theme.add")}</option>
                  {facets?.[field]
                    ?.filter((label) => !selected.includes(label))
                    .map((label) => (
                      <option key={label} value={label}>
                        {field === "languages" ? languageLabel(label) : label}
                      </option>
                    ))}
                </select>
              </label>
              <div className="row theme-custom">
                <input
                  aria-label={t("theme.custom", { field: t(`theme.${field}`) })}
                  maxLength={128}
                  value={labels[field] ?? ""}
                  onChange={(e) => setLabels((old) => ({ ...old, [field]: e.target.value }))}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      add(labels[field] ?? "");
                    }
                  }}
                />
                <Button
                  aria-label={t("theme.addCustom", { field: t(`theme.${field}`) })}
                  disabled={!labels[field]?.trim() || selected.length >= 16}
                  onClick={() => add(labels[field] ?? "")}
                >
                  +
                </Button>
              </div>
              <div className="row wrap theme-chips">
                {selected.map((label) => (
                  <Button
                    key={label}
                    aria-label={t("theme.remove", { value: label })}
                    onClick={() =>
                      set(
                        field,
                        selected.filter((v) => v !== label),
                      )
                    }
                  >
                    {field === "languages" ? languageLabel(label) : label} ×
                  </Button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <div className="row wrap theme-years">
        <label>
          {t("theme.yearFrom")}
          <input
            type="number"
            min={1000}
            max={9999}
            list={`${id}-years`}
            value={value.year_min ?? ""}
            onChange={(e) => set("year_min", e.target.value === "" ? null : Number(e.target.value))}
          />
        </label>
        <label>
          {t("theme.yearTo")}
          <input
            type="number"
            min={1000}
            max={9999}
            list={`${id}-years`}
            value={value.year_max ?? ""}
            onChange={(e) => set("year_max", e.target.value === "" ? null : Number(e.target.value))}
          />
        </label>
        <datalist id={`${id}-years`}>
          {facets?.years.map((year) => (
            <option key={year} value={year} />
          ))}
        </datalist>
      </div>
      {!validRange && (
        <p className="error" role="alert">
          {t("theme.invalidRange")}
        </p>
      )}
      <div className="capacity-card" aria-live="polite" aria-busy={loading}>
        {loading ? (
          <p>{t("theme.loading")}</p>
        ) : error ? (
          <p className="error" role="alert">
            {tCode("error", error)}
          </p>
        ) : (
          facets && (
            <>
              <strong>
                {t("theme.count", { available: facets.available, fresh: facets.fresh })}
              </strong>
              {facets.available === 0 && <p>{t("theme.empty")}</p>}
              {!!facets.unclassified && (
                <p className="muted">{t("theme.incomplete", { count: facets.unclassified })}</p>
              )}
              {!!facets.examples.length && (
                <div className="theme-examples">
                  <span className="muted">{t("theme.examples")}</span>
                  {facets.examples.map((track) => (
                    <span key={`${track.bridge_id}:${track.track_id}`}>
                      {track.title ?? track.filename}
                    </span>
                  ))}
                </div>
              )}
            </>
          )
        )}
      </div>
      <p className="muted">{t("theme.saveHint")}</p>
    </section>
  );
}
