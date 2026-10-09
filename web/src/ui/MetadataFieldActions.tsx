import { useState } from "react";
import { t } from "../i18n";
import type { MusicalMetadata } from "../protocol";
import { Button } from "./components";

type Field = "title" | "artist" | "featuring" | "album" | "year";

/** Empty text inherits; clearing is explicit so imported/tag values cannot return. */
export function MetadataFieldActions({
  field,
  draft,
  onChange,
}: {
  readonly field: Field;
  readonly draft: MusicalMetadata;
  readonly onChange: (draft: MusicalMetadata) => void;
}) {
  const [advanced, setAdvanced] = useState(false);
  const cleared = draft.cleared_fields?.includes(field);
  const change = (remove: boolean) =>
    onChange({
      ...draft,
      [field]: null,
      cleared_fields: [
        ...(draft.cleared_fields ?? []).filter((key) => key !== field),
        ...(remove ? [field] : []),
      ],
    });
  return (
    <span className="metadata-field-actions">
      <Button aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>
        {t("repair.referenceOptions")}
      </Button>
      {advanced && (
        <>
          <small>{t(cleared ? "library.referenceCleared" : "library.emptyInherits")}</small>
          <Button onClick={() => change(false)}>{t("library.inherit")}</Button>
          <Button onClick={() => change(true)}>{t("library.clearReference")}</Button>
        </>
      )}
    </span>
  );
}
