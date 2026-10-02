import { useState } from "react";
import * as cmd from "../app/commands";
import { useGame } from "../app/hooks";
import { t } from "../i18n";
import { formatDelta, formatLate, formatRank, formatSeconds } from "../i18n/format";
import { nameOf } from "../player/PlayerApp";
import type { HostView } from "../protocol";
import { Button, ConfirmDialog } from "../ui/components";
import { NumericDraft } from "../ui/NumericDraft";

export function ReviewRound({ view }: { readonly view: HostView }) {
  const game = useGame();
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());
  const [confirm, setConfirm] = useState(false);
  const [editTrack, setEditTrack] = useState(false);
  const round = view.round;
  if (round?.state !== "REVIEW" || !("answers" in round)) return null;
  const checked = round.answers.filter((row) => row.reviewed).length;
  const presets = [
    ...new Set([
      0,
      view.rules?.title_points ?? 1,
      view.rules?.artist_points ?? 1,
      (view.rules?.title_points ?? 1) + (view.rules?.artist_points ?? 1),
      3,
    ]),
  ].filter((points) => points <= 1000);
  const markBusy = (id: string, value: boolean) =>
    setBusy((old) => {
      const next = new Set(old);
      if (value) next.add(id);
      else next.delete(id);
      return next;
    });
  return (
    <section className="stack review-section">
      <div className="review-heading">
        <p className="eyebrow">{t("ux.privateCorrection")}</p>
        <h1>{round.track?.title ?? round.track?.display_name ?? t("hostui.reviewTitle")}</h1>
        {round.track?.artist && <p className="track-artist">{round.track.artist}</p>}
        <Button onClick={() => setEditTrack(!editTrack)}>{t("ux.editTrack")}</Button>
        {editTrack && <TrackEditor key={round.round_id} view={view} />}
      </div>
      {round.recovery_interrupted && (
        <p className="notice" role="status">
          {t("ux.interruptedRound")}
        </p>
      )}
      <div className="phase-band">
        <strong>{t("hostui.reviewTitle")}</strong>
        <span role="status">
          {t("ux.reviewed", { count: checked, total: round.answers.length })}
        </span>
      </div>
      <p className="muted">{t("hostui.publishHint")}</p>
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
            const capturedZero =
              row.status === "CAPTURED" && view.rules?.captured_policy === "zero";
            return (
              <tr key={row.player_id} className={row.reviewed ? "reviewed" : "unreviewed"}>
                <td className="answer-rank">{formatRank(row.order, row.near_tie)}</td>
                <td className="answer-player">
                  {nameOf(view, row.player_id)}
                  <small className="review-status">
                    {row.reviewed ? t("ux.checked") : t("ux.unchecked")}
                  </small>
                </td>
                <td className="answer-text">
                  {row.text ?? t("round.noAnswer")}
                  <small className="answer-status">
                    {row.status === "LOCKED"
                      ? t("ux.validated")
                      : row.status === "CAPTURED"
                        ? t("ux.captured")
                        : t("round.noAnswer")}
                  </small>
                </td>
                <td className="answer-time">
                  {row.elapsed_ms !== null ? formatSeconds(row.elapsed_ms) : "—"}
                  {formatLate(row.late_start_ms) && (
                    <span className="late-notice">{formatLate(row.late_start_ms)}</span>
                  )}
                </td>
                <td className="score-cell">
                  <div className="score-controls">
                    {presets.map((points) => (
                      <button
                        type="button"
                        key={points}
                        className={`btn btn-small ${row.reviewed && row.points_draft === points ? "btn-primary" : "btn-secondary"}`}
                        aria-pressed={!!row.reviewed && row.points_draft === points}
                        disabled={busy.has(row.player_id) || (capturedZero && points !== 0)}
                        onClick={() => game.send(cmd.scoreDraft(view, row.player_id, points))}
                      >
                        {points === 0 ? "0" : formatDelta(points)}
                      </button>
                    ))}
                    <NumericDraft
                      value={row.points_draft}
                      label={t("hostui.pointsFor", { name: nameOf(view, row.player_id) })}
                      disabled={capturedZero}
                      onBusy={(value) => markBusy(row.player_id, value)}
                      onCommit={(value) => game.send(cmd.scoreDraft(view, row.player_id, value))}
                    />
                  </div>
                  <small className="score-preview">
                    {t("ux.scorePreview", {
                      before: row.score_before ?? 0,
                      delta: formatDelta(row.points_draft),
                      after: (row.score_before ?? 0) + row.points_draft,
                    })}
                  </small>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="publish-action">
        <Button
          kind="primary"
          disabled={busy.size > 0 || !view.host.commands.includes("publish")}
          onClick={() =>
            checked < round.answers.length ? setConfirm(true) : game.send(cmd.publish(view))
          }
        >
          {t("hostui.publish")}
        </Button>
        {busy.size > 0 && (
          <p role="status" className="muted">
            {t("ux.waitingScores")}
          </p>
        )}
      </div>
      <ConfirmDialog
        open={confirm}
        message={t("ux.confirmUnchecked", { count: round.answers.length - checked })}
        onCancel={() => setConfirm(false)}
        onConfirm={() => {
          game.send(cmd.publish(view, true));
          setConfirm(false);
        }}
      />
    </section>
  );
}

function TrackEditor({ view }: { readonly view: HostView }) {
  const game = useGame();
  const track = view.round?.state === "REVIEW" && "track" in view.round ? view.round.track : null;
  const [title, setTitle] = useState(track?.title ?? track?.display_name ?? "");
  const [artist, setArtist] = useState(track?.artist ?? "");
  return (
    <form
      className="stack metadata-editor"
      onSubmit={(e) => {
        e.preventDefault();
        game.send(cmd.trackMetadata(view, title, artist));
      }}
    >
      <label>
        {t("ux.trackTitle")}
        <input maxLength={256} value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        {t("ux.artist")}
        <input maxLength={256} value={artist} onChange={(e) => setArtist(e.target.value)} />
      </label>
      <Button type="submit" disabled={!title.trim() && !artist.trim()}>
        {t("hostui.save")}
      </Button>
    </form>
  );
}
