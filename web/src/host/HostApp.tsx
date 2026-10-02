// Host interface (spec §5.1): the current game stays beside a collapsible command pane.
// Buttons shown = view.host.commands: the client never recomputes game rules.
import { useCallback, useState } from "react";
import * as cmd from "../app/commands";
import { useGame, useUi } from "../app/hooks";
import { t, tCode } from "../i18n";
import { formatDelta, formatLate } from "../i18n/format";
import { api } from "../net/api";
import { nameOf, PlayerApp } from "../player/PlayerApp";
import { PlayerHistory } from "../player/Recap";
import type { HostView } from "../protocol";
import { readLocal, writeLocal } from "../storage";
import { AudioBadge, Button, ConfirmDialog } from "../ui/components";
import { NumericDraft } from "../ui/NumericDraft";
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
      {view.session.persistence_status === "failed" && (
        <p className="error" role="alert">
          {t("ux.persistenceFailed")}
        </p>
      )}
      {view.session.recovered && <p className="notice">{t("ux.sessionRecovered")}</p>}
      <ModeSwitch key={`${view.kind}:${view.phase}`} view={view} />
      {view.phase !== "LOBBY" && <Warnings view={view} />}
      {view.kind === "host_mc" && view.round?.state !== "REVIEW" && <McPanel view={view} />}
      {view.phase === "LOBBY" && <SetupPanel view={view} />}
      {view.round?.state === "REVIEW" && "answers" in view.round && (
        <ReviewRound key={view.round.round_id} view={view} />
      )}
      {view.phase === "IN_GAME" && <RoundControls view={view} />}
      {view.phase === "FINAL_SCORE_REVIEW" && <FinalReview view={view} />}
      {view.phase === "FINAL_RESULTS" && <EndActions view={view} />}
      {can("adjust") && (
        <details className="disclosure">
          <summary>{t("hostui.adjust")}</summary>
          <Adjustments view={view} />
        </details>
      )}
      {view.phase === "LOBBY" && (
        <>
          <Invite />
          <Participation view={view} />
        </>
      )}
      <PartyHistory view={view} />
      {view.phase !== "LOBBY" && <LibraryIssues view={view} />}
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
          <Button onClick={() => send(cmd.endGame(view, "abandon"))}>{t("hostui.toFinal")}</Button>
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

function FinalReview(props: { readonly view: HostView }) {
  const { view } = props;
  const send = useSend();
  const rows = view.host.final_review ?? [];
  const [confirm, setConfirm] = useState(false);
  const [detail, setDetail] = useState<string | null>(null);
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());
  const corrections = rows.filter((r) => r.draft_delta !== 0);
  const summary = rows
    .map(
      (r) =>
        `${nameOf(view, r.player_id)} : ${r.score_after} ${t("hostui.points")} (${formatDelta(r.draft_delta)})`,
    )
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
                    disabled={busy.has(row.player_id) || row.draft_delta <= -1000}
                    aria-label={t("final.decrease", { name: nameOf(view, row.player_id) })}
                    onClick={() => send(cmd.finalSet(row.player_id, row.draft_delta - 1))}
                  >
                    −
                  </Button>
                  <NumericDraft
                    label={t("final.correctionFor", { name: nameOf(view, row.player_id) })}
                    value={row.draft_delta}
                    onCommit={(value) => send(cmd.finalSet(row.player_id, value))}
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
                    disabled={busy.has(row.player_id) || row.draft_delta >= 1000}
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
                {detail === row.player_id && <PlayerHistory row={row} />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row">
        <Button disabled={busy.size > 0} onClick={() => send(cmd.finalReset())}>
          {t("final.reset")}
        </Button>
        <Button kind="primary" disabled={busy.size > 0} onClick={() => setConfirm(true)}>
          {t("final.validate")}
        </Button>
      </div>
      <ConfirmDialog
        open={confirm}
        message={t("ux.confirmFinal", { list: summary, count: corrections.length })}
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
          <pre className="diag">{data}</pre>
        </>
      )}
    </details>
  );
}
