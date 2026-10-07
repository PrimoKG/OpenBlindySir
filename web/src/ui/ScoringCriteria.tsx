import { t } from "../i18n";

export type Criterion = "title" | "artist" | "album" | "year" | "featuring" | "custom";
export type Decision = `${Criterion}_correct`;
export const musicalCriteria = ["title", "artist", "album", "year", "featuring"] as const;

export function criteriaFor(
  rules:
    | { readonly answer_mode?: string; readonly answer_fields?: readonly string[] }
    | null
    | undefined,
): Criterion[] {
  if (rules?.answer_mode === "fields")
    return musicalCriteria.filter((key) => rules.answer_fields?.includes(key));
  if (rules?.answer_mode === "custom") return ["custom"];
  if (rules?.answer_mode === "title") return ["title"];
  if (rules?.answer_mode === "artist") return ["artist"];
  return ["title", "artist"];
}

export function criterionLabel(key: Criterion): string {
  return key === "custom" ? t("flow.customCriterion") : t(`review.${key}`);
}

export function criterionPoints(
  key: Criterion,
  rules: Partial<Record<`${Criterion}_points`, number>> | null | undefined,
): number {
  return rules?.[`${key}_points`] ?? 1;
}

export type AliasValues = Partial<
  Record<"title" | "artist" | "album" | "featuring", readonly string[]>
>;

export function AliasEditor({
  value,
  onChange,
}: {
  readonly value: AliasValues;
  readonly onChange: (next: AliasValues) => void;
}) {
  return (
    <details className="disclosure alias-editor">
      <summary>{t("auto.aliases")}</summary>
      <p className="muted">{t("auto.aliasesHint")}</p>
      {(["title", "artist", "album", "featuring"] as const).map((key) => (
        <label key={key}>
          {t("auto.aliasField", { field: criterionLabel(key) })}
          <textarea
            rows={2}
            maxLength={2055}
            value={(value[key] ?? []).join("\n")}
            onChange={(event) =>
              onChange({ ...value, [key]: event.target.value.split("\n").slice(0, 8) })
            }
          />
        </label>
      ))}
    </details>
  );
}
