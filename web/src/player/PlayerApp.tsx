// Player screens per phase (spec §5.1). The host in Player Mode sees exactly the same round.
import { type FormEvent, useEffect, useRef, useState } from "react";
import { useEngine, useGame, useServerNow, useUi } from "../app/hooks";
import { t, tCode } from "../i18n";
import { formatDelta, formatRank, formatSeconds } from "../i18n/format";
import type { AnyView, RevealRow, RoundOpen, StandingRow } from "../protocol";
import { AudioBadge, Button, LiveRegion, Toast } from "../ui/components";

export function PlayerApp(props: { readonly view: AnyView }) {
  const { view } = props;
  return (
    <div className="app">
      <Header view={view} />
      <AudioGate />
      <PhaseScreen view={view} />
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
    <header className="header">
      <strong>{t("app.title")}</strong>
      {view.game?.round_number != null && (
        <span>
          {t("round.header", { n: view.game.round_number, total: view.game.rounds_total })}
        </span>
      )}
      <span>{view.me.nickname}</span>
      {ui.socket === "reconnecting" && (
        <span className="badge badge-off">{t("banner.reconnecting")}</span>
      )}
    </header>
  );
}

/** « Tester mon audio » / reactivation overlay (spec §9.7). */
function AudioGate() {
  const game = useGame();
  const engine = useEngine();
  if (engine.contextState === "running") {
    return null;
  }
  const unlock = () => {
    void game.engine.unlock().then(() => game.engine.testBeep());
  };
  return (
    <div className="overlay" role="dialog" aria-modal="true">
      <Button kind="primary" onClick={unlock}>
        {engine.contextState === "none" ? t("lobby.testAudio") : t("audio.reactivate")}
      </Button>
    </div>
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
        <main>
          <LiveRegion>{t("final.waiting")}</LiveRegion>
          <Standings rows={view.standings} view={view} />
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
    <main className="stack">
      <h1>{t("app.title")}</h1>
      <section>
        <h2>{t("lobby.players", { count: view.players.length })}</h2>
        <ul className="list">
          {view.players.map((p) => (
            <li key={p.id}>
              {p.nickname} {p.is_host ? "★" : ""} {p.online ? "" : t("status.offline")}
            </li>
          ))}
        </ul>
      </section>
      <section className="row">
        <Button onClick={() => game.engine.testBeep()} disabled={engine.contextState !== "running"}>
          {t("lobby.testAudio")}
        </Button>
        <Button
          onClick={() => game.engine.confirmHeard()}
          disabled={engine.contextState !== "running"}
        >
          {engine.heardConfirmed ? t("lobby.audioOk") : t("lobby.hearIt")}
        </Button>
        <AudioBadge state={engine.state} />
      </section>
      <Volume />
      <LiveRegion>{t("lobby.waiting")}</LiveRegion>
    </main>
  );
}

function Volume() {
  const game = useGame();
  const engine = useEngine();
  return (
    <label className="volume">
      {t("settings.volume")}
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={engine.volume}
        onChange={(e) => game.engine.setVolume(Number(e.target.value))}
      />
    </label>
  );
}

function RoundScreen(props: { readonly view: AnyView }) {
  const { view } = props;
  const round = view.round;
  if (!round) {
    return null;
  }
  switch (round.state) {
    case "QUEUED":
    case "PREPARING":
      return <main className="center">{t("round.preparing")}</main>;
    case "LOADING":
      return <main className="center">{t("round.loading")}</main>;
    case "COUNTDOWN":
      return <Countdown startAt={round.official_start_at} />;
    case "OPEN":
      return "my_answer" in round ? <OpenRound view={view} round={round} /> : <McOpenNotice />;
    case "REVIEW":
      return (
        <main className="stack">
          <LiveRegion>{t("round.review")}</LiveRegion>
          {"my_answer" in round && round.my_answer.text && (
            <p>{t("round.yourAnswer", { text: round.my_answer.text })}</p>
          )}
        </main>
      );
    case "REVEALED":
      return <Reveal view={view} />;
  }
}

function McOpenNotice() {
  return <main className="center">{t("round.review")}</main>;
}

function Countdown(props: { readonly startAt: number }) {
  const now = useServerNow(true);
  const seconds = Math.max(0, Math.ceil((props.startAt - now) / 1000));
  return (
    <main className="center">
      <p className="countdown" aria-live="assertive">
        {seconds > 0 ? seconds : "♪"}
      </p>
    </main>
  );
}

function OpenRound(props: { readonly view: AnyView; readonly round: RoundOpen }) {
  const { round } = props;
  const game = useGame();
  const ui = useUi();
  const engine = useEngine();
  const now = useServerNow(true);
  const [text, setText] = useState("");
  const initialised = useRef<string | null>(null);
  const draftTimer = useRef<number | undefined>(undefined);
  const locked = round.my_answer.status === "LOCKED" || ui.acceptedRound === round.round_id;

  useEffect(() => {
    // Initialise from the server only on a new round, never while typing.
    if (initialised.current !== round.round_id) {
      initialised.current = round.round_id;
      setText(round.my_answer.text ?? round.my_answer.draft_text ?? "");
    }
  }, [round]);

  const onChange = (value: string) => {
    setText(value);
    window.clearTimeout(draftTimer.current);
    draftTimer.current = window.setTimeout(() => {
      game.send({ t: "ANSWER_DRAFT", round_id: round.round_id, text: value });
    }, 500);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    window.clearTimeout(draftTimer.current);
    if (text.trim()) {
      game.submitAnswer(round.round_id, text);
    }
  };

  const remaining = Math.max(0, Math.ceil((round.deadline - now) / 1000));
  return (
    <main className="stack">
      {engine.lateJoinMs !== null && (
        <p className="notice">{t("round.lateJoin", { time: formatSeconds(engine.lateJoinMs) })}</p>
      )}
      <p className="muted">{t("round.timeLeft", { s: remaining })}</p>
      {locked ? (
        <LiveRegion>
          <p className="saved">{t("round.saved")}</p>
        </LiveRegion>
      ) : (
        <form onSubmit={submit} className="stack">
          <label>
            {t("round.answerLabel")}
            <input
              value={text}
              maxLength={200}
              onChange={(e) => onChange(e.target.value)}
              autoComplete="off"
            />
          </label>
          <Button type="submit" kind="primary">
            {t("round.submit")}
          </Button>
          {ui.pendingSubmit && <p className="notice">{t("round.pendingSubmit")}</p>}
        </form>
      )}
      {round.progress && (
        <LiveRegion>
          {t("round.progress", {
            validated: round.progress.validated,
            expected: round.progress.expected,
          })}
        </LiveRegion>
      )}
      <Volume />
    </main>
  );
}

function Reveal(props: { readonly view: AnyView }) {
  const { view } = props;
  const round = view.round;
  if (round?.state !== "REVEALED") {
    return null;
  }
  return (
    <main className="stack">
      <section>
        <h2>{t("reveal.title")}</h2>
        <p className="track">{round.track.display_name}</p>
        <p className="muted">{round.track.folder}</p>
      </section>
      <table className="table">
        <tbody>
          {round.rows.map((row: RevealRow) => (
            <tr key={row.player_id}>
              <td>{formatRank(row.order, row.near_tie)}</td>
              <td>{nameOf(view, row.player_id)}</td>
              <td>{row.text ?? t("round.noAnswer")}</td>
              <td>
                {row.status === "CAPTURED"
                  ? t("round.notValidated")
                  : row.elapsed_ms !== null
                    ? formatSeconds(row.elapsed_ms)
                    : ""}
              </td>
              <td>{formatDelta(row.points)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Standings rows={view.standings} view={view} />
    </main>
  );
}

export function Standings(props: {
  readonly rows: readonly StandingRow[];
  readonly view: AnyView;
}) {
  return (
    <section>
      <h2>{t("standings.title")}</h2>
      <ol className="list">
        {props.rows.map((row) => (
          <li key={row.player_id}>
            {row.rank}. {nameOf(props.view, row.player_id)} —{" "}
            {t("standings.points", { score: row.score })}
          </li>
        ))}
      </ol>
    </section>
  );
}

function Results(props: { readonly view: AnyView }) {
  const { view } = props;
  const results = view.final_results;
  if (!results) {
    return null;
  }
  return (
    <main className="stack">
      <h1>{t("results.title")}</h1>
      <ol className="podium">
        {results.podium.map((row) => (
          <li key={row.player_id}>
            {row.rank}. {nameOf(view, row.player_id)} —{" "}
            {t("standings.points", { score: row.score })}
          </li>
        ))}
      </ol>
      <Standings rows={results.standings} view={view} />
      <p>{t("results.rounds", { count: results.rounds_played })}</p>
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
    </main>
  );
}
