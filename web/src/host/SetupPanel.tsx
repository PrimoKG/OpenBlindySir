import { type ReactNode, useEffect, useId, useState } from "react";
import * as cmd from "../app/commands";
import { useGame, useUi } from "../app/hooks";
import { t, tCode, useMessage } from "../i18n";
import { api } from "../net/api";
import type {
  FolderNode,
  GameSettings,
  HostView,
  LibraryResponse,
  SettingsPatch,
} from "../protocol";
import { readLocal, writeLocal } from "../storage";
import { Button, Tabs } from "../ui/components";
import {
  criteriaFor,
  criterionLabel,
  criterionPoints,
  musicalCriteria,
} from "../ui/ScoringCriteria";

export function selectedCapacity(
  library: LibraryResponse | null,
  selected: ReadonlySet<string>,
  repeats: boolean,
): number {
  const count = (node: FolderNode, bridge: string): number =>
    selected.has(`${bridge}|${node.prefix}`)
      ? repeats
        ? (node.available_count ?? node.track_count)
        : (node.fresh_count ?? node.track_count)
      : node.children.reduce((sum, child) => sum + count(child, bridge), 0);
  return (
    library?.bridges.reduce(
      (sum, bridge) => sum + (bridge.online ? count(bridge.root, bridge.bridge_id) : 0),
      0,
    ) ?? 0
  );
}

type Preset = { name: string; settings: GameSettings };
function loadPresets(): Preset[] {
  try {
    const value = JSON.parse(readLocal("selections") ?? "[]");
    return Array.isArray(value)
      ? value
          .filter(
            (p) =>
              typeof p?.name === "string" &&
              p.name.length <= 40 &&
              Array.isArray(p?.settings?.sources) &&
              p.settings.sources.every(
                (s: { bridge_id?: unknown; folder_prefix?: unknown } | null) =>
                  s && typeof s.bridge_id === "string" && typeof s.folder_prefix === "string",
              ) &&
              ["rounds", "clip_seconds", "answer_grace_s"].every(
                (field) => typeof p.settings[field] === "number",
              ),
          )
          .slice(0, 20)
      : [];
  } catch {
    return [];
  }
}

export function settingsKey(settings: GameSettings): string {
  const sources = [...settings.sources].sort((a, b) =>
    `${a.bridge_id}|${a.folder_prefix}`.localeCompare(`${b.bridge_id}|${b.folder_prefix}`),
  );
  return JSON.stringify(
    Object.fromEntries(
      Object.entries({ ...settings, sources }).sort(([a], [b]) => a.localeCompare(b)),
    ),
  );
}

export function SetupPanel({
  view,
  onDirtyChange,
  players,
  advanced,
}: {
  readonly view: HostView;
  readonly onDirtyChange?: (dirty: boolean) => void;
  readonly players?: ReactNode;
  readonly advanced?: ReactNode;
}) {
  const tabId = useId();
  const [tab, setTab] = useState("music");
  const tabs = ["music", "rules", "rhythm", "players", "advanced"].map((id) => ({
    id,
    label: t(`flow.${id}` as "flow.music"),
  }));
  const game = useGame();
  const ui = useUi();
  const saved = view.host.settings;
  const [draft, setDraft] = useState<GameSettings>(saved);
  const [library, setLibrary] = useState<LibraryResponse | null>(null);
  const [error, setError] = useMessage(null);
  const [retry, setRetry] = useState(0);
  const [pending, setPending] = useState(false);
  const [presets, setPresets] = useState<Preset[]>(loadPresets);
  const [presetName, setPresetName] = useState("");
  const [folderQuery, setFolderQuery] = useState("");
  const key = `${view.host.bridge.state}:${view.host.bridge.track_count}:${retry}`;
  useEffect(() => {
    const refresh = () => setRetry((n) => n + 1);
    window.addEventListener("openblindysir:library", refresh);
    return () => window.removeEventListener("openblindysir:library", refresh);
  }, []);
  useEffect(() => {
    let active = true;
    if (key)
      void api.library().then((result) => {
        if (!active) return;
        if (result.ok) {
          setLibrary(result.data);
          setError(null);
        } else setError(() => tCode("error", result.error));
      });
    return () => {
      active = false;
    };
  }, [key, setError]);
  const dirty = settingsKey(draft) !== settingsKey(saved);
  useEffect(() => {
    onDirtyChange?.(dirty || pending);
  }, [dirty, pending, onDirtyChange]);
  useEffect(() => {
    if (!dirty) setPending(false);
  }, [dirty]);
  useEffect(() => {
    if (ui.toast) setPending(false);
  }, [ui.toast]);
  useEffect(() => {
    if (!pending) return;
    const timeout = window.setTimeout(() => {
      setPending(false);
      setError(() => t("ux.saveTimeout"));
    }, 10000);
    return () => window.clearTimeout(timeout);
  }, [pending, setError]);
  const set = <K extends keyof GameSettings>(field: K, value: GameSettings[K]) =>
    setDraft((old) => ({ ...old, [field]: value }));
  const selected = new Set(draft.sources.map((s) => `${s.bridge_id}|${s.folder_prefix}`));
  const capacity = selectedCapacity(library, selected, draft.allow_repeats);
  const fresh = selectedCapacity(library, selected, false);
  const tooMany = !draft.allow_repeats && draft.rounds > capacity;
  const limits = view.host.limits;
  const valid =
    Number.isInteger(draft.rounds) &&
    draft.rounds >= 1 &&
    draft.rounds <= 200 &&
    Number.isInteger(draft.clip_seconds) &&
    draft.clip_seconds >= limits.clip_min_s &&
    draft.clip_seconds <= limits.clip_max_s &&
    Number.isInteger(draft.answer_grace_s) &&
    draft.answer_grace_s >= 0 &&
    draft.answer_grace_s <= 120 &&
    Number.isInteger(draft.intermission_s ?? 2) &&
    (draft.intermission_s ?? 2) >= 0 &&
    (draft.intermission_s ?? 2) <= 10 &&
    criteriaFor(draft).length > 0 &&
    criteriaFor(draft).reduce((sum, key) => sum + criterionPoints(key, draft), 0) <= 1000 &&
    !(draft.scoring_mode === "auto" && draft.answer_mode === "custom") &&
    Number.isInteger(draft.acceptance_threshold ?? 90) &&
    (draft.acceptance_threshold ?? 90) >= 80 &&
    (draft.acceptance_threshold ?? 90) <= 100 &&
    criteriaFor(draft)
      .map((key) => criterionPoints(key, draft))
      .every((p) => Number.isInteger(p) && p >= 0 && p <= 1000);
  const save = (start: boolean) => {
    if (valid && game.send(cmd.configure(view, draft as SettingsPatch, start))) setPending(true);
  };
  const toggle = (bridge_id: string, folder_prefix: string) => {
    const checked = draft.sources.some(
      (s) => s.bridge_id === bridge_id && s.folder_prefix === folder_prefix,
    );
    set(
      "sources",
      checked
        ? draft.sources.filter(
            (s) => s.bridge_id !== bridge_id || s.folder_prefix !== folder_prefix,
          )
        : [...draft.sources, { bridge_id, folder_prefix }],
    );
  };
  const checkbox = (
    field:
      | "auto_advance"
      | "auto_start"
      | "allow_repeats"
      | "normalize_audio"
      | "avoid_silence"
      | "balance_folders",
    label: string,
  ) => (
    <label className="folder-option">
      <input
        type="checkbox"
        checked={draft[field] ?? field !== "balance_folders"}
        onChange={(e) => set(field, e.target.checked)}
      />
      {label}
    </label>
  );
  return (
    <form
      className="stack setup"
      onSubmit={(e) => {
        e.preventDefault();
        save(false);
      }}
    >
      <Tabs id={tabId} tabs={tabs} value={tab} onChange={setTab} />
      <section
        className="stack"
        role="tabpanel"
        id={`${tabId}-panel-rhythm`}
        aria-labelledby={`${tabId}-rhythm`}
        hidden={tab !== "rhythm"}
      >
        {checkbox("auto_advance", t("flow.autoAdvance"))}
        <label>
          {t("flow.gap")}
          <input
            type="number"
            min={0}
            max={10}
            value={draft.intermission_s ?? 2}
            onChange={(event) => set("intermission_s", Number(event.target.value))}
          />
        </label>
        <p className="muted">{t("flow.rhythmHint")}</p>
        <div className="setup-fields">
          <label>
            {t("hostui.rounds")}
            <input
              type="number"
              min={1}
              max={200}
              value={draft.rounds}
              onChange={(e) => set("rounds", Number(e.target.value))}
            />
          </label>
          <label>
            {t("hostui.clipSeconds")}
            <input
              type="number"
              min={limits.clip_min_s}
              max={limits.clip_max_s}
              value={draft.clip_seconds}
              onChange={(e) => set("clip_seconds", Number(e.target.value))}
            />
          </label>
        </div>
        <label>
          {t("hostui.grace")}
          <input
            type="number"
            min={0}
            max={120}
            value={draft.answer_grace_s}
            onChange={(e) => set("answer_grace_s", Number(e.target.value))}
          />
        </label>
      </section>
      <section
        className="stack"
        role="tabpanel"
        id={`${tabId}-panel-rules`}
        aria-labelledby={`${tabId}-rules`}
        hidden={tab !== "rules"}
      >
        <label>
          {t("ux.answerMode")}
          <select
            value={draft.answer_mode ?? "both"}
            onChange={(e) =>
              setDraft((old) => ({
                ...old,
                answer_mode: e.target.value,
                scoring_mode: e.target.value === "custom" ? "manual" : old.scoring_mode,
              }))
            }
          >
            <option value="both">{t("ux.modeBoth")}</option>
            <option value="title">{t("ux.modeTitle")}</option>
            <option value="artist">{t("ux.modeArtist")}</option>
            <option value="custom">{t("ux.modeCustom")}</option>
            <option value="fields">{t("auto.fields")}</option>
          </select>
        </label>
        <div className="setup-fields">
          <label hidden={!criteriaFor(draft).includes("title")}>
            {t("ux.titlePoints")}
            <input
              type="number"
              min={0}
              max={1000}
              value={draft.title_points ?? 1}
              onChange={(e) => set("title_points", Number(e.target.value))}
            />
          </label>
          <label hidden={!criteriaFor(draft).includes("artist")}>
            {t("ux.artistPoints")}
            <input
              type="number"
              min={0}
              max={1000}
              value={draft.artist_points ?? 1}
              onChange={(e) => set("artist_points", Number(e.target.value))}
            />
          </label>
        </div>
        {draft.answer_mode === "fields" && (
          <fieldset className="stack">
            <legend>{t("auto.fields")}</legend>
            <div className="row wrap">
              {musicalCriteria.map((key) => (
                <label key={key} className="folder-option">
                  <input
                    type="checkbox"
                    checked={
                      draft.answer_fields?.includes(key) ?? ["title", "artist"].includes(key)
                    }
                    onChange={(event) =>
                      set(
                        "answer_fields",
                        event.target.checked
                          ? [...(draft.answer_fields ?? ["title", "artist"]), key]
                          : (draft.answer_fields ?? ["title", "artist"]).filter(
                              (field) => field !== key,
                            ),
                      )
                    }
                  />
                  {criterionLabel(key)}
                </label>
              ))}
            </div>
            <div className="setup-fields">
              {(["album", "year", "featuring"] as const)
                .filter((key) => criteriaFor(draft).includes(key))
                .map((key) => (
                  <label key={key}>
                    {t("auto.points", { field: criterionLabel(key) })}
                    <input
                      type="number"
                      min={0}
                      max={1000}
                      value={criterionPoints(key, draft)}
                      onChange={(event) => set(`${key}_points`, Number(event.target.value))}
                    />
                  </label>
                ))}
            </div>
          </fieldset>
        )}
        <label>
          {t("auto.mode")}
          <select
            value={draft.scoring_mode ?? "manual"}
            disabled={draft.answer_mode === "custom"}
            onChange={(event) => set("scoring_mode", event.target.value as "manual" | "auto")}
          >
            <option value="manual">{t("auto.manual")}</option>
            <option value="auto">{t("auto.enabled")}</option>
          </select>
        </label>
        {draft.scoring_mode === "auto" && (
          <>
            <label>
              {t("auto.threshold")}
              <input
                type="number"
                min={80}
                max={100}
                value={draft.acceptance_threshold ?? 90}
                onChange={(event) => set("acceptance_threshold", Number(event.target.value))}
              />
            </label>
            <p className="muted">{t("auto.hint")}</p>
            {!dirty && !!view.host.auto_missing_references && (
              <p className="notice">
                {t("auto.preflight", { count: view.host.auto_missing_references })}
              </p>
            )}
          </>
        )}
        <label>
          {t("ux.instructions")}
          <textarea
            rows={2}
            maxLength={500}
            value={draft.instructions ?? ""}
            onChange={(e) => set("instructions", e.target.value)}
          />
        </label>
        <label>
          {t("ux.capturedPolicy")}
          <select
            value={draft.captured_policy ?? "manual"}
            onChange={(e) => set("captured_policy", e.target.value)}
          >
            <option value="manual">{t("ux.capturedManual")}</option>
            <option value="zero">{t("ux.capturedZero")}</option>
          </select>
        </label>
        {draft.answer_mode === "custom" && (
          <label>
            {t("flow.customPoints")}
            <input
              type="number"
              min={0}
              max={1000}
              value={draft.custom_points ?? 1}
              onChange={(event) => set("custom_points", Number(event.target.value))}
            />
          </label>
        )}
      </section>
      <section
        className="stack"
        role="tabpanel"
        id={`${tabId}-panel-music`}
        aria-labelledby={`${tabId}-music`}
        hidden={tab !== "music"}
      >
        <h3>{t("hostui.library")}</h3>
        <p className="muted">
          {view.host.bridge.state === "ONLINE"
            ? t("hostui.bridgeOnline")
            : t("hostui.bridgeOffline")}
        </p>
        <p className="muted">{t("hostui.libraryHint")}</p>
        <Button type="button" onClick={() => setRetry((n) => n + 1)}>
          {t("library.refresh")}
        </Button>
        {error && (
          <p className="error" role="alert">
            {error} <Button onClick={() => setRetry((n) => n + 1)}>{t("app.retry")}</Button>
          </p>
        )}
        {!library && !error && <p role="status">{t("hostui.libraryLoading")}</p>}
        <label>
          {t("library.searchFolders")}
          <input
            type="search"
            value={folderQuery}
            onChange={(e) => setFolderQuery(e.target.value)}
          />
        </label>
        {library?.bridges.map((bridge) => (
          <ul className="tree" key={bridge.bridge_id}>
            <Folder
              node={bridge.root}
              bridgeId={bridge.bridge_id}
              selected={selected}
              toggle={toggle}
              query={folderQuery}
            />
          </ul>
        ))}
        {library?.bridges.length === 0 && <p>{t("hostui.libraryEmpty")}</p>}
        <div className="capacity-card" role="status">
          <strong>{t("ux.capacity", { count: fresh, rounds: draft.rounds })}</strong>
          <p className="muted">{t("ux.sessionNoRepeat")}</p>
        </div>
        {checkbox("allow_repeats", t("hostui.allowRepeats"))}
        {tooMany && capacity > 0 && (
          <div className="notice">
            <p>{t("ux.insufficientTracks", { count: capacity, rounds: draft.rounds })}</p>
            <Button onClick={() => set("rounds", capacity)}>
              {t("ux.reduceRounds", { count: capacity })}
            </Button>
          </div>
        )}
      </section>
      <section
        className="stack"
        role="tabpanel"
        id={`${tabId}-panel-advanced`}
        aria-labelledby={`${tabId}-advanced`}
        hidden={tab !== "advanced"}
      >
        <details className="disclosure" open>
          <summary>{t("hostui.advanced")}</summary>
          <div className="stack">
            {checkbox("auto_start", t("hostui.autoStart"))}
            {checkbox("normalize_audio", t("ux.normalize"))}
            {checkbox("avoid_silence", t("ux.avoidSilence"))}
            {checkbox("balance_folders", t("library.balance"))}
          </div>
        </details>
        {(library?.issues?.length ?? 0) > 0 && (
          <details className="disclosure">
            <summary>{t("ux.libraryIssues")}</summary>
            <ul>
              {library?.issues?.map((issue) => (
                <li key={`${issue.bridge_id}:${issue.filename}`}>
                  {issue.filename} — {tCode("error", issue.code)}
                </li>
              ))}
            </ul>
          </details>
        )}
        <details className="disclosure">
          <summary>{t("ux.presets")}</summary>
          <div className="stack">
            <label>
              {t("ux.presetName")}
              <input
                maxLength={40}
                value={presetName}
                onChange={(e) => setPresetName(e.target.value)}
              />
            </label>
            <Button
              disabled={!presetName.trim() || !valid}
              onClick={() => {
                const next = [
                  ...presets.filter((p) => p.name !== presetName.trim()),
                  { name: presetName.trim(), settings: draft },
                ].slice(-20);
                setPresets(next);
                writeLocal("selections", JSON.stringify(next));
                setPresetName("");
              }}
            >
              {t("ux.savePreset")}
            </Button>
            <p className="muted">{t("ux.presetLocal")}</p>
            {presets.map((preset) => (
              <div className="row wrap" key={preset.name}>
                <Button onClick={() => setDraft({ ...draft, ...preset.settings } as GameSettings)}>
                  {preset.name}
                </Button>
                <Button
                  aria-label={t("ux.deletePreset", { name: preset.name })}
                  onClick={() => {
                    const next = presets.filter((p) => p.name !== preset.name);
                    setPresets(next);
                    writeLocal("selections", JSON.stringify(next));
                  }}
                >
                  ×
                </Button>
              </div>
            ))}
          </div>
        </details>
        {advanced}
      </section>
      <section
        className="stack"
        role="tabpanel"
        id={`${tabId}-panel-players`}
        aria-labelledby={`${tabId}-players`}
        hidden={tab !== "players"}
      >
        {players}
      </section>
      {draft.answer_mode === "both" &&
        (draft.title_points ?? 1) + (draft.artist_points ?? 1) > 1000 && (
          <p className="error" role="alert">
            {t("flow.scaleBound")}
          </p>
        )}
      {!valid && (
        <p role="alert" className="error">
          {t("ux.settingsInvalid", { min: limits.clip_min_s, max: limits.clip_max_s })}
        </p>
      )}
      {view.host.start_blockers
        .filter((b) => (b !== "no_sources" && b !== "pool_exhausted") || (!dirty && capacity === 0))
        .map((b) => (
          <p className="notice" key={b}>
            {tCode("blocker", b)}
          </p>
        ))}
      {capacity === 0 && library && <p className="notice">{t("ux.noPlayableTracks")}</p>}
      <div className="setup-footer stack">
        <strong>
          {t("flow.summary", {
            rounds: draft.rounds,
            seconds: draft.clip_seconds,
            players: view.players.filter((p) => !p.spectator && (!p.is_host || view.me.participant))
              .length,
          })}
        </strong>
        <div className="row wrap setup-actions">
          <Button type="submit" disabled={!dirty || !valid || pending}>
            {t("hostui.save")}
          </Button>
          <Button
            kind="primary"
            disabled={
              !valid ||
              pending ||
              capacity === 0 ||
              tooMany ||
              view.host.start_blockers.includes("no_competitors")
            }
            onClick={() => save(true)}
          >
            {pending ? t("ux.saving") : dirty ? t("ux.saveAndStart") : t("hostui.start")}
          </Button>
        </div>
        <p className="muted" role="status">
          {dirty ? t("hostui.unsaved") : t("hostui.saved")}
        </p>
      </div>
    </form>
  );
}

function Folder(props: {
  readonly node: FolderNode;
  readonly bridgeId: string;
  readonly selected: ReadonlySet<string>;
  readonly toggle: (bridge: string, prefix: string) => void;
  readonly query: string;
}) {
  const contains = (node: FolderNode): boolean =>
    `${node.name} ${node.prefix}`.toLocaleLowerCase().includes(props.query.toLocaleLowerCase()) ||
    node.children.some(contains);
  if (props.query && !contains(props.node)) return null;
  return (
    <li>
      <label className="folder-option">
        <input
          type="checkbox"
          checked={props.selected.has(`${props.bridgeId}|${props.node.prefix}`)}
          onChange={() => props.toggle(props.bridgeId, props.node.prefix)}
        />
        <span>
          {props.node.name}{" "}
          <small className="muted">
            {t("flow.freshCount", {
              fresh: props.node.fresh_count ?? props.node.track_count,
              total: props.node.available_count ?? props.node.track_count,
            })}
          </small>
        </span>
      </label>
      {props.node.children.length > 0 && (
        <ul>
          {props.node.children.map((node) => (
            <Folder key={node.prefix} {...props} node={node} />
          ))}
        </ul>
      )}
    </li>
  );
}
