// Phase screens only display the server's filtered view, including for a playing host.
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { useEngine, useGame, useServerNow, useUi } from "../app/hooks";
import { t, tCode } from "../i18n";
import { formatDelta, formatRank, formatSeconds } from "../i18n/format";
import type { AnyView, RoundOpen, StandingRow } from "../protocol";
import {
  AudioBadge,
  Brand,
  Button,
  LiveRegion,
  RecordMark,
  StageMessage,
  Toast,
} from "../ui/components";
import { clipPresentation } from "./presentation";

export function PlayerApp(props: { readonly view: AnyView; readonly children?: ReactNode }) {
  const { view } = props;
  const fullReview =
    view.kind !== "player" &&
    (view.round?.state === "REVIEW" || view.phase === "FINAL_SCORE_REVIEW");
  return (
    <div className={`app ${view.kind === "player" ? "" : "with-host"}`}>
      <Header view={view} />
      <div id="game" className={`game-layout ${fullReview ? "full-review" : ""}`}>
        <div className="player-stage">
          <AudioGate view={view} />
          <PhaseScreen view={view} />
        </div>
        {props.children}
      </div>
      <Notices />
    </div>
  );
}

export function nameOf(view: AnyView, playerId: string): string {
  return view.players.find((p) => p.id === playerId)?.nickname ?? "?";
}

function Header(props: { readonly view: AnyView }) {
  const { view } = props;
  const ui = useUi();
  return (
    <>
      <header className="header">
        <Brand />
        <div className="header-meta">
          {view.game?.round_number != null && (
            <span className="round-number">
              {t("round.header", { n: view.game.round_number, total: view.game.rounds_total })}
            </span>
          )}
          <span className="identity">{view.me.nickname}</span>
          {view.phase !== "LOBBY" && (
            <details className="sound-settings">
              <summary>{t("audio.settings")}</summary>
              <div className="sound-popover">
                <Volume />
              </div>
            </details>
          )}
          {view.kind !== "player" && (
            <a className="host-jump" href="#host-controls">
              {t("hostui.drawer")}
            </a>
          )}
        </div>
      </header>
      {ui.socket === "reconnecting" && (
        <div className="connection-banner" role="status">
          <strong>{t("banner.reconnecting")}</strong>
          <span>{t("banner.reconnectingHint")}</span>
        </div>
      )}
    </>
  );
}

function AudioTest() {
  const game = useGame();
  const engine = useEngine();
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const test = async () => {
    setError(false);
    setBusy(true);
    try {
      if (engine.contextState !== "running") await game.engine.unlock();
      if (game.engine.unlocked) game.engine.testBeep();
      else setError(true);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="audio-test">
      <Button
        kind={engine.heardConfirmed ? "secondary" : "primary"}
        disabled={busy}
        onClick={() => void test()}
      >
        {engine.contextState === "suspended" || engine.contextState === "interrupted"
          ? t("audio.reactivate")
          : t("lobby.testAudio")}
      </Button>
      {error && (
        <p className="error" role="alert">
          {t("audio.unlockFailed")}
        </p>
      )}
    </div>
  );
}

/** Inline audio recovery leaves the current game and host controls reachable. */
function AudioGate(props: { readonly view: AnyView }) {
  const game = useGame();
  const engine = useEngine();
  if (
    props.view.phase !== "IN_GAME" ||
    (engine.contextState === "running" && engine.state !== "ERROR")
  )
    return null;
  return (
    <section className="audio-gate" aria-label={t("audio.gateTitle")}>
      <LiveRegion>
        <strong>{engine.state === "ERROR" ? t("status.error") : t("audio.gateTitle")}</strong>
      </LiveRegion>
      <p className="muted">
        {engine.state === "ERROR" ? t("audio.errorHint") : t("audio.gateHint")}
      </p>
      {engine.state === "ERROR" && engine.contextState === "running" ? (
        <Button onClick={() => game.engine.syncWithView(props.view)}>{t("app.retry")}</Button>
      ) : (
        <AudioTest />
      )}
    </section>
  );
}

function Notices() {
  const game = useGame();
  const ui = useUi();
  return ui.toast ? (
    <Toast text={tCode("error", ui.toast.code)} onClose={() => game.dismissToast()} />
  ) : null;
}

function PhaseScreen(props: { readonly view: AnyView }) {
  const { view } = props;
  switch (view.phase) {
    case "LOBBY":
      return <Lobby view={view} />;
    case "IN_GAME":
      return <RoundScreen view={view} />;
    case "FINAL_SCORE_REVIEW":
      return (
        <main className="stack">
          <StageMessage
            title={view.kind === "player" ? t("final.waiting") : t("hostui.toFinal")}
            description={view.kind === "player" ? t("final.waitingHint") : t("final.hostHint")}
          />
          {view.kind === "player" && <Standings rows={view.standings} view={view} />}
        </main>
      );
    case "FINAL_RESULTS":
      return <Results view={view} />;
  }
}

function Lobby(props: { readonly view: AnyView }) {
  const { view } = props;
  const game = useGame();
  const engine = useEngine();
  return (
    <main className="stack lobby">
      <div className="page-heading">
        <p className="eyebrow">{t("lobby.eyebrow")}</p>
        <h1>{t("lobby.title")}</h1>
        <p className="muted">{t("lobby.description")}</p>
      </div>
      <section className="audio-setup" aria-labelledby="audio-title">
        <div className="section-heading">
          <RecordMark />
          <h2 id="audio-title">{t("lobby.audioTitle")}</h2>
        </div>
        <p className="muted">
          {engine.heardConfirmed ? t("lobby.readyHint") : t("lobby.audioHint")}
        </p>
        <div className="row wrap">
          <AudioTest />
          {engine.heardConfirmed ? (
            <LiveRegion>
              <span className="audio-confirmed">{t("lobby.audioOk")}</span>
            </LiveRegion>
          ) : (
            <Button
              onClick={() => game.engine.confirmHeard()}
              disabled={engine.contextState !== "running"}
            >
              {t("lobby.hearIt")}
            </Button>
          )}
        </div>
        <Volume />
      </section>
      <section className="participants" aria-labelledby="players-title">
        <h2 id="players-title">{t("lobby.players", { count: view.players.length })}</h2>
        <ul className="player-list">
          {view.players.map((p) => (
            <li key={p.id} className={p.online ? "" : "is-offline"}>
              <span className="avatar" aria-hidden="true">
                {p.nickname.slice(0, 1).toLocaleUpperCase()}
              </span>
              <span className="player-name">
                {p.nickname}
                {p.id === view.me.player_id && <small>{t("app.you")}</small>}
                {p.is_host && <small>{t("app.host")}</small>}
                {!p.online && <small>{t("status.offline")}</small>}
              </span>
            </li>
          ))}
        </ul>
      </section>
      <LiveRegion>
        <p className="waiting-line">
          <span aria-hidden="true" className="waiting-dot" />
          {view.kind === "player" ? t("lobby.waiting") : t("lobby.hostWaiting")}
        </p>
      </LiveRegion>
    </main>
  );
}

function Volume() {
  const game = useGame();
  const engine = useEngine();
  return (
    <label className="volume">
      <span>
        {t("settings.volume")}
        <span className="volume-value" aria-hidden="true">
          {Math.round(engine.volume * 100)} %
        </span>
      </span>
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={engine.volume}
        aria-valuetext={`${Math.round(engine.volume * 100)} %`}
        onChange={(e) => game.engine.setVolume(Number(e.target.value))}
      />
    </label>
  );
}

function RoundScreen(props: { readonly view: AnyView }) {
  const { view } = props;
  const round = view.round;
  if (!round)
    return (
      <main>
        <StageMessage busy title={t("round.preparing")} description={t("round.prepareHint")} />
      </main>
    );
  switch (round.state) {
    case "QUEUED":
    case "PREPARING":
      return (
        <main>
          <StageMessage busy title={t("round.preparing")} description={t("round.prepareHint")} />
        </main>
      );
    case "LOADING":
      return (
        <main>
          <StageMessage busy title={t("round.loading")} description={t("round.loadingHint")} />
        </main>
      );
    case "COUNTDOWN":
      return <Countdown startAt={round.official_start_at} />;
    case "OPEN":
      return "my_answer" in round ? (
        <OpenRound view={view} round={round} />
      ) : (
        <McOpenNotice view={view} />
      );
    case "REVIEW":
      return (
        <main className="stack">
          <p className="eyebrow">{t("round.reviewEyebrow")}</p>
          <StageMessage
            title={view.kind === "player" ? t("round.review") : t("hostui.reviewTitle")}
            description={
              view.kind === "player"
                ? t("round.reviewHint")
                : view.kind === "host_mc"
                  ? t("hostui.reviewHintMc")
                  : t("hostui.reviewHint")
            }
          />
          {"my_answer" in round && round.my_answer.text && (
            <p className="own-answer">
              {t("round.yourAnswer", { text: round.my_answer.text })}
              {round.my_answer.status === "CAPTURED" && (
                <span className="muted"> {t("round.notValidated")}</span>
              )}
            </p>
          )}
        </main>
      );
    case "REVEALED":
      return <Reveal view={view} />;
  }
}

function McOpenNotice(props: { readonly view: AnyView }) {
  const round = props.view.round;
  const now = useServerNow(true);
  if (round?.state !== "OPEN" || !("per_player" in round)) return null;
  return (
    <main className="stack">
      <Playback view={props.view} now={now} />
      <h1>{t("round.mcTitle")}</h1>
      <p className="muted">{t("round.mcHint")}</p>
      <p className="time-left">
        {t("round.timeLeft", { s: Math.max(0, Math.ceil((round.deadline - now) / 1000)) })}
      </p>
      <ul className="mc-progress">
        {round.per_player.map((p) => (
          <li key={p.player_id}>
            <span>{nameOf(props.view, p.player_id)}</span>
            <span className="muted">
              {p.validated ? t("round.mcValidated") : t("round.mcWaiting")}
            </span>
          </li>
        ))}
      </ul>
    </main>
  );
}

function Countdown(props: { readonly startAt: number }) {
  const now = useServerNow(true);
  const seconds = Math.max(0, Math.ceil((props.startAt - now) / 1000));
  return (
    <main className="countdown-stage">
      <p className="eyebrow">{t("lobby.eyebrow")}</p>
      <p className="countdown" aria-hidden="true">
        {seconds > 0 ? seconds : "♪"}
      </p>
      <LiveRegion>
        <span className="sr-only">{t("round.countdown", { s: seconds })}</span>
      </LiveRegion>
      <p className="muted">{t("round.countdownHint")}</p>
    </main>
  );
}

function Playback(props: { readonly view: AnyView; readonly now: number }) {
  const engine = useEngine();
  const clip = clipPresentation(props.view.play, props.view.audio.current, engine.state, props.now);
  return (
    <div className="playback">
      <RecordMark playing={clip.kind === "playing"} />
      <div className="playback-info">
        <LiveRegion>
          <strong>
            {clip.kind === "playing" ? (
              t("audio.playing")
            ) : clip.kind === "ended" ? (
              t("audio.ended")
            ) : (
              <AudioBadge state={engine.state} />
            )}
          </strong>
        </LiveRegion>
        <progress value={clip.progress} max={1} aria-label={t("audio.progress")} />
      </div>
    </div>
  );
}

function OpenRound(props: { readonly view: AnyView; readonly round: RoundOpen }) {
  const { view, round } = props;
  const game = useGame();
  const ui = useUi();
  const engine = useEngine();
  const now = useServerNow(true);
  const [text, setText] = useState("");
  const initialised = useRef<string | null>(null);
  const draftTimer = useRef<number | undefined>(undefined);
  const locked = round.my_answer.status === "LOCKED" || ui.acceptedRound === round.round_id;
  useEffect(() => {
    // Restore only on a new round; never overwrite the player's typing with an old view.
    if (initialised.current !== round.round_id) {
      initialised.current = round.round_id;
      setText(round.my_answer.text ?? round.my_answer.draft_text ?? "");
    }
  }, [round]);
  useEffect(() => () => window.clearTimeout(draftTimer.current), []);
  const onChange = (value: string) => {
    setText(value);
    window.clearTimeout(draftTimer.current);
    draftTimer.current = window.setTimeout(
      () => game.send({ t: "ANSWER_DRAFT", round_id: round.round_id, text: value }),
      500,
    );
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    window.clearTimeout(draftTimer.current);
    if (text.trim() && !ui.pendingSubmit) game.submitAnswer(round.round_id, text);
  };
  const remaining = Math.max(0, Math.ceil((round.deadline - now) / 1000));
  const clip = clipPresentation(view.play, view.audio.current, engine.state, now);
  return (
    <main className="stack open-round">
      <Playback view={view} now={now} />
      {engine.lateJoinMs !== null && (
        <p className="notice">{t("round.lateJoin", { time: formatSeconds(engine.lateJoinMs) })}</p>
      )}
      <div className="page-heading">
        <h1>{t("round.openTitle")}</h1>
        <p className="time-left">{t("round.timeLeft", { s: remaining })}</p>
        {clip.kind === "ended" && !locked && <p className="muted">{t("audio.endedHint")}</p>}
      </div>
      {locked ? (
        <section className="answer-saved">
          <LiveRegion>
            <h2 className="saved">{t("round.saved")}</h2>
          </LiveRegion>
          <p className="own-answer">{round.my_answer.text ?? text}</p>
          <p className="muted">{t("round.savedHint")}</p>
        </section>
      ) : (
        <form onSubmit={submit} className="stack answer-form">
          <label htmlFor="answer">{t("round.answerLabel")}</label>
          <input
            id="answer"
            value={text}
            maxLength={200}
            placeholder={t("round.answerPlaceholder")}
            aria-describedby="draft-hint"
            onChange={(e) => onChange(e.target.value)}
            autoComplete="off"
            disabled={ui.pendingSubmit}
          />
          <p id="draft-hint" className="muted">
            {t("round.draftHint")}
          </p>
          <Button type="submit" kind="primary" disabled={!text.trim() || ui.pendingSubmit}>
            {t("round.submit")}
          </Button>
          {ui.pendingSubmit && (
            <LiveRegion>
              <p className="notice">{t("round.pendingSubmit")}</p>
            </LiveRegion>
          )}
        </form>
      )}
      {round.progress && (
        <LiveRegion>
          <p className="answer-progress">
            {t("round.progress", {
              validated: round.progress.validated,
              expected: round.progress.expected,
            })}
          </p>
        </LiveRegion>
      )}
    </main>
  );
}

function Reveal(props: { readonly view: AnyView }) {
  const { view } = props;
  const round = view.round;
  if (round?.state !== "REVEALED") return null;
  return (
    <main className="stack reveal">
      <section className="reveal-heading">
        <p className="eyebrow">{t("reveal.title")}</p>
        <RecordMark size="large" />
        <h1 className="track">{round.track.display_name}</h1>
        <p className="muted track-folder">{round.track.folder}</p>
      </section>
      <section>
        <h2>{t("reveal.answers")}</h2>
        <table className="table answer-table">
          <caption className="sr-only">{t("reveal.answers")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("reveal.order")}</th>
              <th scope="col">{t("reveal.player")}</th>
              <th scope="col">{t("reveal.answer")}</th>
              <th scope="col">{t("reveal.time")}</th>
              <th scope="col">{t("reveal.points")}</th>
            </tr>
          </thead>
          <tbody>
            {round.rows.map((row) => (
              <tr
                key={row.player_id}
                className={row.player_id === view.me.player_id ? "is-me" : ""}
              >
                <td className="answer-rank">{formatRank(row.order, row.near_tie)}</td>
                <td className="answer-player">{nameOf(view, row.player_id)}</td>
                <td className="answer-text">{row.text ?? t("round.noAnswer")}</td>
                <td className="answer-time">
                  {row.status === "CAPTURED"
                    ? t("round.notValidated")
                    : row.elapsed_ms !== null
                      ? formatSeconds(row.elapsed_ms)
                      : "—"}
                </td>
                <td className="answer-points">{formatDelta(row.points)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <Standings rows={view.standings} view={view} />
    </main>
  );
}

export function Standings(props: {
  readonly rows: readonly StandingRow[];
  readonly view: AnyView;
}) {
  return (
    <section className="standings">
      <h2>{t("standings.title")}</h2>
      <ol className="standing-list">
        {props.rows.map((row) => (
          <li
            key={row.player_id}
            className={row.player_id === props.view.me.player_id ? "is-me" : ""}
          >
            <span className="standing-rank">{row.rank}.</span>
            <span className="standing-player">{nameOf(props.view, row.player_id)}</span>
            <span className="standing-score">{t("standings.points", { score: row.score })}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Results(props: { readonly view: AnyView }) {
  const { view } = props;
  const results = view.final_results;
  if (!results) return null;
  return (
    <main className="stack results">
      <div className="page-heading">
        <p className="eyebrow">{t("results.eyebrow")}</p>
        <h1>{t("results.title")}</h1>
        <p className="muted">{t("results.rounds", { count: results.rounds_played })}</p>
      </div>
      <ol className="podium">
        {results.podium.map((row) => (
          <li key={row.player_id} className={row.rank === 1 ? "podium-first" : ""}>
            <span className="podium-rank">{row.rank}.</span>
            <span className="podium-name">{nameOf(view, row.player_id)}</span>
            <strong>{t("standings.points", { score: row.score })}</strong>
          </li>
        ))}
      </ol>
      <Standings rows={results.standings} view={view} />
      {results.final_adjustments.length > 0 && (
        <section className="final-adjustments">
          <h2>{t("results.corrections")}</h2>
          <ul className="list">
            {results.final_adjustments.map((adj) => (
              <li key={adj.player_id}>
                {t("results.adjustment", {
                  name: nameOf(view, adj.player_id),
                  delta: formatDelta(adj.delta),
                })}
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="muted">{t("results.hint")}</p>
    </main>
  );
}
