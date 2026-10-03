import { useEffect, useRef, useState } from "react";
import * as cmd from "../app/commands";
import { useGame, useUi } from "../app/hooks";
import { t, tCode } from "../i18n";
import { api } from "../net/api";
import type {
  HostView,
  LibraryBridge,
  LibraryResponse,
  LibrarySearch,
  LibraryTrack,
  MusicalMetadata,
} from "../protocol";
import { Button, Modal } from "../ui/components";

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
  const pageSize = 25;
  const game = useGame();
  const ui = useUi();
  const choices = view.kind === "host_mc" ? (view.mc.manual_choices ?? []) : [];
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
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<LibraryTrack | null>(null);
  const [notice, setNotice] = useState("");
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
      setNotice(t("manual.saved"));
      setRevision((r) => r + 1);
      return;
    }
    if (ui.toast && ui.toast.at !== pendingChoice.toastAt) {
      setPendingChoice(null);
      setNotice(tCode("error", ui.toast.code));
      return;
    }
    const timer = window.setTimeout(
      () => {
        setPendingChoice(null);
        setNotice(t("manual.saveFailed"));
      },
      Math.max(0, pendingChoice.expiresAt - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [pendingChoice, choices, selectionRevision, ui.toast]);
  const choose = (track: LibraryTrack | null) => {
    if (view.kind !== "host_mc" || !choice || choice.locked || pendingChoice) return;
    setNotice(t("manual.saving"));
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
      else setError(tCode("error", r.error));
    });
    return () => {
      active = false;
    };
  }, [revision]);
  // biome-ignore lint/correctness/useExhaustiveDependencies: edits and rescans invalidate the search response
  useEffect(() => {
    let active = true;
    setLoading(true);
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({
        q,
        bridge,
        folder,
        ext,
        availability,
        offset: String(offset),
        limit: String(pageSize),
        sort,
        descending: String(descending),
      });
      void api.search(params).then((r) => {
        if (!active) return;
        setLoading(false);
        if (r.ok) {
          setResult(r.data);
          setError(null);
        } else setError(tCode("error", r.error));
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
    offset,
    revision,
    selectionRevision,
    view.round?.state,
  ]);
  const refresh = (updated?: LibraryResponse) => {
    if (updated) setLibrary(updated);
    setRevision((n) => n + 1);
    window.dispatchEvent(new Event("openblindysir:library"));
  };
  const filter = (set: (value: string) => void, value: string) => {
    set(value);
    setOffset(0);
  };
  return (
    <>
      <Button
        onClick={(event) => {
          event.currentTarget.focus();
          setOpen(true);
        }}
      >
        {t("library.manage")}
      </Button>
      <Modal
        open={open}
        title={t("library.manage")}
        onClose={() => {
          if (!pendingChoice) setOpen(false);
        }}
      >
        {view.kind === "host_player" && <p className="notice">{t("flow.spoiler")}</p>}
        <div className="stack">
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
          <p className="muted">{t("library.sourcesHint")}</p>
          {library?.bridges.map((b) => (
            <SourceManager key={b.bridge_id} bridge={b} refresh={refresh} />
          ))}
          <p className="muted">{t("library.mountHint")}</p>
          <div className="library-filters">
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
          <div className="row wrap">
            <label>
              {t("flow.sort")}
              <select value={sort} onChange={(event) => filter(setSort, event.target.value)}>
                {["title", "artist", "filename", "folder"].map((value) => (
                  <option key={value} value={value}>
                    {t(`library.${value}` as "library.folder")}
                  </option>
                ))}
              </select>
            </label>
            <label className="folder-option">
              <input
                type="checkbox"
                checked={descending}
                onChange={(event) => {
                  setDescending(event.target.checked);
                  setOffset(0);
                }}
              />
              {t("flow.descending")}
            </label>
          </div>
          {loading && <p role="status">{t("app.loading")}</p>}
          {error && (
            <p role="alert" className="error">
              {error} <Button onClick={() => refresh()}>{t("app.retry")}</Button>
            </p>
          )}
          {result && <p role="status">{t("library.results", { count: result.total })}</p>}
          {!loading && result?.total === 0 && <p>{t("library.empty")}</p>}
          <ul className="list library-tracks">
            {result?.tracks.map((track) => (
              <li key={`${track.bridge_id}:${track.track_id}`}>
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
                  <Button onClick={() => setEditing(track)}>{t("ux.editTrack")}</Button>
                </div>
              </li>
            ))}
          </ul>
          <div className="row wrap">
            <Button
              disabled={!offset || loading}
              onClick={() => setOffset((n) => Math.max(0, n - pageSize))}
            >
              {t("library.previous")}
            </Button>
            <Button
              disabled={loading || offset + pageSize >= (result?.total ?? 0)}
              onClick={() => setOffset((n) => n + pageSize)}
            >
              {t("library.next")}
            </Button>
            <span role="status">
              {t("flow.page", {
                page: Math.floor(offset / pageSize) + 1,
                total: Math.max(1, Math.ceil((result?.total ?? 0) / pageSize)),
              })}
            </span>
            <Button onClick={() => refresh()}>{t("library.refresh")}</Button>
          </div>
          {editing && (
            <MetadataEditor
              key={`${editing.bridge_id}:${editing.track_id}`}
              track={editing}
              onSaved={() => {
                setEditing(null);
                refresh();
              }}
            />
          )}
          <label>
            {t("library.import")}
            <input
              type="file"
              accept="application/json,.json"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                if (file.size > 1024 * 1024) {
                  setError(t("error.payload_too_large"));
                  return;
                }
                try {
                  const imported = await api.importMetadata(JSON.parse(await file.text()));
                  if (imported.ok) {
                    setNotice(
                      `${t("library.imported", { count: imported.data.accepted })} ${imported.data.issues.map((i) => `${i.row}: ${t(`library.issue.${i.code}` as "library.issue.invalid")}`).join(" · ")}`,
                    );
                    refresh();
                  } else setError(tCode("error", imported.error));
                } catch {
                  setError(t("error.invalid_message"));
                }
              }}
            />
          </label>
          {notice && <p role="status">{notice}</p>}
          <Button
            onClick={async () => {
              const data = await api.metadata();
              if (!data.ok) {
                setError(tCode("error", data.error));
                return;
              }
              const url = URL.createObjectURL(
                new Blob([JSON.stringify(data.data, null, 2)], { type: "application/json" }),
              );
              const link = document.createElement("a");
              link.href = url;
              link.download = "openblindysir-metadata.json";
              link.click();
              window.setTimeout(() => URL.revokeObjectURL(url), 1000);
            }}
          >
            {t("library.exportMetadata")}
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
  const [notice, setNotice] = useState("");
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
    setNotice(result.ok ? t("library.scanRequested") : tCode("error", result.error));
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
            setNotice(
              controller.signal.aborted ? t("library.scanTimeout") : tCode("error", status.error),
            );
            confirmed = true;
            break;
          }
          const current = status.data.bridges.find((b) => b.bridge_id === bridge.bridge_id);
          if (!current?.online) {
            refresh(status.data);
            setNotice(t("error.bridge_offline"));
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
            setNotice(t(current.source_error ? "library.inaccessible" : "library.scanApplied"));
            confirmed = true;
            break;
          }
        }
        if (!confirmed) setNotice(t("library.scanTimeout"));
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
}: {
  readonly track: LibraryTrack;
  readonly onSaved: () => void;
}) {
  const [draft, setDraft] = useState<MusicalMetadata>({
    title: track.title,
    artist: track.artist,
    featuring: track.featuring,
    album: track.album,
    year: track.year,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
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
        });
        setBusy(false);
        if (r.ok) onSaved();
        else setError(tCode("error", r.error));
      }}
    >
      <h3>{track.filename}</h3>
      {(["title", "artist", "featuring", "album"] as const).map((key) => (
        <label key={key}>
          {t(`review.${key}`)}
          <input
            maxLength={256}
            value={draft[key] ?? ""}
            onChange={(e) => setDraft((old) => ({ ...old, [key]: e.target.value }))}
          />
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
            setDraft((old) => ({ ...old, year: e.target.value ? Number(e.target.value) : null }))
          }
        />
      </label>
      <Button type="submit" disabled={busy}>
        {t(busy ? "ux.saving" : "hostui.save")}
      </Button>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
