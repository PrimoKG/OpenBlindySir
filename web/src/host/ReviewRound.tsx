import { useEffect, useState } from "react";
import * as cmd from "../app/commands";
import { useGame } from "../app/hooks";
import { t } from "../i18n";
import { formatDelta, formatLate, formatRank, formatSeconds } from "../i18n/format";
import { nameOf } from "../player/PlayerApp";
import type { HostView, ReviewRound as ReviewData } from "../protocol";
import { Button } from "../ui/components";
import { NumericDraft } from "../ui/NumericDraft";
import { ReviewAudio } from "./ReviewAudio";

export function ReviewRound({
  view,
  round,
  onBusy,
}: {
  readonly view: HostView;
  readonly round: ReviewData;
  readonly onBusy: (busy: boolean) => void;
}) {
  const game = useGame();
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());
  const [pending, setPending] = useState<Map<string, number>>(new Map());
  const [saveError, setSaveError] = useState(false);
  const [editTrack, setEditTrack] = useState(false);
  const [trackBusy, setTrackBusy] = useState(false);
  useEffect(() => {
    setPending((old) => {
      const next = new Map(old);
      for (const row of round.answers)
        if (row.reviewed && next.get(row.player_id) === row.points_draft)
          next.delete(row.player_id);
      return next.size === old.size ? old : next;
    });
  }, [round.answers]);
  useEffect(() => {
    onBusy(busy.size > 0 || pending.size > 0 || trackBusy);
    return () => onBusy(false);
  }, [busy, pending, trackBusy, onBusy]);
  useEffect(() => {
    if (!pending.size) return;
    const timer = window.setTimeout(() => {
      setPending(new Map());
      setSaveError(true);
    }, 10000);
    return () => window.clearTimeout(timer);
  }, [pending]);
  const score = (pid: string, points: number) => {
    const row = round.answers.find((a) => a.player_id === pid);
    if (row?.reviewed && row.points_draft === points) return true;
    const sent = game.send(cmd.scoreDraft(round.round_id, pid, points));
    setSaveError(!sent);
    if (sent) setPending((old) => new Map(old).set(pid, points));
    return sent;
  };
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
        <Button disabled={trackBusy} onClick={() => setEditTrack(!editTrack)}>
          {t("ux.editTrack")}
        </Button>
        <p className="muted">
          {[round.track?.featuring, round.track?.album, round.track?.year]
            .filter(Boolean)
            .join(" · ")}
        </p>
        {editTrack && <TrackEditor key={round.round_id} round={round} onBusy={setTrackBusy} />}
      </div>
      <ReviewAudio key={round.round_id} round={round} />
      {!round.included && <p className="notice">{t("review.cancelled")}</p>}
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
      <p className="muted">{t("review.privateHint")}</p>
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
                  {row.received_at_wall_ms != null && (
                    <time
                      className="muted"
                      dateTime={new Date(row.received_at_wall_ms).toISOString()}
                    >
                      {new Date(row.received_at_wall_ms).toLocaleTimeString()}
                    </time>
                  )}
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
                        disabled={
                          !round.included ||
                          busy.has(row.player_id) ||
                          pending.has(row.player_id) ||
                          (capturedZero && points !== 0)
                        }
                        onClick={() => score(row.player_id, points)}
                      >
                        {points === 0 ? "0" : formatDelta(points)}
                      </button>
                    ))}
                    <NumericDraft
                      value={row.points_draft}
                      label={t("hostui.pointsFor", { name: nameOf(view, row.player_id) })}
                      disabled={capturedZero || !round.included || pending.has(row.player_id)}
                      onBusy={(value) => markBusy(row.player_id, value)}
                      onCommit={(value) => score(row.player_id, value)}
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
        {saveError && (
          <p role="alert" className="error">
            {t("ux.saveTimeout")}
          </p>
        )}
        {busy.size > 0 || pending.size > 0 ? (
          <p role="status" className="muted">
            {t("ux.waitingScores")}
          </p>
        ) : (
          <p role="status" className="muted">
            {t("hostui.saved")}
          </p>
        )}
      </div>
    </section>
  );
}

function TrackEditor({
  round,
  onBusy,
}: {
  readonly round: ReviewData;
  readonly onBusy: (value: boolean) => void;
}) {
  const game = useGame();
  const track = round.track;
  const [title, setTitle] = useState(track?.title ?? track?.display_name ?? "");
  const [artist, setArtist] = useState(track?.artist ?? "");
  const [featuring, setFeaturing] = useState(track?.featuring ?? "");
  const [album, setAlbum] = useState(track?.album ?? "");
  const [year, setYear] = useState(String(track?.year ?? ""));
  const [pending, setPending] = useState<number | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(false);
  const metadata = {
    title: title.trim() || null,
    artist: artist.trim() || null,
    featuring: featuring.trim() || null,
    album: album.trim() || null,
    year: year ? Number(year) : null,
  };
  const key = JSON.stringify(metadata);
  const actual = JSON.stringify({
    title: track?.title ?? track?.display_name ?? null,
    artist: track?.artist ?? null,
    featuring: track?.featuring ?? null,
    album: track?.album ?? null,
    year: track?.year ?? null,
  });
  useEffect(() => {
    if (pending !== null && round.metadata_revision > pending) {
      setPending(null);
      setSaved(true);
      setTitle(track?.title ?? track?.display_name ?? "");
      setArtist(track?.artist ?? "");
      setFeaturing(track?.featuring ?? "");
      setAlbum(track?.album ?? "");
      setYear(String(track?.year ?? ""));
    }
  }, [round.metadata_revision, track, pending]);
  useEffect(() => {
    onBusy(pending !== null);
    return () => onBusy(false);
  }, [pending, onBusy]);
  useEffect(() => {
    if (pending === null) return;
    const timer = window.setTimeout(() => {
      setPending(null);
      setError(true);
    }, 10000);
    return () => window.clearTimeout(timer);
  }, [pending]);
  return (
    <form
      className="stack metadata-editor"
      onSubmit={(e) => {
        e.preventDefault();
        setSaved(false);
        const sent = game.send(cmd.trackMetadata(round.round_id, metadata));
        setError(!sent);
        if (sent) setPending(round.metadata_revision);
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
      <label>
        {t("review.featuring")}
        <input maxLength={256} value={featuring} onChange={(e) => setFeaturing(e.target.value)} />
      </label>
      <label>
        {t("review.album")}
        <input maxLength={256} value={album} onChange={(e) => setAlbum(e.target.value)} />
      </label>
      <label>
        {t("review.year")}
        <input
          type="number"
          min={1000}
          max={9999}
          value={year}
          onChange={(e) => setYear(e.target.value)}
        />
      </label>
      <Button
        type="submit"
        disabled={
          pending !== null ||
          (!!year &&
            (!Number.isInteger(Number(year)) || Number(year) < 1000 || Number(year) > 9999))
        }
      >
        {t(pending !== null ? "ux.saving" : "hostui.save")}
      </Button>
      {saved && key === actual && <p role="status">{t("hostui.saved")}</p>}
      {error && (
        <p role="alert" className="error">
          {t("ux.saveTimeout")}
        </p>
      )}
    </form>
  );
}
