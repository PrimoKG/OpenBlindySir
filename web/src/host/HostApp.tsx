// Host interface (spec §5.1): the current game stays beside a collapsible command pane.
// Buttons shown = view.host.commands: the client never recomputes game rules.
import { useCallback, useEffect, useState } from "react";
import * as cmd from "../app/commands";
import { useGame, useUi } from "../app/hooks";
import { t, tCode } from "../i18n";
import { formatDelta, formatLate, formatRank, formatSeconds } from "../i18n/format";
import { api } from "../net/api";
import { nameOf, PlayerApp } from "../player/PlayerApp";
import type { FolderNode, HostView, LibraryResponse } from "../protocol";
import { readLocal, writeLocal } from "../storage";
import { AudioBadge, Button, ConfirmDialog, LiveRegion } from "../ui/components";

export function HostApp(props: { readonly view: HostView }) {
  const { view } = props;
  return (
    <PlayerApp view={view}>
      <Drawer view={view} />
    </PlayerApp>
  );
}

function Drawer(props: { readonly view: HostView }) {
  const [open, setOpen] = useState(() => readLocal("hostDrawerOpen") !== "0");
  const toggle = () => {
    writeLocal("hostDrawerOpen", open ? "0" : "1");
    setOpen(!open);
  };
  return (
    <aside className="drawer" id="host-controls" aria-label={t("hostui.drawer")}>
      <button
        type="button"
        className="drawer-toggle"
        aria-expanded={open}
        aria-controls="host-panel"
        onClick={toggle}
      >
        <span>{t("hostui.drawer")}</span>
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div id="host-panel">
          <HostControls view={props.view} />
        </div>
      )}
    </aside>
  );
}

function useSend() {
  const game = useGame();
  return useCallback((msg: Parameters<typeof game.send>[0]) => game.send(msg), [game]);
}

function HostControls(props: { readonly view: HostView }) {
  const { view } = props;
  const ui = useUi();
  const can = (name: string) => view.host.commands.includes(name);
  return (
    <fieldset className="stack host" disabled={ui.socket !== "open"}>
      <legend className="sr-only">{t("hostui.drawer")}</legend>
      <ModeSwitch key={`${view.kind}:${view.phase}`} view={view} />
      <Warnings view={view} />
      {view.kind === "host_mc" && <McPanel view={view} />}
      {view.phase === "LOBBY" && <Setup view={view} />}
      {view.round?.state === "REVIEW" && "answers" in view.round && <ReviewTable view={view} />}
      {view.phase === "IN_GAME" && <RoundControls view={view} />}
      {view.phase === "FINAL_SCORE_REVIEW" && <FinalReview view={view} />}
      {view.phase === "FINAL_RESULTS" && <EndActions view={view} />}
      {can("adjust") && (
        <details className="disclosure">
          <summary>{t("hostui.adjust")}</summary>
          <Adjustments view={view} />
        </details>
      )}
      <PlayerOps view={view} />
      <Diagnostics />
    </fieldset>
  );
}

function ModeSwitch(props: { readonly view: HostView }) {
  const { view } = props;
  const send = useSend();
  const mc = view.kind === "host_mc";
  return (
    <div className="host-mode">
      <strong>{mc ? t("hostui.modeMc") : t("hostui.modePlayer")}</strong>
      <p className="muted">{mc ? t("hostui.modeHintMc") : t("hostui.modeHintPlayer")}</p>
      <details className="mode-options">
        <summary>{t("hostui.modeSettings")}</summary>
        <Button
          disabled={!view.host.commands.includes("set_mode")}
          onClick={() => send(cmd.setMode(view, mc ? "player" : "mc"))}
        >
          {mc ? t("hostui.switchToPlayer") : t("hostui.switchToMc")}
        </Button>
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

function Setup(props: { readonly view: HostView }) {
  const { view } = props;
  const send = useSend();
  const settings = view.host.settings;
  const [rounds, setRounds] = useState(settings.rounds);
  const [clip, setClip] = useState(settings.clip_seconds);
  const [grace, setGrace] = useState(settings.answer_grace_s);
  const [library, setLibrary] = useState<LibraryResponse | null>(null);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [libraryRetry, setLibraryRetry] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(settings.sources.map((s) => `${s.bridge_id}|${s.folder_prefix}`)),
  );

  // Reload the folder tree whenever the Bridge state or its catalogue changes.
  const libraryKey = `${view.host.bridge.state}:${view.host.bridge.track_count}:${libraryRetry}`;
  useEffect(() => {
    let active = true;
    if (libraryKey) {
      setLibraryLoading(true);
      setLibraryError(null);
      void api.library().then((result) => {
        if (!active) return;
        setLibraryLoading(false);
        if (result.ok) setLibrary(result.data);
        else setLibraryError(tCode("error", result.error));
      });
    }
    return () => {
      active = false;
    };
  }, [libraryKey]);

  const savedSources = settings.sources.map((s) => `${s.bridge_id}|${s.folder_prefix}`);
  const dirty =
    rounds !== settings.rounds ||
    clip !== settings.clip_seconds ||
    grace !== settings.answer_grace_s ||
    selected.size !== savedSources.length ||
    savedSources.some((s) => !selected.has(s));

  const toggle = (key: string) => {
    const next = new Set(selected);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    setSelected(next);
  };

  const save = () => {
    const sources = [...selected].map((key) => {
      const [bridge_id = "", folder_prefix = ""] = key.split("|");
      return { bridge_id, folder_prefix };
    });
    send(cmd.configure(view, { rounds, clip_seconds: clip, answer_grace_s: grace, sources }));
  };

  return (
    <form
      className="stack setup"
      onSubmit={(event) => {
        event.preventDefault();
        save();
      }}
    >
      <h2>{t("hostui.setup")}</h2>
      <div className="setup-fields">
        <label>
          {t("hostui.rounds")}
          <input
            type="number"
            min={1}
            max={200}
            value={rounds}
            onChange={(e) => setRounds(Number(e.target.value))}
          />
        </label>
        <label>
          {t("hostui.clipSeconds")}
          <input
            type="number"
            min={view.host.limits.clip_min_s}
            max={view.host.limits.clip_max_s}
            value={clip}
            onChange={(e) => setClip(Number(e.target.value))}
          />
        </label>
      </div>
      <details className="disclosure">
        <summary>{t("hostui.advanced")}</summary>
        <label>
          {t("hostui.grace")}
          <input
            type="number"
            min={0}
            max={120}
            value={grace}
            onChange={(e) => setGrace(Number(e.target.value))}
          />
        </label>
      </details>
      <h3>{t("hostui.library")}</h3>
      <p className="muted">
        {view.host.bridge.state === "ONLINE" ? t("hostui.bridgeOnline") : t("hostui.bridgeOffline")}
      </p>
      <p className="muted">{t("hostui.libraryHint")}</p>
      {libraryLoading ? (
        <p role="status">{t("hostui.libraryLoading")}</p>
      ) : libraryError ? (
        <div>
          <p role="alert" className="error">
            {libraryError}
          </p>
          <Button onClick={() => setLibraryRetry((n) => n + 1)}>{t("app.retry")}</Button>
        </div>
      ) : library && library.bridges.length > 0 ? (
        library.bridges.map((bridge) => (
          <ul className="tree" key={bridge.bridge_id}>
            <Folder
              node={bridge.root}
              bridgeId={bridge.bridge_id}
              selected={selected}
              onToggle={toggle}
            />
          </ul>
        ))
      ) : (
        <p className="muted">{t("hostui.libraryEmpty")}</p>
      )}
      <div className="row setup-actions">
        <Button type="submit" disabled={!dirty}>
          {t("hostui.save")}
        </Button>
        <Button
          kind="primary"
          disabled={dirty || !view.host.commands.includes("start_game")}
          onClick={() => send(cmd.startGame())}
        >
          {t("hostui.start")}
        </Button>
      </div>
      <LiveRegion>
        {dirty ? (
          <p className="muted">{t("hostui.unsaved")}</p>
        ) : (
          <p className="muted">{t("hostui.saved")}</p>
        )}
      </LiveRegion>
    </form>
  );
}

function Folder(props: {
  readonly node: FolderNode;
  readonly bridgeId: string;
  readonly selected: ReadonlySet<string>;
  readonly onToggle: (key: string) => void;
}) {
  const key = `${props.bridgeId}|${props.node.prefix}`;
  return (
    <li>
      <label className="folder-option">
        <input
          type="checkbox"
          checked={props.selected.has(key)}
          onChange={() => props.onToggle(key)}
        />
        <span>
          {props.node.name} <small className="muted">({props.node.track_count})</small>
        </span>
      </label>
      {props.node.children.length > 0 && (
        <ul>
          {props.node.children.map((child) => (
            <Folder
              key={child.prefix}
              node={child}
              bridgeId={props.bridgeId}
              selected={props.selected}
              onToggle={props.onToggle}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function RoundControls(props: { readonly view: HostView }) {
  const { view } = props;
  const send = useSend();
  const can = (name: string) => view.host.commands.includes(name);
  const [confirmEnd, setConfirmEnd] = useState<"score" | "abandon" | null>(null);
  const check = view.host.ready_check;
  return (
    <section className="stack round-controls">
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
              <>
                <Button kind="danger" onClick={() => setConfirmEnd("score")}>
                  {t("hostui.endScore")}
                </Button>
                <Button kind="danger" onClick={() => setConfirmEnd("abandon")}>
                  {t("hostui.endAbandon")}
                </Button>
              </>
            )}
          </div>
        </details>
      )}
      <ConfirmDialog
        open={confirmEnd !== null}
        message={confirmEnd === "abandon" ? t("hostui.endAbandon") : t("hostui.endScore")}
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

function ReviewTable(props: { readonly view: HostView }) {
  const { view } = props;
  const send = useSend();
  const round = view.round;
  if (round?.state !== "REVIEW" || !("answers" in round)) {
    return null;
  }
  return (
    <section className="stack review-section">
      <h2>{t("reveal.answers")}</h2>
      <table className="table review">
        <caption className="sr-only">{t("hostui.reviewTitle")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("reveal.order")}</th>
            <th scope="col">{t("reveal.player")}</th>
            <th scope="col">{t("reveal.answer")}</th>
            <th scope="col">{t("reveal.time")}</th>
            <th scope="col">{t("hostui.points")}</th>
          </tr>
        </thead>
        <tbody>
          {round.answers.map((row) => {
            const late = formatLate(row.late_start_ms);
            return (
              <tr key={row.player_id}>
                <td className="answer-rank">{formatRank(row.order, row.near_tie)}</td>
                <td className="answer-player">{nameOf(view, row.player_id)}</td>
                <td className="answer-text">
                  {row.text ?? t("round.noAnswer")}{" "}
                  {row.status === "CAPTURED" && t("round.notValidated")}
                </td>
                <td className="answer-time">
                  {row.elapsed_ms !== null ? formatSeconds(row.elapsed_ms) : "—"}
                  {late && <span className="late-notice">{late}</span>}
                </td>
                <td className="score-cell">
                  <div className="score-controls">
                    {[0, 1, 2, 3].map((points) => (
                      <button
                        type="button"
                        key={points}
                        className={`btn btn-small ${row.points_draft === points ? "btn-primary" : "btn-secondary"}`}
                        aria-pressed={row.points_draft === points}
                        onClick={() => send(cmd.scoreDraft(view, row.player_id, points))}
                      >
                        {points === 0 ? "0" : `+${points}`}
                      </button>
                    ))}
                    <input
                      type="number"
                      aria-label={t("hostui.pointsFor", { name: nameOf(view, row.player_id) })}
                      className="points"
                      min={-1000}
                      max={1000}
                      value={row.points_draft}
                      onChange={(e) =>
                        send(cmd.scoreDraft(view, row.player_id, Number(e.target.value) || 0))
                      }
                    />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="publish-action">
        <p className="muted">{t("hostui.publishHint")}</p>
        <Button
          kind="primary"
          disabled={!view.host.commands.includes("publish")}
          onClick={() => send(cmd.roundCmd(view, "publish"))}
        >
          {t("hostui.publish")}
        </Button>
      </div>
    </section>
  );
}

function FinalReview(props: { readonly view: HostView }) {
  const { view } = props;
  const send = useSend();
  const rows = view.host.final_review ?? [];
  const [confirm, setConfirm] = useState(false);
  const [detail, setDetail] = useState<string | null>(null);
  const corrections = rows.filter((r) => r.draft_delta !== 0);
  const summary = corrections
    .map((r) => `${nameOf(view, r.player_id)} ${formatDelta(r.draft_delta)}`)
    .join(", ");
  return (
    <section className="stack final-review">
      <h2>{t("final.title")}</h2>
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
                    aria-label={t("final.decrease", { name: nameOf(view, row.player_id) })}
                    onClick={() => send(cmd.finalSet(row.player_id, row.draft_delta - 1))}
                  >
                    −
                  </Button>
                  <input
                    type="number"
                    className="points"
                    aria-label={t("final.correctionFor", { name: nameOf(view, row.player_id) })}
                    value={row.draft_delta}
                    onChange={(e) => send(cmd.finalSet(row.player_id, Number(e.target.value) || 0))}
                  />
                  <Button
                    aria-label={t("final.increase", { name: nameOf(view, row.player_id) })}
                    onClick={() => send(cmd.finalSet(row.player_id, row.draft_delta + 1))}
                  >
                    +
                  </Button>
                </div>
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
                {detail === row.player_id && (
                  <ul className="list">
                    {row.history.map((h) => (
                      <li key={h.round_id}>
                        #{h.number} {h.text ?? "—"}{" "}
                        {h.elapsed_ms !== null ? formatSeconds(h.elapsed_ms) : ""}{" "}
                        {formatRank(h.order, h.near_tie)} {formatDelta(h.points)}
                      </li>
                    ))}
                    {row.adjustments.map((a, index) => (
                      // biome-ignore lint/suspicious/noArrayIndexKey: adjustments have no id
                      <li key={`adj-${index}`}>
                        {formatDelta(a.delta)} {a.note ?? ""}
                      </li>
                    ))}
                  </ul>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row">
        <Button onClick={() => send(cmd.finalReset())}>{t("final.reset")}</Button>
        <Button kind="primary" onClick={() => setConfirm(true)}>
          {t("final.validate")}
        </Button>
      </div>
      <ConfirmDialog
        open={confirm}
        message={
          corrections.length
            ? t("final.confirm", { count: corrections.length, list: summary })
            : t("final.confirmNone")
        }
        onConfirm={() => {
          send(cmd.finalValidate());
          setConfirm(false);
        }}
        onCancel={() => setConfirm(false)}
      />
    </section>
  );
}

function EndActions(props: { readonly view: HostView }) {
  const { view } = props;
  const send = useSend();
  const [confirm, setConfirm] = useState(false);
  return (
    <section className="stack end-actions">
      <Button kind="primary" onClick={() => send(cmd.newGame())}>
        {t("hostui.newGame")}
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

function Adjustments(props: { readonly view: HostView }) {
  const { view } = props;
  const send = useSend();
  const [pending, setPending] = useState<{ playerId: string; delta: number; opId: string } | null>(
    null,
  );
  return (
    <section>
      <h3>{t("hostui.adjust")}</h3>
      <ul className="list">
        {view.standings.map((row) => (
          <li key={row.player_id} className="row">
            {nameOf(view, row.player_id)} ({row.score})
            <Button
              onClick={() =>
                setPending({ playerId: row.player_id, delta: -1, opId: cmd.newOpId() })
              }
            >
              −1
            </Button>
            <Button
              onClick={() => setPending({ playerId: row.player_id, delta: 1, opId: cmd.newOpId() })}
            >
              +1
            </Button>
          </li>
        ))}
      </ul>
      <ConfirmDialog
        open={pending !== null}
        message={
          pending
            ? t("hostui.confirmAdjust", {
                delta: formatDelta(pending.delta),
                name: nameOf(view, pending.playerId),
              })
            : ""
        }
        onConfirm={() => {
          if (pending) {
            send(cmd.adjust(pending.playerId, pending.delta, pending.opId));
          }
          setPending(null);
        }}
        onCancel={() => setPending(null)}
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
  const load = () => {
    setBusy(true);
    setError(null);
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
          <Button onClick={() => void navigator.clipboard?.writeText(data)}>
            {t("hostui.copyDiagnostics")}
          </Button>
          <pre className="diag">{data}</pre>
        </>
      )}
    </details>
  );
}
