// Host interface: a stable toolbar opens optional parameter modals.
// Buttons shown = view.host.commands: the client never recomputes game rules.
import { useCallback, useEffect, useId, useState } from "react";
import * as cmd from "../app/commands";
import { useGame, useUi } from "../app/hooks";
import { t, tCode } from "../i18n";
import { formatDelta, formatLate } from "../i18n/format";
import { api } from "../net/api";
import { nameOf, PlayerApp } from "../player/PlayerApp";
import { PlayerHistory } from "../player/Recap";
import type { HostView } from "../protocol";
import { readLocal, writeLocal } from "../storage";
import { AudioBadge, Button, ConfirmDialog, Modal, Tabs } from "../ui/components";
import { NumericDraft } from "../ui/NumericDraft";
import { BridgeConnections } from "./BridgeConnections";
import { LibraryManager } from "./LibraryManager";
import { Invite, LibraryIssues, Participation, PartyHistory } from "./PartyTools";
import { ReviewRound } from "./ReviewRound";
import { SetupPanel } from "./SetupPanel";

export function HostApp(props: { readonly view: HostView }) {
  const { view } = props;
  return (
    <PlayerApp view={view}>
      <Drawer view={view} />
    </PlayerApp>
  );
}

function Drawer({ view }: { readonly view: HostView }) {
  const [openPhase, setOpenPhase] = useState<HostView["phase"] | null>(null);
  const open = openPhase === view.phase;
  const setOpen = (value: boolean) => setOpenPhase(value ? view.phase : null);
  const [dirty, setDirty] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [generation, setGeneration] = useState(0);
  const tabId = useId();
  const [tab, setTab] = useState("actions");
  const [selecting, setSelecting] = useState(false);
  const game = useGame();
  const ui = useUi();
  const can = (name: string) => view.host.commands.includes(name);
  // Close obsolete dialogs without dismissing one opened for the new phase.
  useEffect(() => {
    setOpenPhase((previous) => (previous === view.phase ? previous : null));
    setDirty(false);
    setDiscard(false);
  }, [view.phase]);
  const close = () => {
    if (dirty) setDiscard(true);
    else setOpen(false);
  };
  const tabs = ["actions", "rhythm", "players", "advanced"].map((id) => ({
    id,
    label: t(`flow.${id}` as "flow.actions"),
  }));
  return (
    <aside
      className="host-console stack"
      id="host-controls"
      tabIndex={-1}
      aria-label={t("hostui.drawer")}
    >
      {view.session.persistence_status === "failed" && (
        <p className="error" role="alert">
          {t("ux.persistenceFailed")}
        </p>
      )}
      {view.session.recovered && <p className="notice">{t("ux.sessionRecovered")}</p>}
      <fieldset className="row wrap host-toolbar" disabled={ui.socket !== "open" || selecting}>
        <legend className="sr-only">{t("hostui.drawer")}</legend>
        {can("pause") && (
          <Button onClick={() => game.send(cmd.roundCmd(view, "pause"))}>{t("ux.pause")}</Button>
        )}
        {can("resume") && (
          <Button kind="primary" onClick={() => game.send(cmd.roundCmd(view, "resume"))}>
            {t("ux.resume")}
          </Button>
        )}
        <Button
          kind={view.phase === "LOBBY" ? "primary" : "secondary"}
          onClick={(event) => {
            event.currentTarget.focus();
            setOpen(true);
          }}
        >
          {t(view.phase === "LOBBY" ? "flow.prepare" : "flow.parameters")}
        </Button>
        {(view.phase !== "IN_GAME" || view.kind === "host_mc") && (
          <LibraryManager view={view} onSelectionPending={setSelecting} />
        )}
      </fieldset>
      {view.phase !== "LOBBY" && <Warnings view={view} />}
      {view.kind === "host_mc" && view.phase === "IN_GAME" && <McPanel view={view} />}
      {view.phase === "LOBBY" && <Invite />}
      {view.phase === "FINAL_SCORE_REVIEW" && <FinalReview view={view} />}
      {view.phase === "FINAL_RESULTS" && (
        <>
          <EndActions view={view} />
          <PartyHistory view={view} />
        </>
      )}
      <Modal
        open={open}
        title={t(view.phase === "LOBBY" ? "flow.prepare" : "flow.parameters")}
        onClose={close}
      >
        <fieldset className="stack host" disabled={ui.socket !== "open" || selecting}>
          <legend className="sr-only">{t("flow.parameters")}</legend>
          {view.phase === "LOBBY" ? (
            <SetupPanel
              key={`${view.game?.game_id ?? "lobby"}:${generation}`}
              view={view}
              onDirtyChange={setDirty}
              players={<Participation view={view} />}
              advanced={
                <>
                  <ModeSwitch view={view} />
                  <SessionControls view={view} />
                  <BridgeConnections view={view} />
                  <PartyHistory view={view} />
                  <PlayerOps view={view} />
                  <Diagnostics />
                </>
              }
            />
          ) : (
            <>
              <p className="notice">{t("flow.now")}</p>
              <p className="muted">{t("flow.frozen")}</p>
              <Tabs id={tabId} tabs={tabs} value={tab} onChange={setTab} />
              <section
                role="tabpanel"
                id={`${tabId}-panel-actions`}
                aria-labelledby={`${tabId}-actions`}
                hidden={tab !== "actions"}
                className="stack"
              >
                {view.phase === "IN_GAME" && <RoundControls view={view} />}
                <SessionControls view={view} />
              </section>
              <section
                role="tabpanel"
                id={`${tabId}-panel-rhythm`}
                aria-labelledby={`${tabId}-rhythm`}
                hidden={tab !== "rhythm"}
                className="stack"
              >
                <RhythmControls view={view} />
              </section>
              <section
                role="tabpanel"
                id={`${tabId}-panel-players`}
                aria-labelledby={`${tabId}-players`}
                hidden={tab !== "players"}
                className="stack"
              >
                <PlayerOps view={view} />
              </section>
              <section
                role="tabpanel"
                id={`${tabId}-panel-advanced`}
                aria-labelledby={`${tabId}-advanced`}
                hidden={tab !== "advanced"}
                className="stack"
              >
                <ModeSwitch view={view} />
                <LibraryIssues view={view} />
                <PartyHistory view={view} />
                {view.kind === "host_mc" && <BridgeConnections view={view} />}
                <Diagnostics />
              </section>
            </>
          )}
        </fieldset>
      </Modal>
      <ConfirmDialog
        open={discard}
        title={t("flow.discardTitle")}
        message={t("flow.discard")}
        onCancel={() => setDiscard(false)}
        onConfirm={() => {
          setDiscard(false);
          setDirty(false);
          setGeneration((n) => n + 1);
          setOpen(false);
        }}
      />
    </aside>
  );
}

function RhythmControls({ view }: { readonly view: HostView }) {
  const send = useSend();
  const settings = view.host.settings;
  const allowed = view.host.commands.includes("configure");
  return (
    <section className="stack">
      <label className="folder-option">
        <input
          type="checkbox"
          disabled={!allowed}
          checked={settings.auto_advance ?? true}
          onChange={(event) => send(cmd.configure(view, { auto_advance: event.target.checked }))}
        />
        {t("flow.autoAdvance")}
      </label>
      <label>
        {t("flow.gap")}
        <select
          disabled={!allowed}
          value={settings.intermission_s ?? 2}
          onChange={(event) =>
            send(cmd.configure(view, { intermission_s: Number(event.target.value) }))
          }
        >
          {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
      <p className="muted">{t("flow.rhythmHint")}</p>
    </section>
  );
}

function useSend() {
  const game = useGame();
  return useCallback((msg: Parameters<typeof game.send>[0]) => game.send(msg), [game]);
}

function ModeSwitch(props: { readonly view: HostView }) {
  const { view } = props;
  const send = useSend();
  const mc = view.kind === "host_mc";
  return (
    <div className="host-mode">
      <strong>{mc ? t("hostui.modeMc") : t("hostui.modePlayer")}</strong>
      {view.round?.state !== "REVIEW" && view.phase !== "FINAL_SCORE_REVIEW" && (
        <p className="muted">{mc ? t("hostui.modeHintMc") : t("hostui.modeHintPlayer")}</p>
      )}
      <details className="mode-options">
        <summary>{t("hostui.modeSettings")}</summary>
        <Button
          disabled={!view.host.commands.includes("set_mode")}
          onClick={() => send(cmd.setMode(view, mc ? "player" : "mc"))}
        >
          {mc ? t("hostui.switchToPlayer") : t("hostui.switchToMc")}
        </Button>
        {!view.host.commands.includes("set_mode") && (
          <p className="muted">{t(mc ? "ux.modeUnavailable" : "ux.modeAfterAnswers")}</p>
        )}
      </details>
    </div>
  );
}

function Warnings(props: { readonly view: HostView }) {
  const { host } = props.view;
  if (host.warnings.length === 0 && host.start_blockers.length === 0) {
    return null;
  }
  return (
    <ul className="warnings" role="status">
      {host.start_blockers.map((b) => (
        <li key={`b-${b}`}>⚠ {tCode("blocker", b)}</li>
      ))}
      {host.warnings.map((w) => (
        <li key={`w-${w}`}>⚠ {tCode("warning", w)}</li>
      ))}
    </ul>
  );
}

function RoundControls(props: { readonly view: HostView }) {
  const { view } = props;
  const send = useSend();
  const can = (name: string) => view.host.commands.includes(name);
  const [confirmEnd, setConfirmEnd] = useState<"score" | "abandon" | null>(null);
  const check = view.host.ready_check;
  const exhausted = view.round?.state === "QUEUED" && view.round.wait_reason === "pool_exhausted";
  return (
    <section className="stack round-controls">
      {exhausted && (
        <div className="stack empty-pool">
          <h2>{t("ux.noPlayableTracks")}</h2>
          <p>{t("ux.poolRecovery")}</p>
          <Button kind="primary" onClick={() => send(cmd.configure(view, { allow_repeats: true }))}>
            {t("ux.enableRepeats")}
          </Button>
          <Button onClick={() => setConfirmEnd("score")}>{t("hostui.toFinal")}</Button>
        </div>
      )}
      {(check || ["replay", "stop", "add_time", "close", "next", "to_final_review"].some(can)) && (
        <h2>{t("hostui.nextAction")}</h2>
      )}
      {check && (
        <p>
          {t("hostui.readyCheck", { ready: check.ready, expected: check.expected })}{" "}
          {check.can_force && (
            <Button onClick={() => send(cmd.roundCmd(view, "force_start"))}>
              {t("hostui.forceStart")}
            </Button>
          )}
        </p>
      )}
      <div className="row wrap">
        {can("pause") && (
          <Button onClick={() => send(cmd.roundCmd(view, "pause"))}>{t("ux.pause")}</Button>
        )}
        {can("resume") && (
          <Button kind="primary" onClick={() => send(cmd.roundCmd(view, "resume"))}>
            {t("ux.resume")}
          </Button>
        )}
        {can("replay") && (
          <Button onClick={() => send(cmd.replay(view))}>{t("hostui.replay")}</Button>
        )}
        {can("stop") && <Button onClick={() => send(cmd.stop(view))}>{t("hostui.stop")}</Button>}
        {can("add_time") && (
          <Button onClick={() => send(cmd.addTime(view))}>{t("hostui.addTime")}</Button>
        )}
        {can("close") && (
          <Button onClick={() => send(cmd.roundCmd(view, "close"))}>{t("hostui.close")}</Button>
        )}
        {can("next") && (
          <Button kind="primary" onClick={() => send(cmd.roundCmd(view, "next"))}>
            {t("hostui.next")}
          </Button>
        )}
        {can("to_final_review") && (
          <Button kind="primary" onClick={() => send(cmd.roundCmd(view, "to_final_review"))}>
            {t("hostui.toFinal")}
          </Button>
        )}
      </div>
      {(can("skip") || can("undo_publish") || can("end_game")) && (
        <details className="disclosure">
          <summary>{t("hostui.roundOptions")}</summary>
          <div className="stack">
            {can("skip") && (
              <Button onClick={() => send(cmd.roundCmd(view, "skip"))}>{t("hostui.skip")}</Button>
            )}
            {can("undo_publish") && (
              <Button onClick={() => send(cmd.undoPublish(view))}>{t("hostui.undo")}</Button>
            )}
            {can("end_game") && (
              <Button kind="danger" onClick={() => setConfirmEnd("abandon")}>
                {t("hostui.endAbandon")}
              </Button>
            )}
          </div>
        </details>
      )}
      <ConfirmDialog
        title={t(confirmEnd === "abandon" ? "hostui.endAbandon" : "session.stop")}
        open={confirmEnd !== null}
        message={confirmEnd === "abandon" ? t("session.abandonHint") : t("session.stopHint")}
        onConfirm={() => {
          if (confirmEnd) {
            send(cmd.endGame(view, confirmEnd));
          }
          setConfirmEnd(null);
        }}
        onCancel={() => setConfirmEnd(null)}
      />
    </section>
  );
}

function FinalReview(props: { readonly view: HostView }) {
  const { view } = props;
  const send = useSend();
  const rows = view.host.final_review ?? [];
  const [confirm, setConfirm] = useState(false);
  const [detail, setDetail] = useState<string | null>(null);
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());
  const [pending, setPending] = useState<Map<string, string>>(new Map());
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState(false);
  const [roundBusy, setRoundBusy] = useState(false);
  useEffect(() => {
    setPending((old) => {
      const next = new Map(old);
      for (const row of rows)
        if (next.get(row.player_id) === JSON.stringify([row.draft_delta, row.draft_note ?? ""]))
          next.delete(row.player_id);
      return next.size === old.size ? old : next;
    });
  }, [rows]);
  useEffect(() => {
    if (!pending.size) return;
    const timer = window.setTimeout(() => {
      setPending(new Map());
      setSaveError(true);
    }, 10000);
    return () => window.clearTimeout(timer);
  }, [pending]);
  const setCorrection = (pid: string, value: number) => {
    const row = rows.find((item) => item.player_id === pid);
    const note = value ? (notes[pid] ?? row?.draft_note ?? "").trim() : "";
    if (row?.draft_delta === value && (row.draft_note ?? "") === note) {
      setSaveError(false);
      setNotes((old) => {
        const next = { ...old };
        delete next[pid];
        return next;
      });
      return true;
    }
    const sent = send(
      cmd.finalSet(pid, value, note || null, {
        delta: row?.draft_delta ?? 0,
        note: row?.draft_note ?? null,
      }),
    );
    setSaveError(!sent);
    if (sent) {
      setPending((old) => new Map(old).set(pid, JSON.stringify([value, note])));
      setNotes((old) => {
        const next = { ...old };
        delete next[pid];
        return next;
      });
    }
    return sent;
  };
  const resetCorrections = () => {
    const sent = send(cmd.finalReset());
    setSaveError(!sent);
    if (sent) {
      setNotes({});
      setPending(
        new Map(
          rows
            .filter((row) => row.draft_delta !== 0)
            .map((row) => [row.player_id, JSON.stringify([0, ""])]),
        ),
      );
    }
  };
  const saving =
    busy.size > 0 || pending.size > 0 || roundBusy || Object.keys(notes).length > 0 || saveError;
  const rounds = view.host.review_rounds ?? [];
  const [selected, setSelected] = useState(
    () => readLocal(`review:${view.game?.game_id}`) ?? rounds[0]?.round_id ?? "",
  );
  const [query, setQuery] = useState("");
  const [onlyUnchecked, setOnlyUnchecked] = useState(false);
  const active = rounds.find((r) => r.round_id === selected) ?? rounds[0];
  const index = active ? rounds.indexOf(active) : 0;
  const unchecked = rounds
    .filter((r) => r.included)
    .reduce((sum, r) => sum + r.answers.filter((a) => !a.reviewed).length, 0);
  const choose = (id: string) => {
    setSelected(id);
    writeLocal(`review:${view.game?.game_id}`, id);
  };
  const corrections = rows.filter((r) => r.draft_delta !== 0);
  const teams = new Map<string, number>();
  for (const row of rows) {
    const team = view.players.find((p) => p.id === row.player_id)?.team;
    if (team) teams.set(team, (teams.get(team) ?? 0) + row.score_after);
  }
  return (
    <section className="stack final-review">
      <h2>{t("final.title")}</h2>
      <p className="muted">{t("review.privateHint")}</p>
      <p role="status">{t("review.remaining", { count: unchecked })}</p>
      <div className="global-review-layout">
        <nav className="review-navigation" aria-label={t("review.rounds")}>
          <label>
            {t("library.search")}
            <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          <label className="folder-option">
            <input
              type="checkbox"
              checked={onlyUnchecked}
              onChange={(event) => setOnlyUnchecked(event.target.checked)}
            />
            {t("flow.onlyUnchecked")}
          </label>
          <Button
            disabled={roundBusy}
            onClick={() => {
              const next = [...rounds.slice(index + 1), ...rounds.slice(0, index + 1)].find(
                (round) => round.included && round.answers.some((row) => !row.reviewed),
              );
              if (next) choose(next.round_id);
            }}
          >
            {t("flow.nextUnchecked")}
          </Button>
          <ul className="list">
            {rounds
              .filter((r) =>
                `${r.number} ${r.track?.display_name ?? ""} ${r.track?.title ?? ""} ${r.track?.artist ?? ""}`
                  .toLocaleLowerCase()
                  .includes(query.toLocaleLowerCase()),
              )
              .filter(
                (r) => !onlyUnchecked || (r.included && r.answers.some((row) => !row.reviewed)),
              )
              .map((r) => (
                <li key={r.round_id}>
                  <Button
                    disabled={roundBusy}
                    aria-current={r.round_id === active?.round_id ? "step" : undefined}
                    onClick={() => choose(r.round_id)}
                  >
                    {r.number}. {r.track?.title ?? r.track?.display_name ?? "—"} ·{" "}
                    {r.included
                      ? `${r.answers.filter((a) => a.reviewed).length}/${r.answers.length}`
                      : t("review.cancelledShort")}
                  </Button>
                </li>
              ))}
          </ul>
        </nav>
        <div className="stack">
          <div className="row wrap">
            <Button
              disabled={roundBusy || index === 0}
              onClick={() => choose(rounds[index - 1]?.round_id ?? "")}
            >
              {t("review.previous")}
            </Button>
            <strong>
              {active
                ? `${t("ux.historyRound", { number: active.number })} · ${index + 1}/${rounds.length}`
                : t("review.empty")}
            </strong>
            <Button
              disabled={roundBusy || index >= rounds.length - 1}
              onClick={() => choose(rounds[index + 1]?.round_id ?? "")}
            >
              {t("hostui.next")}
            </Button>
          </div>
          {active && (
            <ReviewRound key={active.round_id} round={active} view={view} onBusy={setRoundBusy} />
          )}
        </div>
      </div>
      {teams.size > 0 && (
        <table className="table provisional-teams">
          <caption>{t("review.teamTotals")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("ux.team")}</th>
              <th scope="col">{t("final.after")}</th>
            </tr>
          </thead>
          <tbody>
            {[...teams]
              .sort((a, b) => b[1] - a[1])
              .map(([team, total]) => (
                <tr key={team}>
                  <td>{team}</td>
                  <td>{total}</td>
                </tr>
              ))}
          </tbody>
        </table>
      )}
      <table className="table final-table">
        <caption className="sr-only">{t("final.title")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("reveal.player")}</th>
            <th scope="col">{t("final.before")}</th>
            <th scope="col">{t("final.correction")}</th>
            <th scope="col">{t("final.after")}</th>
            <th scope="col">{t("final.detail")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.player_id}>
              <td className="final-player">{nameOf(view, row.player_id)}</td>
              <td className="final-before">{row.score_before}</td>
              <td className="final-correction">
                <div className="score-controls">
                  <Button
                    disabled={
                      busy.has(row.player_id) ||
                      pending.has(row.player_id) ||
                      row.draft_delta <= -1000
                    }
                    aria-label={t("final.decrease", { name: nameOf(view, row.player_id) })}
                    onClick={() => setCorrection(row.player_id, row.draft_delta - 1)}
                  >
                    −
                  </Button>
                  <NumericDraft
                    label={t("final.correctionFor", { name: nameOf(view, row.player_id) })}
                    value={row.draft_delta}
                    disabled={pending.has(row.player_id)}
                    onCommit={(value) => setCorrection(row.player_id, value)}
                    onBusy={(value) =>
                      setBusy((old) => {
                        const next = new Set(old);
                        if (value) next.add(row.player_id);
                        else next.delete(row.player_id);
                        return next;
                      })
                    }
                  />
                  <Button
                    disabled={
                      busy.has(row.player_id) ||
                      pending.has(row.player_id) ||
                      row.draft_delta >= 1000
                    }
                    aria-label={t("final.increase", { name: nameOf(view, row.player_id) })}
                    onClick={() => setCorrection(row.player_id, row.draft_delta + 1)}
                  >
                    +
                  </Button>
                </div>
                <label>
                  {t("flow.reason")}
                  <input
                    maxLength={120}
                    value={notes[row.player_id] ?? row.draft_note ?? ""}
                    disabled={pending.has(row.player_id)}
                    onChange={(event) => {
                      const value = event.target.value;
                      setNotes((old) => {
                        const next = { ...old };
                        if (value.trim() === (row.draft_note ?? "")) delete next[row.player_id];
                        else next[row.player_id] = value;
                        return next;
                      });
                    }}
                  />
                </label>
                <Button
                  disabled={
                    pending.has(row.player_id) ||
                    busy.has(row.player_id) ||
                    notes[row.player_id] === undefined
                  }
                  onClick={() => setCorrection(row.player_id, row.draft_delta)}
                >
                  {t("flow.saveReason")}
                </Button>
              </td>
              <td className="final-after">
                {row.score_before} → {formatDelta(row.draft_delta)} → {row.score_after}
              </td>
              <td className="final-detail">
                <button
                  type="button"
                  className="link"
                  aria-expanded={detail === row.player_id}
                  aria-label={`${t("final.detail")} — ${nameOf(view, row.player_id)}`}
                  onClick={() => setDetail(detail === row.player_id ? null : row.player_id)}
                >
                  {t("final.detail")}
                </button>
                {detail === row.player_id && <PlayerHistory row={row} />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {saveError && (
        <p role="alert" className="error">
          {t("ux.saveTimeout")}
        </p>
      )}
      {pending.size > 0 && (
        <p role="status" className="muted">
          {t("ux.waitingScores")}
        </p>
      )}
      <div className="row">
        <Button disabled={saving} onClick={resetCorrections}>
          {t("final.reset")}
        </Button>
        <Button kind="primary" disabled={saving} onClick={() => setConfirm(true)}>
          {t("final.validate")}
        </Button>
      </div>
      <ConfirmDialog
        open={confirm}
        title={t("final.validate")}
        message={
          unchecked ? t("ux.confirmUnchecked", { count: unchecked }) : t("review.privateHint")
        }
        onConfirm={() => {
          send(cmd.finalValidate(unchecked > 0));
          setConfirm(false);
        }}
        onCancel={() => setConfirm(false)}
      >
        <table className="table">
          <caption>{t("final.title")}</caption>
          <thead>
            <tr>
              <th>{t("reveal.player")}</th>
              <th>{t("final.correction")}</th>
              <th>{t("final.after")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.player_id}>
                <td>{nameOf(view, row.player_id)}</td>
                <td>
                  {formatDelta(row.draft_delta)}
                  {row.draft_note && <p>{row.draft_note}</p>}
                </td>
                <td>{row.score_after}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p>
          {t("review.remaining", { count: unchecked })} · {corrections.length}{" "}
          {t("results.corrections")}
        </p>
      </ConfirmDialog>
    </section>
  );
}

function SessionControls({ view }: { readonly view: HostView }) {
  const send = useSend();
  const [confirm, setConfirm] = useState(false);
  return (
    <section className="row wrap session-controls">
      <Button onClick={() => send(cmd.joinLock(view, !view.host.joins_locked))}>
        {t(view.host.joins_locked ? "session.unlock" : "session.lock")}
      </Button>
      {view.host.commands.includes("end_game") && (
        <Button kind="danger" onClick={() => setConfirm(true)}>
          {t("session.stop")}
        </Button>
      )}
      <ConfirmDialog
        open={confirm}
        title={t("session.stop")}
        message={t("session.stopHint")}
        onCancel={() => setConfirm(false)}
        onConfirm={() => {
          send(cmd.endGame(view, "score"));
          setConfirm(false);
        }}
      />
    </section>
  );
}

function EndActions(props: { readonly view: HostView }) {
  const { view } = props;
  const send = useSend();
  const [confirm, setConfirm] = useState(false);
  const [reset, setReset] = useState(false);
  return (
    <section className="stack end-actions">
      <Button
        onClick={(event) => {
          event.currentTarget.focus();
          setReset(true);
        }}
      >
        {t("flow.resetLibrary")}
      </Button>
      <ConfirmDialog
        open={reset}
        title={t("flow.resetLibrary")}
        message={t("flow.resetHint")}
        onCancel={() => setReset(false)}
        onConfirm={() => {
          send(cmd.newGame(true));
          setReset(false);
        }}
      />
      <Button kind="primary" onClick={() => send(cmd.newGame())}>
        {t("flow.continueLibrary")}
      </Button>
      <Button kind="danger" onClick={() => setConfirm(true)}>
        {t("hostui.endSession")}
      </Button>
      <ConfirmDialog
        open={confirm}
        message={t("hostui.confirmEndSession")}
        onConfirm={() => {
          send(cmd.endSession(view));
          setConfirm(false);
        }}
        onCancel={() => setConfirm(false)}
      />
    </section>
  );
}

function PlayerOps(props: { readonly view: HostView }) {
  const { view } = props;
  const send = useSend();
  const [kick, setKick] = useState<string | null>(null);
  return (
    <details className="disclosure player-ops">
      <summary>{t("hostui.playerConnections")}</summary>
      <p className="muted">
        {view.host.bridge.state === "ONLINE" ? t("hostui.bridgeOnline") : t("hostui.bridgeOffline")}
        {view.host.pool &&
          ` · ${t("hostui.pool", { remaining: view.host.pool.remaining, size: view.host.pool.size })}`}
      </p>
      <ul className="list">
        {view.host.players_ops.map((ops) => (
          <li key={ops.player_id} className="player-op-row">
            <strong>{nameOf(view, ops.player_id)}</strong>
            <AudioBadge state={ops.audio_state} connection={ops.connection} />
            {ops.rtt_min_ms !== null && (
              <span className="muted">{t("hostui.rtt", { ms: ops.rtt_min_ms })}</span>
            )}
            {ops.late_ms !== null && formatLate(ops.late_ms) && (
              <span className="warn">{formatLate(ops.late_ms)}</span>
            )}
            {ops.player_id !== view.me.player_id && (
              <Button kind="danger" onClick={() => setKick(ops.player_id)}>
                {t("hostui.kick")}
              </Button>
            )}
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={kick !== null}
        message={kick ? t("hostui.confirmKick", { name: nameOf(view, kick) }) : ""}
        onConfirm={() => {
          if (kick) {
            send(cmd.kick(view, kick));
          }
          setKick(null);
        }}
        onCancel={() => setKick(null)}
      />
    </details>
  );
}

function McPanel(props: { readonly view: Extract<HostView, { kind: "host_mc" }> }) {
  const { mc } = props.view;
  return (
    <section className="mc-panel">
      <h3>{t("hostui.currentTrack")}</h3>
      <p>
        {mc.current_track
          ? `${mc.current_track.display_name ?? mc.current_track.filename} — ${mc.current_track.folder}`
          : t("hostui.noCurrentTrack")}
      </p>
      <details className="disclosure">
        <summary>{t("hostui.upcoming")}</summary>
        <ol className="list">
          {mc.upcoming.map((track, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: upcoming tracks have no id in the MC view
            <li key={index}>
              {track.display_name ?? track.filename} — {track.folder}
            </li>
          ))}
        </ol>
        {mc.upcoming.length === 0 && <p className="muted">{t("hostui.upcomingEmpty")}</p>}
      </details>
    </section>
  );
}

function Diagnostics() {
  const [data, setData] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const load = () => {
    setBusy(true);
    setError(null);
    setCopied(false);
    void api.diagnostics().then((result) => {
      setBusy(false);
      if (result.ok) {
        setData(JSON.stringify(result.data, null, 2));
      } else setError(tCode("error", result.error));
    });
  };
  return (
    <details className="disclosure" onToggle={(e) => (e.currentTarget.open ? load() : undefined)}>
      <summary>{t("hostui.diagnostics")}</summary>
      <p>{t("flow.diagnosticHint")}</p>
      <p className="muted">{t("hostui.diagnosticsPrivacy")}</p>
      {busy && <p role="status">{t("app.loading")}</p>}
      {error && (
        <div>
          <p className="error" role="alert">
            {error}
          </p>
          <Button onClick={load}>{t("app.retry")}</Button>
        </div>
      )}
      {data && (
        <>
          <Button
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(data);
                setCopied(true);
              } catch {
                setError(t("ux.copyDiagnosticsFallback"));
              }
            }}
          >
            {copied ? t("ux.copyDiagnosticsDone") : t("hostui.copyDiagnostics")}
          </Button>
          <details className="disclosure">
            <summary>{t("flow.advanced")}</summary>
            <pre className="diag">{data}</pre>
          </details>
        </>
      )}
    </details>
  );
}
