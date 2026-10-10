import { useEffect, useRef, useState } from "react";
import * as cmd from "../app/commands";
import { useGame, useUi } from "../app/hooks";
import { t, tCode, useMessage } from "../i18n";
import { api } from "../net/api";
import type {
  HostView,
  LibraryBridge,
  LibraryResponse,
  LibrarySearch,
  LibraryTrack,
  MusicalMetadata,
} from "../protocol";
import { Button, ConfirmDialog, Modal } from "../ui/components";
import { MetadataFieldActions } from "../ui/MetadataFieldActions";
import { AliasEditor } from "../ui/ScoringCriteria";
import { PrivatePreview } from "./PrivatePreview";
import { languageLabel } from "./ThemeSelector";

export function LibraryManager({
  view,

  onSelectionPending,
}: {
  readonly view: HostView;

  readonly onSelectionPending?: (pending: boolean) => void;
}) {
  const [open, setOpen] = useState(false);

  const [sort, setSort] = useState("title");

  const [descending, setDescending] = useState(false);

  const [pageSize, setPageSize] = useState(20);

  const listRegion = useRef<HTMLDivElement>(null);

  const game = useGame();

  const ui = useUi();

  const choices = view.kind === "host_mc" ? (view.mc.manual_choices ?? []) : [];

  const catalogState = view.host.bridges

    .map((bridge) => `${bridge.bridge_id}:${bridge.state}:${bridge.track_count}`)

    .join("|");

  const selectionRevision = view.kind === "host_mc" ? (view.mc.selection_revision ?? 0) : 0;

  const [roundNumber, setRoundNumber] = useState(1);

  const [pendingChoice, setPendingChoice] = useState<{
    number: number;

    bridgeId: string | null;

    trackId: string | null;

    revision: number;

    toastAt: number | null;

    expiresAt: number;
  } | null>(null);

  const choice = choices.find((c) => c.round_number === roundNumber);

  const manualAllowed = view.kind === "host_mc" && view.host.commands.includes("select_track");

  const [library, setLibrary] = useState<LibraryResponse | null>(null);

  const [result, setResult] = useState<LibrarySearch | null>(null);

  const [q, setQuery] = useState("");

  const [bridge, setBridge] = useState("");

  const [folder, setFolder] = useState("");

  const [ext, setExt] = useState("");

  const [availability, setAvailability] = useState("all");

  const [exportOffset, setExportOffset] = useState(0);

  const [exportBusy, setExportBusy] = useState(false);

  const [quality, setQuality] = useState("all");
  const [poolOnly, setPoolOnly] = useState(false);

  const [activation, setActivation] = useState("all");

  const [tag, setTag] = useState("");

  const [linkedTo, setLinkedTo] = useState("");
  const [genre, setGenre] = useState("");
  const [language, setTrackLanguage] = useState("");
  const [yearMin, setYearMin] = useState("");
  const [yearMax, setYearMax] = useState("");

  const activeFilters = [
    q,
    genre,
    language,
    yearMin || yearMax,
    tag,
    linkedTo,
    bridge,
    folder,
    ext,
    availability !== "all",
    activation !== "all",
    quality !== "all",
    poolOnly,
  ].filter(Boolean).length;

  const [offset, setOffset] = useState(0);

  const [revision, setRevision] = useState(0);

  const [error, setError] = useMessage(null);

  const [loading, setLoading] = useState(false);

  const [editing, setEditing] = useState<LibraryTrack | null>(null);

  const [editorDirty, setEditorDirty] = useState(false);

  const [editorSaving, setEditorSaving] = useState(false);

  const [leaveAction, setLeaveAction] = useState<(() => void) | null>(null);

  const [preview, setPreview] = useState<LibraryTrack | null>(null);

  const [mutating, setMutating] = useState(false);

  const [selectedTracks, setSelectedTracks] = useState<ReadonlySet<string>>(new Set());

  const [bulkTags, setBulkTags] = useState("");

  const [bulkLinks, setBulkLinks] = useState("");
  const [bulkGenres, setBulkGenres] = useState("");
  const [bulkLanguages, setBulkLanguages] = useState("");

  const [bulkActivation, setBulkActivation] = useState("");

  const identity = (track: LibraryTrack) => `${track.bridge_id}:${track.track_id}`;

  const guard = (action: () => void) => {
    if (editorSaving || mutating) return;

    if (editorDirty) {
      setLeaveAction(() => action);

      return;
    }

    setEditing(null);

    setPreview(null);

    action();
  };

  useEffect(() => {
    const region = listRegion.current;

    if (!region) return;

    const resize = () => {
      if (!region.clientWidth || editorDirty || editorSaving) return;

      const columns = region.clientWidth >= 860 ? 2 : 1;

      const size = columns * (innerHeight < 600 ? 5 : 10);

      setPageSize((old) => {
        if (old !== size) setOffset((offset) => Math.floor(offset / size) * size);

        return size;
      });
    };

    const observer = new ResizeObserver(resize);

    observer.observe(region);

    window.addEventListener("resize", resize);

    resize();

    return () => {
      observer.disconnect();

      window.removeEventListener("resize", resize);
    };
  }, [editorDirty, editorSaving]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: phase and public PLAY changes invalidate private previews.
  useEffect(() => {
    setPreview(null);
  }, [view.phase, view.play?.play_id]);

  const [notice, setNotice] = useMessage("");

  useEffect(() => {
    if (choices.length && !choices.some((c) => c.round_number === roundNumber)) {
      setRoundNumber(choices[0]?.round_number ?? 1);
    }
  }, [choices, roundNumber]);

  useEffect(() => {
    onSelectionPending?.(pendingChoice !== null);

    return () => onSelectionPending?.(false);
  }, [pendingChoice, onSelectionPending]);

  useEffect(() => {
    if (!pendingChoice) return;

    const confirmed = choices.find((c) => c.round_number === pendingChoice.number);

    if (
      selectionRevision > pendingChoice.revision &&
      confirmed &&
      (pendingChoice.trackId === null
        ? !confirmed.manual
        : confirmed.bridge_id === pendingChoice.bridgeId &&
          confirmed.track_id === pendingChoice.trackId)
    ) {
      setPendingChoice(null);

      setNotice(() => t("manual.saved"));

      setRevision((r) => r + 1);

      return;
    }

    if (ui.toast && ui.toast.at !== pendingChoice.toastAt) {
      setPendingChoice(null);

      const code = ui.toast.code;

      setNotice(() => tCode("error", code));

      return;
    }

    const timer = window.setTimeout(
      () => {
        setPendingChoice(null);

        setNotice(() => t("manual.saveFailed"));
      },

      Math.max(0, pendingChoice.expiresAt - Date.now()),
    );

    return () => window.clearTimeout(timer);
  }, [pendingChoice, choices, selectionRevision, ui.toast, setNotice]);

  const choose = (track: LibraryTrack | null) => {
    if (view.kind !== "host_mc" || !choice || choice.locked || pendingChoice) return;

    setNotice(() => t("manual.saving"));

    setPendingChoice({
      number: roundNumber,

      bridgeId: track?.bridge_id ?? null,

      trackId: track?.track_id ?? null,

      revision: selectionRevision,

      toastAt: ui.toast?.at ?? null,

      expiresAt: Date.now() + 10000,
    });

    game.send(cmd.selectTrack(view, roundNumber, track));
  };

  // biome-ignore lint/correctness/useExhaustiveDependencies: revision explicitly requests a catalog refresh
  useEffect(() => {
    let active = true;

    void api.library().then((r) => {
      if (!active) return;

      if (r.ok) setLibrary(r.data);
      else setError(() => tCode("error", r.error));
    });

    return () => {
      active = false;
    };
  }, [revision, catalogState]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: edits and rescans invalidate the search response
  useEffect(() => {
    let active = true;

    setLoading(true);

    const timer = window.setTimeout(() => {
      if (
        [yearMin, yearMax].some(
          (year) => year !== "" && (!/^\d{4}$/.test(year) || Number(year) < 1000),
        ) ||
        (yearMin !== "" && yearMax !== "" && Number(yearMin) > Number(yearMax))
      ) {
        setLoading(false);
        setResult(null);
        setError(() => t("theme.invalidRange"));
        return;
      }
      const params = new URLSearchParams({
        q,

        bridge,

        folder,

        ext,

        availability,

        activation,

        quality,
        pool_only: String(poolOnly),

        tag,

        linked_to: linkedTo,
        genre,
        language,

        offset: String(offset),

        limit: String(pageSize),

        sort,

        descending: String(descending),
      });

      if (yearMin) params.set("year_min", yearMin);
      if (yearMax) params.set("year_max", yearMax);
      void api.search(params).then((r) => {
        if (!active) return;

        setLoading(false);

        if (r.ok) {
          setResult(r.data);

          if (offset >= r.data.total && offset > 0)
            setOffset(Math.floor(Math.max(0, r.data.total - 1) / pageSize) * pageSize);

          setError(null);
        } else setError(() => tCode("error", r.error));
      });
    }, 250);

    return () => {
      active = false;

      window.clearTimeout(timer);
    };
  }, [
    q,

    sort,

    descending,

    bridge,

    folder,

    ext,

    availability,

    activation,

    quality,
    poolOnly,

    tag,

    linkedTo,
    genre,
    language,
    yearMin,
    yearMax,

    pageSize,

    offset,

    revision,

    selectionRevision,

    catalogState,

    view.round?.state,
  ]);

  const refresh = (updated?: LibraryResponse) => {
    if (updated) setLibrary(updated);

    setRevision((n) => n + 1);

    window.dispatchEvent(new Event("openblindysir:library"));
  };

  const applyBulk = () => {
    const tracks = result?.tracks.filter((track) => selectedTracks.has(identity(track))) ?? [];

    const split = (value: string) =>
      value

        .split(",")

        .map((label) => label.trim())

        .filter(Boolean);

    guard(() => {
      setMutating(true);

      setError(null);

      void (async () => {
        let count = 0;
        const expectedRevision = tracks[0]?.metadata_revision ?? 0;
        let failure: (() => string) | null = null;

        for (const track of tracks) {
          const metadata: MusicalMetadata = {
            ...(bulkTags.trim() ? { tags: [...track.tags, ...split(bulkTags)] } : {}),
            ...(bulkGenres.trim()
              ? { genres: [...(track.genres ?? []), ...split(bulkGenres)] }
              : {}),
            ...(bulkLanguages.trim()
              ? { languages: [...(track.languages ?? []), ...split(bulkLanguages)] }
              : {}),

            ...(bulkLinks.trim() ? { linked_to: [...track.linked_to, ...split(bulkLinks)] } : {}),

            ...(bulkActivation ? { enabled: bulkActivation === "active" } : {}),
          };

          const saved = await api.editMetadata({
            bridge_id: track.bridge_id,

            track_id: track.track_id,

            metadata,
            expected_revision: expectedRevision + count,
          });

          if (!saved.ok) {
            failure = () =>
              saved.error === "stale_command"
                ? t("library.editConflict")
                : tCode("error", saved.error);
            setError(failure);

            break;
          }

          count++;

          setSelectedTracks((old) => {
            const next = new Set(old);

            next.delete(identity(track));

            return next;
          });
        }

        setMutating(false);

        setNotice(
          () =>
            `${t("library.bulkSaved", { count, total: tracks.length })}${failure ? ` · ${failure()}` : ""}`,
        );

        refresh();
      })();
    });
  };

  // biome-ignore lint/correctness/useExhaustiveDependencies: the selection belongs to one filtered page, not the returned object identity.
  useEffect(() => {
    setSelectedTracks(new Set());
  }, [
    offset,

    pageSize,

    q,

    sort,

    descending,

    bridge,

    folder,

    ext,

    availability,

    activation,

    quality,

    tag,

    linkedTo,
    genre,
    language,
    yearMin,
    yearMax,
  ]);

  const filter = (set: (value: string) => void, value: string) => {
    guard(() => {
      set(value);

      setOffset(0);
    });
  };

  const useTheme = () =>
    guard(() => {
      const sources = (library?.bridges ?? [])
        .filter((item) => item.online && (!bridge || item.bridge_id === bridge))
        .map((item) => ({ bridge_id: item.bridge_id, folder_prefix: folder }));
      if (
        game.send(
          cmd.configure(
            view,
            {
              sources,
              selection_filter: {
                query: q,
                genres: genre ? [genre] : [],
                languages: language ? [language] : [],
                tags: tag ? [tag] : [],
                linked_to: linkedTo ? [linkedTo] : [],
                year_min: yearMin ? Number(yearMin) : null,
                year_max: yearMax ? Number(yearMax) : null,
              },
              ...(tag === "Génériques"
                ? {
                    answer_mode: "title",
                    answer_fields: ["title"],
                    clip_seconds: Math.max(
                      view.host.limits.clip_min_s,
                      Math.min(view.host.limits.clip_max_s, 12),
                    ),
                    instructions: t("theme.cartoonInstructions"),
                  }
                : {}),
            },
            false,
          ),
        )
      )
        setOpen(false);
    });

  return (
    <>
      <Button
        onClick={(event) => {
          event.currentTarget.focus();

          setOpen(true);
          // Another host may have edited while this dialog was closed.
          setRevision((revision) => revision + 1);
        }}
      >
        {t("library.manage")}
      </Button>

      <Modal
        open={open}
        title={t("library.manage")}
        onClose={() => {
          if (!pendingChoice && !mutating && !editorSaving) guard(() => setOpen(false));
        }}
      >
        {view.kind === "host_player" && <p className="notice">{t("flow.spoiler")}</p>}

        <div className="stack library-workspace">
          {manualAllowed && (
            <section className="stack manual-picker" aria-label={t("manual.heading")}>
              <strong>{t("manual.heading")}</strong>

              <p className="muted">{t("manual.hint")}</p>

              <label>
                {t("manual.round")}

                <select
                  value={roundNumber}
                  onChange={(e) => setRoundNumber(Number(e.target.value))}
                >
                  {choices.map((c) => (
                    <option key={c.round_number} value={c.round_number}>
                      {t("manual.number", { number: c.round_number })}

                      {c.locked ? ` · ${t("manual.locked")}` : ""}
                    </option>
                  ))}
                </select>
              </label>

              {choice && (
                <p role="status">
                  {choice.manual
                    ? `${t("manual.selected")} ${choice.title || choice.filename || t("manual.unavailable")}`
                    : t("manual.random")}
                </p>
              )}

              {choice?.locked && <p className="muted">{t("manual.lockedHint")}</p>}

              {choice?.error && (
                <p role="alert" className="error">
                  {choice.error === "BRIDGE_OFFLINE"
                    ? t("error.bridge_offline")
                    : t("manual.unavailable")}{" "}
                  {t("manual.replaceHint")}
                </p>
              )}

              <Button
                disabled={!choice?.manual || choice.locked || pendingChoice !== null}
                onClick={() => choose(null)}
              >
                {t("manual.clear")}
              </Button>

              {choices

                .filter((c) => c.manual)

                .map((c) => (
                  <p className="muted" key={c.round_number}>
                    {t("manual.number", { number: c.round_number })} ·{" "}
                    {c.title || c.filename || t("manual.unavailable")}
                    {c.locked ? ` · ${t("manual.locked")}` : ""}
                  </p>
                ))}
            </section>
          )}

          <details className="disclosure advanced-sources">
            <summary>{t("library.advancedSources")}</summary>

            <p className="muted">{t("library.sourcesHint")}</p>

            {library?.bridges.map((b) => (
              <SourceManager key={b.bridge_id} bridge={b} refresh={refresh} />
            ))}

            <p className="muted">{t("library.mountHint")}</p>
          </details>

          {view.phase === "LOBBY" && (view.host.auto_missing_references ?? 0) > 0 && (
            <p className="notice">
              {t("library.preflight", { count: view.host.auto_missing_references ?? 0 })}
            </p>
          )}

          <div className="library-primary-search">
            <label>
              {t("library.search")}

              <input
                type="search"
                value={q}
                maxLength={256}
                onChange={(e) => filter(setQuery, e.target.value)}
              />
            </label>

            <label>
              {t("flow.sort")}

              <select value={sort} onChange={(event) => filter(setSort, event.target.value)}>
                {["title", "artist", "filename", "folder", "year", "genre", "language"].map(
                  (value) => (
                    <option key={value} value={value}>
                      {t(
                        value === "year"
                          ? "theme.yearSort"
                          : value === "genre"
                            ? "theme.genreSort"
                            : value === "language"
                              ? "theme.languageSort"
                              : (`library.${value}` as "library.folder"),
                      )}
                    </option>
                  ),
                )}
              </select>
            </label>

            <label className="folder-option">
              <input
                type="checkbox"
                checked={descending}
                onChange={(event) => {
                  const value = event.target.checked;

                  guard(() => {
                    setDescending(value);

                    setOffset(0);
                  });
                }}
              />

              {t("flow.descending")}
            </label>
          </div>

          <details className="disclosure library-extra-filters">
            <summary>{t("library.moreFilters", { count: activeFilters })}</summary>
            <div className="row wrap theme-shortcuts">
              <Button
                onClick={() =>
                  guard(() => {
                    setGenre("");
                    setTrackLanguage("");
                    setYearMin("");
                    setYearMax("");
                    setTag("Génériques");
                    setLinkedTo("");
                    setQuery("");
                    setOffset(0);
                  })
                }
              >
                {t("theme.cartoons")}
              </Button>
              <Button onClick={() => filter(setGenre, "Pop")}>Pop</Button>
              <Button onClick={() => filter(setGenre, "Rap")}>Rap</Button>
              <Button onClick={() => filter(setTrackLanguage, "fr")}>{t("theme.french")}</Button>
              <Button onClick={() => filter(setTrackLanguage, "en")}>{t("theme.english")}</Button>
              <Button
                onClick={() =>
                  guard(() => {
                    setYearMin("2012");
                    setYearMax("2012");
                    setOffset(0);
                  })
                }
              >
                2012
              </Button>
              <Button
                onClick={() =>
                  guard(() => {
                    setGenre("");
                    setTrackLanguage("");
                    setYearMin("");
                    setYearMax("");
                    setTag("");
                    setLinkedTo("");
                    setQuery("");
                    setBridge("");
                    setFolder("");
                    setExt("");
                    setAvailability("all");
                    setActivation("all");
                    setQuality("all");
                    setPoolOnly(false);
                    setOffset(0);
                  })
                }
              >
                {t("theme.clear")}
              </Button>
            </div>
            <div className="library-filters">
              <label>
                {t("theme.genres")}
                <select value={genre} onChange={(e) => filter(setGenre, e.target.value)}>
                  <option value="">{t("library.all")}</option>
                  {[...new Set([...(result?.genres ?? []), ...(genre ? [genre] : [])])].map((v) => (
                    <option value={v} key={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("theme.languages")}
                <select value={language} onChange={(e) => filter(setTrackLanguage, e.target.value)}>
                  <option value="">{t("library.all")}</option>
                  {[
                    ...new Set([...(result?.languages ?? []), ...(language ? [language] : [])]),
                  ].map((v) => (
                    <option value={v} key={v}>
                      {languageLabel(v)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("theme.yearFrom")}
                <input
                  type="number"
                  min={1000}
                  max={9999}
                  value={yearMin}
                  onChange={(e) => filter(setYearMin, e.target.value)}
                />
              </label>
              <label>
                {t("theme.yearTo")}
                <input
                  type="number"
                  min={1000}
                  max={9999}
                  value={yearMax}
                  onChange={(e) => filter(setYearMax, e.target.value)}
                />
              </label>

              <label className="folder-option">
                <input
                  type="checkbox"
                  checked={poolOnly}
                  onChange={(e) => {
                    const value = e.target.checked;
                    guard(() => {
                      setPoolOnly(value);
                      setOffset(0);
                    });
                  }}
                />
                {t("library.selectedSources")}
              </label>
              <label>
                {t("library.quality")}
                <select value={quality} onChange={(e) => filter(setQuality, e.target.value)}>
                  {["all", "ready", "missing"].map((value) => (
                    <option key={value} value={value}>
                      {t(`library.quality.${value}` as "library.quality.all")}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                {t("library.activation")}

                <select
                  value={activation}
                  onChange={(event) => filter(setActivation, event.target.value)}
                >
                  {["all", "active", "disabled"].map((value) => (
                    <option value={value} key={value}>
                      {t(`library.${value}` as "library.all")}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                {t("library.tags")}

                <select value={tag} onChange={(event) => filter(setTag, event.target.value)}>
                  <option value="">{t("library.all")}</option>

                  {result?.tags?.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                {t("library.linkedTo")}

                <select
                  value={linkedTo}
                  onChange={(event) => filter(setLinkedTo, event.target.value)}
                >
                  <option value="">{t("library.all")}</option>

                  {result?.linked_to?.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                {t("library.bridge")}

                <select value={bridge} onChange={(e) => filter(setBridge, e.target.value)}>
                  <option value="">{t("library.all")}</option>

                  {library?.bridges.map((b) => (
                    <option key={b.bridge_id} value={b.bridge_id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                {t("library.folder")}

                <input
                  value={folder}
                  maxLength={1024}
                  onChange={(e) => filter(setFolder, e.target.value)}
                />
              </label>

              <label>
                {t("library.type")}

                <select value={ext} onChange={(e) => filter(setExt, e.target.value)}>
                  <option value="">{t("library.all")}</option>

                  {[
                    ".mp3",

                    ".flac",

                    ".wav",

                    ".m4a",

                    ".aac",

                    ".ogg",

                    ".oga",

                    ".opus",

                    ".aiff",

                    ".aif",

                    ".wma",

                    ".mp4",

                    ".mov",

                    ".m4v",

                    ".3gp",

                    ".mkv",

                    ".mka",

                    ".webm",

                    ".avi",

                    ".wmv",

                    ".asf",
                  ].map((e) => (
                    <option key={e}>{e}</option>
                  ))}
                </select>
              </label>

              <label>
                {t("library.availability")}

                <select
                  value={availability}
                  onChange={(e) => filter(setAvailability, e.target.value)}
                >
                  {[
                    "all",

                    "available",

                    "unavailable",

                    "online",

                    "offline",

                    "fresh",

                    "used",

                    "reserved",
                  ].map((value) => (
                    <option value={value} key={value}>
                      {t(`library.${value}` as "library.all")}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </details>

          {loading && <p role="status">{t("app.loading")}</p>}

          {error && (
            <p role="alert" className="error">
              {error} <Button onClick={() => guard(() => refresh())}>{t("app.retry")}</Button>
            </p>
          )}

          <div className="row library-result-actions">
            {result && <p role="status">{t("library.results", { count: result.total })}</p>}
            {(view.phase === "LOBBY" || view.phase === "FINAL_RESULTS") && (
              <Button
                kind="primary"
                disabled={
                  loading ||
                  mutating ||
                  editorSaving ||
                  !result?.total ||
                  [yearMin, yearMax].some(
                    (v) =>
                      v !== "" &&
                      (!Number.isInteger(Number(v)) || Number(v) < 1000 || Number(v) > 9999),
                  ) ||
                  (yearMin !== "" && yearMax !== "" && Number(yearMin) > Number(yearMax))
                }
                onClick={useTheme}
              >
                {t("theme.useLibrary")}
              </Button>
            )}
          </div>

          {!loading && result?.total === 0 && <p>{t("library.empty")}</p>}

          <details className="disclosure library-bulk" hidden={selectedTracks.size === 0}>
            <summary>
              {t("library.bulk")} ({selectedTracks.size})
            </summary>

            <p className="muted">{t("library.bulkHint")}</p>

            <div className="grid">
              <label>
                {t("theme.genres")}
                <input
                  value={bulkGenres}
                  maxLength={2048}
                  placeholder={t("theme.genreExamples")}
                  onChange={(e) => setBulkGenres(e.target.value)}
                />
              </label>
              <label>
                {t("theme.languages")}
                <input
                  value={bulkLanguages}
                  maxLength={2048}
                  placeholder={t("theme.languageExamples")}
                  onChange={(e) => setBulkLanguages(e.target.value)}
                />
              </label>
              <label>
                {t("library.tags")}

                <input
                  value={bulkTags}
                  maxLength={2048}
                  onChange={(event) => setBulkTags(event.target.value)}
                />
              </label>

              <label>
                {t("library.linkedTo")}

                <input
                  value={bulkLinks}
                  maxLength={2048}
                  onChange={(event) => setBulkLinks(event.target.value)}
                />
              </label>

              <label>
                {t("library.activation")}

                <select
                  value={bulkActivation}
                  onChange={(event) => setBulkActivation(event.target.value)}
                >
                  <option value="">{t("library.keepActivation")}</option>

                  <option value="active">{t("library.active")}</option>

                  <option value="disabled">{t("library.disabled")}</option>
                </select>
              </label>
            </div>

            <Button
              disabled={
                mutating ||
                loading ||
                editorSaving ||
                !selectedTracks.size ||
                (!bulkTags.trim() &&
                  !bulkLinks.trim() &&
                  !bulkGenres.trim() &&
                  !bulkLanguages.trim() &&
                  !bulkActivation)
              }
              onClick={applyBulk}
            >
              {t("library.bulk")}
            </Button>
          </details>

          <div className="library-list-region" ref={listRegion}>
            <ul className="list library-tracks">
              {result?.tracks.map((track) => (
                <li key={`${track.bridge_id}:${track.track_id}`}>
                  <label className="folder-option">
                    <input
                      type="checkbox"
                      aria-label={t("library.select", { name: track.title || track.filename })}
                      checked={selectedTracks.has(identity(track))}
                      disabled={loading || mutating || editorSaving}
                      onChange={(event) => {
                        const checked = event.target.checked;

                        setSelectedTracks((old) => {
                          const next = new Set(old);

                          if (checked) next.add(identity(track));
                          else next.delete(identity(track));

                          return next;
                        });
                      }}
                    />

                    {t("library.selectTrack")}
                  </label>

                  <div>
                    <strong>{track.title || track.filename}</strong>

                    <p className="muted">
                      {[
                        track.artist,

                        track.folder,

                        library?.bridges.find((b) => b.bridge_id === track.bridge_id)?.name,
                      ]

                        .filter(Boolean)

                        .join(" · ")}
                    </p>

                    <p className="muted">
                      {[
                        track.title ? track.filename : "",

                        track.duration_ms
                          ? `${Math.round(track.duration_ms / 1000)} s`
                          : t("manual.durationUnknown"),

                        track.available ? t("manual.available") : t("manual.unavailable"),

                        track.consumption === "cancelled"
                          ? t("review.cancelledShort")
                          : track.played
                            ? t("manual.played")
                            : "",

                        track.reserved ? t("manual.reserved") : "",
                      ]

                        .filter(Boolean)

                        .join(" · ")}
                    </p>

                    {manualAllowed && !track.in_pool && (
                      <p className="muted">{t("manual.outsideSources")}</p>
                    )}

                    {!!track.missing_references?.length && (
                      <p className="notice">
                        {t("library.missingFields", {
                          fields: track.missing_references
                            .map((key) => t(`review.${key}` as "review.title"))
                            .join(" · "),
                        })}
                      </p>
                    )}

                    {track.enabled === false && (
                      <p className="notice">{t("library.disabledHint")}</p>
                    )}

                    {!!track.genres?.length && (
                      <p className="track-labels">
                        {t("theme.genres")} : {track.genres.join(" · ")}
                      </p>
                    )}
                    {!!track.languages?.length && (
                      <p className="track-labels">
                        {t("theme.languages")} : {track.languages.map(languageLabel).join(" · ")}
                      </p>
                    )}
                    {!!track.tags?.length && (
                      <p className="track-labels">
                        {t("library.tags")} : {track.tags.join(" · ")}
                      </p>
                    )}

                    {!!track.linked_to?.length && (
                      <p className="track-labels">
                        {t("library.linkedTo")} : {track.linked_to.join(" · ")}
                      </p>
                    )}
                  </div>

                  <div className="row wrap">
                    {manualAllowed && (
                      <Button
                        disabled={
                          !choice ||
                          choice.locked ||
                          pendingChoice !== null ||
                          !track.available ||
                          !track.in_pool ||
                          (track.played && !view.host.settings.allow_repeats) ||
                          (track.reserved &&
                            !(
                              choice.bridge_id === track.bridge_id &&
                              choice.track_id === track.track_id
                            ))
                        }
                        onClick={() => choose(track)}
                      >
                        {t("manual.choose", { number: roundNumber })}
                      </Button>
                    )}

                    <Button disabled={mutating} onClick={() => guard(() => setEditing(track))}>
                      {t("ux.editTrack")}
                    </Button>

                    <Button
                      onClick={() => setPreview(track)}
                      disabled={(!track.available && track.enabled !== false) || !!view.play}
                    >
                      {t("library.preview")}
                    </Button>

                    <Button
                      disabled={loading || mutating}
                      onClick={() => {
                        guard(() => {
                          setMutating(true);

                          setError(null);

                          void api

                            .editMetadata({
                              bridge_id: track.bridge_id,

                              track_id: track.track_id,

                              metadata: { enabled: track.enabled === false },
                              expected_revision: track.metadata_revision ?? 0,
                            })

                            .then((result) => {
                              setMutating(false);

                              if (result.ok) {
                                setNotice(() => (track.reserved ? t("library.reservedHint") : ""));

                                refresh();
                              } else
                                setError(() =>
                                  result.error === "stale_command"
                                    ? t("library.editConflict")
                                    : tCode("error", result.error),
                                );
                            });
                        });
                      }}
                    >
                      {t(track.enabled === false ? "library.enable" : "library.disable")}
                    </Button>
                  </div>

                  {open &&
                    preview?.track_id === track.track_id &&
                    preview.bridge_id === track.bridge_id && (
                      <PrivatePreview key={`${track.bridge_id}:${track.track_id}`} track={track} />
                    )}

                  {open &&
                    editing?.track_id === track.track_id &&
                    editing.bridge_id === track.bridge_id && (
                      <MetadataEditor
                        key={`${track.bridge_id}:${track.track_id}`}
                        track={track}
                        onDirty={setEditorDirty}
                        onBusy={setEditorSaving}
                        onCancel={() => guard(() => setEditing(null))}
                        onSaved={() => {
                          setEditorDirty(false);

                          setEditing(null);

                          refresh();
                        }}
                      />
                    )}
                </li>
              ))}
            </ul>
          </div>

          <div className="row wrap library-pagination">
            <Button
              disabled={!offset || loading}
              onClick={() => guard(() => setOffset((n) => Math.max(0, n - pageSize)))}
            >
              {t("library.previous")}
            </Button>

            <Button
              disabled={loading || offset + pageSize >= (result?.total ?? 0)}
              onClick={() => guard(() => setOffset((n) => n + pageSize))}
            >
              {t("library.next")}
            </Button>

            <span role="status">
              {t("flow.page", {
                page: Math.floor(offset / pageSize) + 1,

                total: Math.max(1, Math.ceil((result?.total ?? 0) / pageSize)),
              })}
            </span>

            <label>
              {t("library.pageJump")}

              <input
                type="number"
                min={1}
                max={Math.max(1, Math.ceil((result?.total ?? 0) / pageSize))}
                value={Math.floor(offset / pageSize) + 1}
                onChange={(event) => {
                  const page = Number(event.target.value);

                  if (
                    Number.isInteger(page) &&
                    page >= 1 &&
                    page <= Math.max(1, Math.ceil((result?.total ?? 0) / pageSize))
                  )
                    guard(() => setOffset((page - 1) * pageSize));
                }}
              />
            </label>

            <Button onClick={() => guard(() => refresh())}>{t("library.refresh")}</Button>
          </div>

          <ConfirmDialog
            open={leaveAction !== null}
            title={t("ux.editTrack")}
            message={t("library.discard")}
            onCancel={() => setLeaveAction(null)}
            onConfirm={() => {
              const action = leaveAction;

              setLeaveAction(null);

              setEditorDirty(false);

              setEditing(null);

              setPreview(null);

              action?.();
            }}
          />

          <label>
            {t("library.import")}

            <input
              type="file"
              accept="application/json,application/zip,.json,.zip"
              onChange={async (e) => {
                const file = e.target.files?.[0];

                if (!file) return;

                const archive = file.name.toLowerCase().endsWith(".zip");

                if (file.size > (archive ? 8 : 1) * 1024 * 1024) {
                  setError(() => t("error.payload_too_large"));

                  return;
                }

                let document: unknown;

                try {
                  document = archive ? file : JSON.parse(await file.text());
                } catch {
                  setError(() => t("error.invalid_message"));

                  return;
                }

                guard(() => {
                  setMutating(true);

                  void (
                    archive ? api.importMetadataArchive(file) : api.importMetadata(document)
                  ).then((imported) => {
                    setMutating(false);

                    if (imported.ok) {
                      setNotice(
                        () =>
                          `${t("library.imported", { count: imported.data.accepted })} ${imported.data.issues.map((i) => `${i.row}: ${t(`library.issue.${i.code}` as "library.issue.invalid")}`).join(" · ")}`,
                      );

                      refresh();
                    } else setError(() => tCode("error", imported.error));
                  });
                });
              }}
            />
          </label>

          {notice && <p role="status">{notice}</p>}

          <Button
            disabled={exportBusy}
            onClick={async () => {
              setExportBusy(true);

              try {
                const response = await fetch(`/api/host/metadata/export?offset=${exportOffset}`, {
                  credentials: "same-origin",
                  cache: "no-store",
                });

                if (!response.ok) {
                  setError(() => t("library.exportFailed"));
                  return;
                }

                const url = URL.createObjectURL(await response.blob());

                const link = document.createElement("a");
                link.href = url;
                link.download = `openblindysir-metadata-${exportOffset + 1}.zip`;
                link.click();

                window.setTimeout(() => URL.revokeObjectURL(url), 1000);

                const next = response.headers.get("X-Next-Offset");

                setExportOffset(next ? Number(next) : 0);

                setNotice(() => t(next ? "library.exportMore" : "library.exportDone"));
              } catch {
                setError(() => t("library.exportFailed"));
              } finally {
                setExportBusy(false);
              }
            }}
          >
            {t(exportOffset ? "library.exportNext" : "library.exportMetadata")}
          </Button>

          {view.phase === "IN_GAME" && <p className="muted">{t("review.privateHint")}</p>}
        </div>
      </Modal>
    </>
  );
}

function SourceManager({
  bridge,

  refresh,
}: {
  readonly bridge: LibraryBridge;

  readonly refresh: (updated?: LibraryResponse) => void;
}) {
  const [folder, setFolder] = useState("");

  const [busy, setBusy] = useState(false);

  const [notice, setNotice] = useMessage("");

  const generation = useRef(0);

  const request = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      generation.current++;

      request.current?.abort();
    },

    [],
  );

  const update = async (folders: string[] | null) => {
    const version = ++generation.current;

    setBusy(true);

    const result = await api.sources(bridge.bridge_id, folders);

    if (version !== generation.current) return;

    setNotice(() => (result.ok ? t("library.scanRequested") : tCode("error", result.error)));

    if (result.ok) {
      const deadline = Date.now() + 75000;

      const controller = new AbortController();

      request.current = controller;

      const timeout = window.setTimeout(() => controller.abort(), 75000);

      let confirmed = false;

      let delay = 1000;

      try {
        while (Date.now() < deadline && !controller.signal.aborted) {
          await new Promise<void>((resolve) =>
            window.setTimeout(resolve, Math.min(delay, deadline - Date.now())),
          );

          delay = Math.min(4000, delay * 2);

          if (version !== generation.current) return;

          if (Date.now() >= deadline || controller.signal.aborted) break;

          const status = await api.library(controller.signal);

          if (version !== generation.current) return;

          if (!status.ok) {
            const timedOut = controller.signal.aborted;

            setNotice(() => (timedOut ? t("library.scanTimeout") : tCode("error", status.error)));

            confirmed = true;

            break;
          }

          const current = status.data.bridges.find((b) => b.bridge_id === bridge.bridge_id);

          if (!current?.online) {
            refresh(status.data);

            setNotice(() => t("error.bridge_offline"));

            confirmed = true;

            break;
          }

          const matches =
            folders === null ||
            JSON.stringify([...current.scanned_folders].sort()) ===
              JSON.stringify([...new Set(folders)].sort());

          let revision = 0;

          try {
            revision =
              JSON.parse(status.headers?.get("X-Catalog-Revisions") ?? "{}")[bridge.bridge_id] ?? 0;
          } catch {
            /* A proxy without the completion header cannot confirm a scan. */
          }

          if (revision > result.data.scan_revision && (matches || current.source_error)) {
            refresh(status.data);

            setNotice(() =>
              t(current.source_error ? "library.inaccessible" : "library.scanApplied"),
            );

            confirmed = true;

            break;
          }
        }

        if (!confirmed) setNotice(() => t("library.scanTimeout"));
      } finally {
        window.clearTimeout(timeout);

        if (request.current === controller) request.current = null;
      }
    }

    setBusy(false);
  };

  return (
    <section className="source-card stack">
      <h3>
        {bridge.name} · {bridge.track_count}
      </h3>

      <ul className="list">
        {(bridge.scanned_folders ?? [""]).map((f) => (
          <li className="row wrap" key={f}>
            <span>{f || t("library.root")}</span>

            <Button
              disabled={busy || !bridge.online}
              aria-label={t("library.remove", { folder: f || t("library.root") })}
              onClick={() => void update(bridge.scanned_folders.filter((p) => p !== f))}
            >
              ×
            </Button>
          </li>
        ))}
      </ul>

      <label>
        {t("library.addFolder")}

        <input
          placeholder={t("library.folderPlaceholder")}
          maxLength={1024}
          value={folder}
          onChange={(e) => setFolder(e.target.value)}
        />
      </label>

      <div className="row wrap">
        <Button
          disabled={busy || !bridge.online}
          onClick={() =>
            void update([...new Set([...(bridge.scanned_folders ?? []), folder.trim()])])
          }
        >
          {t("library.add")}
        </Button>

        <Button disabled={busy || !bridge.online} onClick={() => void update(null)}>
          {t("library.refresh")}
        </Button>
      </div>

      {notice && <p role="status">{notice}</p>}

      {bridge.source_error && (
        <p className="error" role="alert">
          {t("library.inaccessible")}
        </p>
      )}
    </section>
  );
}

function MetadataEditor({
  track,

  onSaved,

  onDirty,

  onBusy,

  onCancel,
}: {
  readonly track: LibraryTrack;

  readonly onSaved: () => void;

  readonly onDirty: (dirty: boolean) => void;

  readonly onBusy: (busy: boolean) => void;

  readonly onCancel: () => void;
}) {
  const [draft, setDraft] = useState<MusicalMetadata>({
    cleared_fields: (track.cleared_fields ?? []) as NonNullable<MusicalMetadata["cleared_fields"]>,

    aliases: track.aliases ?? {},

    title: track.title,

    artist: track.artist,

    featuring: track.featuring,

    album: track.album,

    year: track.year,

    tags: track.tags ?? [],
    genres: track.genres ?? [],
    languages: track.languages ?? [],

    linked_to: track.linked_to ?? [],
  });

  const [busy, setBusy] = useState(false);

  const [error, setError] = useMessage("");

  const original = useRef(JSON.stringify(draft));

  const [labels, setLabels] = useState({
    tags: (draft.tags ?? []).join(", "),
    genres: (draft.genres ?? []).join(", "),
    languages: (draft.languages ?? []).join(", "),

    linked_to: (draft.linked_to ?? []).join(", "),
  });

  useEffect(() => {
    onDirty(JSON.stringify(draft) !== original.current || busy);

    onBusy(busy);
  }, [draft, busy, onDirty, onBusy]);

  useEffect(
    () => () => {
      onDirty(false);
      onBusy(false);
    },
    [onDirty, onBusy],
  );

  return (
    <form
      className="stack metadata-editor"
      onSubmit={async (e) => {
        e.preventDefault();

        setBusy(true);

        const r = await api.editMetadata({
          bridge_id: track.bridge_id,

          track_id: track.track_id,

          metadata: draft,

          expected_revision: track.metadata_revision ?? 0,
        });

        setBusy(false);

        if (r.ok) onSaved();
        else
          setError(() =>
            r.error === "stale_command" ? t("library.editConflict") : tCode("error", r.error),
          );
      }}
    >
      <h3>{track.filename}</h3>

      {(["genres", "languages", "tags", "linked_to"] as const).map((key) => (
        <label key={key}>
          {t(
            key === "genres"
              ? "theme.genres"
              : key === "languages"
                ? "theme.languages"
                : key === "tags"
                  ? "library.tags"
                  : "library.linkedTo",
          )}

          <input
            value={labels[key]}
            maxLength={8192}
            placeholder={t(
              key === "genres"
                ? "theme.genreExamples"
                : key === "languages"
                  ? "theme.languageExamples"
                  : key === "tags"
                    ? "library.tagExamples"
                    : "library.linkExamples",
            )}
            onChange={(event) => {
              const value = event.target.value;

              setLabels((old) => ({ ...old, [key]: value }));

              setDraft((old) => ({
                ...old,

                [key]: value

                  .split(",")

                  .map((label) => label.trim())

                  .filter(Boolean),
              }));
            }}
          />

          <small>{t("library.labelsHint")}</small>
        </label>
      ))}

      {(["title", "artist", "featuring", "album"] as const).map((key) => (
        <label key={key}>
          {t(`review.${key}`)}

          <input
            maxLength={256}
            value={draft[key] ?? ""}
            aria-label={t(`review.${key}`)}
            onChange={(e) =>
              setDraft((old) => ({
                ...old,
                [key]: e.target.value,
                cleared_fields: (old.cleared_fields ?? []).filter((field) => field !== key),
              }))
            }
          />

          <MetadataFieldActions field={key} draft={draft} onChange={setDraft} />
        </label>
      ))}

      <label>
        {t("review.year")}

        <input
          type="number"
          min={1000}
          max={9999}
          value={draft.year ?? ""}
          onChange={(e) =>
            setDraft((old) => ({
              ...old,
              year: e.target.value ? Number(e.target.value) : null,
              cleared_fields: (old.cleared_fields ?? []).filter((field) => field !== "year"),
            }))
          }
        />
      </label>

      <MetadataFieldActions field="year" draft={draft} onChange={setDraft} />

      <AliasEditor
        value={draft.aliases ?? {}}
        onChange={(aliases) => setDraft((old) => ({ ...old, aliases }))}
      />

      <Button type="submit" disabled={busy}>
        {t(busy ? "ux.saving" : "hostui.save")}
      </Button>

      <Button disabled={busy} onClick={onCancel}>
        {t("hostui.cancel")}
      </Button>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
