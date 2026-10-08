import { type ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useGame, useServerNow } from "../app/hooks";
import { type MessageKey, type Params, t } from "../i18n";
import { formatDelta } from "../i18n/format";
import type { AnyView, RevealTrack } from "../protocol";
import { RecordMark } from "../ui/components";
import { ScoreScroll } from "../ui/ScoreScroll";
import { criteriaFor, criterionLabel } from "../ui/ScoringCriteria";
import { useFinaleMotion } from "./FinaleSounds";

const celebrationSparks = Array.from({ length: 24 }, (_, position) => ({
  id: `spark-${position}`,
  left: `${(position * 37) % 100}%`,
  animationDelay: `${(position % 6) * 0.07}s`,
  background: ["#b74728", "#d8aa45", "#638453", "#ffffff"][position % 4],
}));

export function trackTitle(track: RevealTrack | null | undefined): string {
  let title = track?.title || track?.display_name || "—";
  const artist = track?.artist;
  if (artist && title.toLocaleLowerCase().startsWith(`${artist.toLocaleLowerCase()} - `)) {
    title = title.slice(artist.length + 3);
  }
  return title
    .replace(/\.(?:mp3|flac|wav|m4a|aac|ogg|opus|mp4|flv)$/i, "")
    .replace(
      /\s*[([](?:exclusive\s+)?(?:official\s+)?(?:music\s+)?(?:video|audio|lyrics?)(?:\s+offici(?:al|el))?[)\]]/gi,
      "",
    )
    .trim();
}

function nickname(view: AnyView, id: string): string {
  return view.players.find((p) => p.id === id)?.nickname ?? "?";
}

export function FinaleStage({
  view,
  children,
}: {
  readonly view: AnyView;
  readonly children?: ReactNode;
}) {
  const finale = view.finale;
  const motion = useFinaleMotion();
  const game = useGame();
  const clipEndsAt = view.play
    ? view.play.start_at + (view.audio.current?.duration_ms ?? 0) - view.play.clip_offset * 1000
    : 0;
  const now = useServerNow(
    !!view.play && performance.now() + (game.clock.estimate()?.offset ?? 0) < clipEndsAt,
  );
  const previous = useRef(finale?.standings);
  const previousRound = useRef(finale?.round);
  const [updated, setUpdated] = useState<ReadonlySet<string>>(new Set());
  const [awarded, setAwarded] = useState<ReadonlySet<string>>(new Set());
  const [activity, setActivity] = useState<{ key: MessageKey; params: Params }[]>([]);
  const positions = useRef(new Map<string, number>());
  const rankingOrder = useRef("");
  const board = useRef<HTMLOListElement>(null);
  useLayoutEffect(() => {
    if (!finale) return;
    const items = board.current?.querySelectorAll<HTMLElement>("[data-scroll-id]");
    const next = new Map<string, number>();
    const order = Array.from(items ?? [])
      .map((item) => item.dataset.scrollId)
      .join(":");
    const reordered = !!rankingOrder.current && order !== rankingOrder.current;
    rankingOrder.current = order;
    for (const item of items ?? []) {
      const id = item.dataset.scrollId ?? "";
      const top = item.offsetTop;
      next.set(id, top);
      const before = positions.current.get(id);
      if (
        reordered &&
        motion &&
        before !== undefined &&
        Math.abs(before - top) > 1 &&
        !window.matchMedia("(prefers-reduced-motion: reduce)").matches
      )
        item.animate?.(
          [{ transform: `translateY(${before - top}px)` }, { transform: "translateY(0)" }],
          { duration: 550, easing: "ease-out" },
        );
    }
    positions.current = next;
  }, [finale, motion]);
  useEffect(() => {
    if (!finale) return;
    const changedRows = finale.standings.filter((row) => {
      const before = previous.current?.find((p) => p.player_id === row.player_id);
      return before && before.score !== row.score;
    });
    const changed: { key: MessageKey; params: Params }[] = changedRows.map((row) => ({
      key:
        row.score < (previous.current?.find((p) => p.player_id === row.player_id)?.score ?? 0)
          ? "auto.adjusted"
          : "finale.activity",
      params: {
        name: nickname(view, row.player_id),
        total: row.score,
        delta: formatDelta(
          row.score - (previous.current?.find((p) => p.player_id === row.player_id)?.score ?? 0),
        ),
      },
    }));
    for (const row of changedRows) {
      const before = previous.current?.find((p) => p.player_id === row.player_id);
      if (before && row.rank < before.rank)
        changed.push({
          key: "auto.overtake",
          params: {
            name: nickname(view, row.player_id),
            before: before.rank,
            after: row.rank,
          },
        });
    }
    const positiveAward = changedRows.some(
      (row) =>
        row.score >
        (previous.current?.find((before) => before.player_id === row.player_id)?.score ?? 0),
    );
    previous.current = finale.standings;
    if (changedRows.length) setUpdated(new Set(changedRows.map((row) => row.player_id)));
    const beforeRound = previousRound.current;
    if (finale.round && beforeRound?.round_id === finale.round.round_id) {
      const awardedIds = finale.round.answers
        .filter((row) => {
          const before = beforeRound.answers.find((a) => a.player_id === row.player_id);
          return before && row.revision !== before.revision;
        })
        .map((row) => row.player_id);
      if (awardedIds.length) {
        setAwarded(new Set(awardedIds));
        changed.push(
          ...awardedIds
            .filter((id) => !changedRows.some((row) => row.player_id === id))
            .map((id) => ({
              key: finale.round?.answers.find((a) => a.player_id === id)?.reviewed
                ? ("experience.confirmedAward" as const)
                : ("polish.partialAward" as const),
              params: {
                name: nickname(view, id),
                points: finale.round?.answers.find((a) => a.player_id === id)?.points ?? 0,
              },
            })),
        );
      }
    } else {
      setAwarded(new Set());
      setUpdated(new Set());
      setActivity([]);
      if (finale.round && finale.round.round_id !== beforeRound?.round_id) {
        changed.push({ key: "experience.roundActivity", params: { number: finale.round.number } });
        game.engine.playFinaleCue(`reveal:${finale.round.round_id}`, "reveal");
      }
    }
    previousRound.current = finale.round;
    if (changed.length) {
      setActivity(changed);
      if (finale.round && beforeRound?.round_id === finale.round.round_id && positiveAward)
        game.engine.playFinaleCue(
          `award:${finale.round.round_id}:${finale.round.answers.map((a) => a.revision).join(":")}`,
          "award",
        );
    }
  }, [finale, view, game]);
  useEffect(() => {
    if (!awarded.size && !updated.size) return;
    const timer = window.setTimeout(() => {
      setUpdated(new Set());
      setAwarded(new Set());
    }, 4500);
    return () => window.clearTimeout(timer);
  }, [awarded, updated]);
  if (!finale) return null;
  const round = finale.round;
  const mine = finale.standings.find((row) => row.player_id === view.me.player_id);
  const myAnswer = round?.answers.find((row) => row.player_id === view.me.player_id);
  const ranks = finale.teams.length
    ? finale.teams.map((row) => ({
        id: row.team,
        name: row.team,
        ...row,
        mine: row.members.includes(view.me.player_id),
      }))
    : finale.standings.map((row) => ({
        id: row.player_id,
        name: nickname(view, row.player_id),
        ...row,
        mine: row.player_id === view.me.player_id,
      }));
  return (
    <section
      className="finale-scene"
      data-motion={motion ? "on" : "off"}
      aria-label={t("finale.title")}
    >
      <div className="finale-banner">
        <div>
          <p className="eyebrow">{t("finale.eyebrow")}</p>
          <h1>{t("finale.title")}</h1>
        </div>
        <span className="live-pill">
          <span aria-hidden="true" />
          {t("finale.live")}
        </span>
      </div>
      <div className="finale-progress">
        <span>
          {t("finale.revealed", {
            count: finale.revealed_round_ids.length,
            total: finale.rounds_total,
          })}
        </span>
        <progress
          value={finale.reviewed}
          max={Math.max(1, finale.expected)}
          aria-label={t("finale.progress")}
        />
        <span>
          {t("experience.awardsProgress", { count: finale.reviewed, total: finale.expected })}
        </span>
      </div>
      <div className="finale-layout">
        <div className="finale-main stack">
          <div
            className={`finale-track ${round ? "is-revealed" : ""} ${children ? "host-scene-track" : ""}`}
            key={round?.round_id ?? "welcome"}
          >
            <RecordMark
              size={children ? "small" : "large"}
              playing={!!view.play && now >= view.play.start_at && now < clipEndsAt}
            />
            <div>
              <p className="eyebrow">
                {round ? t("ux.historyRound", { number: round.number }) : t("finale.ready")}
              </p>
              <h2 dir="auto">{round ? trackTitle(round.track) : t("finale.welcome")}</h2>
              <p className="track-artist" dir="auto">
                {round ? round.track?.artist : t("experience.waitFirst")}
              </p>
              {round && !round.included && <p className="muted">{t("review.cancelled")}</p>}
              {round?.track && (
                <details className="track-original">
                  <summary>{t("finale.original")}</summary>
                  <p dir="auto">{round.track.display_name}</p>
                </details>
              )}
            </div>
          </div>
          {view.play && (
            <p className="shared-replay-status" role="status">
              {t(
                now < view.play.start_at
                  ? "experience.replayScheduled"
                  : now < clipEndsAt
                    ? "experience.replayPlaying"
                    : "experience.replayEnded",
              )}
            </p>
          )}
          {round?.awards_pending && (
            <p className="award-wave-banner" role="status">
              {t("auto.waves")}
            </p>
          )}
          {children ??
            (round ? (
              <ScoreScroll
                scope={round.round_id}
                rows={round.answers.map((answer) => ({
                  id: answer.player_id,
                  reviewed: answer.reviewed,
                  revision: answer.revision,
                }))}
              >
                <div className="finale-answers">
                  <h2>{t("finale.answers")}</h2>
                  {round.answers.map((answer) => (
                    <article
                      key={answer.player_id}
                      className={`finale-answer ${answer.player_id === view.me.player_id ? "is-me" : ""}`}
                      data-scroll-id={answer.player_id}
                    >
                      <div>
                        <strong>{nickname(view, answer.player_id)}</strong>
                        <p dir="auto">{answer.text || t("round.noAnswer")}</p>
                        {criteriaFor(view.rules).some(
                          (key) => answer[`${key}_correct`] === true,
                        ) && (
                          <small className="matched-criteria">
                            {t("auto.criteriaWon", {
                              fields: criteriaFor(view.rules)
                                .filter((key) => answer[`${key}_correct`] === true)
                                .map(criterionLabel)
                                .join(" · "),
                            })}
                          </small>
                        )}
                        <small className="muted">
                          {!round.included
                            ? t("review.cancelledShort")
                            : answer.reviewed
                              ? t("finale.scored")
                              : answer.revision
                                ? t("finale.scoring")
                                : t("finale.pending")}
                        </small>
                      </div>
                      <strong
                        className={`award ${awarded.has(answer.player_id) ? "score-changed" : ""}`}
                        key={`${answer.revision}:${answer.points}`}
                      >
                        {!round.included || answer.reviewed || answer.revision
                          ? t("standings.points", { score: answer.points })
                          : "—"}
                      </strong>
                    </article>
                  ))}
                </div>
              </ScoreScroll>
            ) : (
              <p className="finale-invitation">{t("finale.invitation")}</p>
            ))}
        </div>
        <aside className="finale-scoreboard stack">
          <div>
            <p className="eyebrow">{t("finale.provisional")}</p>
            <h2>{t(finale.teams.length ? "flow.teamRanking" : "standings.title")}</h2>
          </div>
          <ScoreScroll
            ranking
            scope={view.game?.game_id ?? ""}
            rows={ranks.map((row) => ({ id: row.id, reviewed: true, revision: row.score }))}
          >
            <ol className="live-standings" ref={board}>
              {ranks.map((row) => (
                <li key={row.id} className={row.mine ? "is-me" : ""} data-scroll-id={row.id}>
                  <span className="live-rank">
                    {finale.revealed_round_ids.length ? `${row.rank}.` : "—"}
                  </span>
                  <strong>{row.name}</strong>
                  <span
                    className={`live-score ${("members" in row ? row.members.some((id) => updated.has(id)) : updated.has(row.id)) ? "score-changed" : ""}`}
                    key={row.score}
                  >
                    {row.score}
                    <small> pts</small>
                  </span>
                </li>
              ))}
            </ol>
          </ScoreScroll>
          {ranks.some((row) => row.mine) && (
            <button
              type="button"
              className="link"
              onClick={(event) => {
                const panel = event.currentTarget.closest(".finale-scoreboard");
                const pane = panel?.querySelector(".score-scroll");
                const target = pane?.querySelector(".is-me");
                if (pane && target)
                  pane.scrollTo({
                    top:
                      pane.scrollTop +
                      target.getBoundingClientRect().top -
                      pane.getBoundingClientRect().top,
                    behavior: "instant",
                  });
              }}
            >
              {t("scroll.myRank")}
            </button>
          )}
          {!finale.revealed_round_ids.length && (
            <p className="muted scoring-not-started">{t("experience.scorePending")}</p>
          )}
          {mine && view.kind === "player" && (
            <div className="my-finale-score">
              <span>{t("finale.yourTotal")}</span>
              <strong>
                {mine.score}
                <small> pts</small>
              </strong>
              <small>
                {myAnswer && (myAnswer.reviewed || myAnswer.revision)
                  ? t("finale.thisRound", { points: formatDelta(myAnswer.points) })
                  : ""}
              </small>
            </div>
          )}
          {finale.teams.length > 0 && (
            <details className="disclosure">
              <summary>{t("flow.individual")}</summary>
              <ScoreScroll
                ranking
                scope="individual"
                rows={finale.standings.map((row) => ({
                  id: row.player_id,
                  reviewed: true,
                  revision: row.score,
                }))}
              >
                <ol className="live-standings">
                  {finale.standings.map((row) => (
                    <li key={row.player_id} data-scroll-id={row.player_id}>
                      <span>{row.rank}.</span>
                      <strong>{nickname(view, row.player_id)}</strong>
                      <span>{row.score} pts</span>
                    </li>
                  ))}
                </ol>
              </ScoreScroll>
            </details>
          )}
          <p
            className="finale-activity"
            aria-label={t("experience.lastAward")}
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            {activity.map(({ key, params }) => t(key, params)).join(" · ") ||
              t(finale.revealed_round_ids.length ? "finale.follow" : "experience.publicWaiting")}
          </p>
        </aside>
      </div>
    </section>
  );
}

export function podiumStep(
  now: number,
  start: number | null | undefined,
  ranks: readonly number[],
): { visible: number[]; done: boolean } {
  const order = [...new Set(ranks.filter((rank) => rank <= 3))].sort((a, b) => b - a);
  if (start == null) return { visible: order, done: true };
  const count = Math.max(0, Math.floor((now - start) / 1800) + 1);
  return { visible: order.slice(0, count), done: now >= start + order.length * 1800 };
}

export function FinalPodium({
  view,
  children,
}: {
  readonly view: AnyView;
  readonly children: ReactNode;
}) {
  const start = view.final_results?.podium_started_at;
  const motion = useFinaleMotion();
  const game = useGame();
  const now = useServerNow(
    start != null && performance.now() + (game.clock.estimate()?.offset ?? 0) < start + 5400,
  );
  const rows = view.team_standings.length
    ? view.team_standings
        .filter((row) => row.rank <= 3)
        .map((row) => ({ id: row.team, name: row.team, ...row }))
    : (view.final_results?.podium ?? []).map((row) => ({
        id: row.player_id,
        name: nickname(view, row.player_id),
        ...row,
      }));
  const allZero = rows.length > 0 && rows.every((row) => row.score === 0);
  const unreviewed = view.final_results?.unreviewed_answers ?? 0;
  const celebrate = rows.some((row) => row.score > 0) && unreviewed === 0;
  const { visible, done } = podiumStep(
    now,
    motion && celebrate ? start : null,
    rows.map((row) => row.rank),
  );
  const winners = rows.filter((row) => row.rank === 1);
  useEffect(() => {
    if (start == null || !celebrate) return;
    const order = [...new Set(rows.map((row) => row.rank))].sort((a, b) => b - a);
    for (const rank of visible) {
      const at = start + order.indexOf(rank) * 1800;
      game.engine.playFinaleCue(
        `podium:${view.game?.game_id}:${start}:${rank}`,
        rank === 1 ? "win" : "reveal",
        at,
      );
    }
  }, [start, visible, rows, game, view.game?.game_id, celebrate]);
  return (
    <>
      <section
        data-motion={motion ? "on" : "off"}
        className={`final-podium ${celebrate && visible.includes(1) ? "has-winner" : "neutral-podium"}`}
      >
        <p className="eyebrow">{t("finale.podium")}</p>
        <h1>
          {unreviewed > 0
            ? t("polish.incompleteTitle")
            : !rows.length || allZero
              ? t("experience.noAwardTitle")
              : visible.includes(1)
                ? t(winners.length > 1 ? "finale.winners" : "finale.winner")
                : t("finale.suspense")}
        </h1>
        <p className="podium-announcement" role="status" aria-live="polite">
          {unreviewed > 0
            ? t("polish.incompleteResults", { count: unreviewed })
            : allZero
              ? t("experience.noScores")
              : visible.includes(1)
                ? winners.map((row) => row.name).join(" & ")
                : t("finale.podiumHint")}
        </p>
        <ol className="podium ceremony-podium">
          {rows.map((row) => (
            <li
              key={row.id}
              className={`podium-place-${row.rank} ${celebrate && row.rank === 1 ? "podium-first" : ""} ${visible.includes(row.rank) ? "podium-visible" : "podium-hidden"}`}
              aria-hidden={!visible.includes(row.rank)}
            >
              {!allZero && <span className="podium-rank">{row.rank}.</span>}
              <span className="podium-name">{visible.includes(row.rank) ? row.name : ""}</span>
              <strong>
                {visible.includes(row.rank) ? t("standings.points", { score: row.score }) : ""}
              </strong>
            </li>
          ))}
        </ol>
        {celebrate && visible.includes(1) && !done && (
          <div className="celebration-sparks" aria-hidden="true">
            {celebrationSparks.map(({ id, ...style }) => (
              <i key={id} style={style} />
            ))}
          </div>
        )}
      </section>
      {done && children}
    </>
  );
}
