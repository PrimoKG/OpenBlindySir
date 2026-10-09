import { useEffect, useState } from "react";
import * as cmd from "../app/commands";
import { useGame } from "../app/hooks";
import { getLanguage, t } from "../i18n";
import { formatDelta, formatLate, formatRank, formatSeconds } from "../i18n/format";
import { trackTitle } from "../player/Finale";
import { nameOf } from "../player/PlayerApp";
import type { HostView, MusicalMetadata, ReviewRound as ReviewData } from "../protocol";
import { Button, ConfirmDialog, Modal } from "../ui/components";
import { MetadataFieldActions } from "../ui/MetadataFieldActions";
import { NumericDraft } from "../ui/NumericDraft";
import { ScoreScroll } from "../ui/ScoreScroll";
import {
  AliasEditor,
  type AliasValues,
  type Criterion,
  criteriaFor,
  criterionLabel,
  criterionPoints,
  type Decision,
} from "../ui/ScoringCriteria";
import { ReviewAudio } from "./ReviewAudio";
export function ReviewRound({
  view,
  round,
  onBusy,
  presented = false,
}: {
  readonly view: HostView;
  readonly round: ReviewData;
  readonly onBusy: (busy: boolean) => void;
  readonly presented?: boolean;
}) {
  const game = useGame();
  const [busy, setBusy] = useState<ReadonlySet<string>>(new Set());
  const [pending, setPending] = useState<Map<string, number>>(new Map());
  const [markAbsent, setMarkAbsent] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [editTrack, setEditTrack] = useState(false);
  const [neutralConfirm, setNeutralConfirm] = useState(false);
  const [neutralPending, setNeutralPending] = useState<number | null>(null);
  useEffect(() => {
    if (neutralPending !== null && round.metadata_revision !== neutralPending)
      setNeutralPending(null);
  }, [neutralPending, round.metadata_revision]);
  useEffect(() => {
    if (neutralPending === null) return;
    const timer = setTimeout(() => {
      setNeutralPending(null);
      setSaveError(true);
    }, 10000);
    return () => clearTimeout(timer);
  }, [neutralPending]);
  const [undo, setUndo] = useState<{
    playerId: string;
    revision: number;
    points: number;
    criteria?: Partial<Record<Decision, boolean | null>> | undefined;
  } | null>(null);
  const [trackBusy, setTrackBusy] = useState(false);
  useEffect(() => {
    setPending((old) => {
      const next = new Map(old);
      for (const row of round.answers)
        if (
          next.has(row.player_id) &&
          (row.score_revision ?? 0) >= (next.get(row.player_id) ?? Infinity)
        )
          next.delete(row.player_id);
      return next.size === old.size ? old : next;
    });
  }, [round.answers]);
  useEffect(() => {
    onBusy(busy.size > 0 || pending.size > 0 || trackBusy || markAbsent || neutralPending !== null);
    return () => onBusy(false);
  }, [busy, pending, trackBusy, markAbsent, neutralPending, onBusy]);
  useEffect(() => {
    if (!pending.size) return;
    const timer = window.setTimeout(() => {
      setPending(new Map());
      setSaveError(true);
      setMarkAbsent(false);
    }, 10000);
    return () => window.clearTimeout(timer);
  }, [pending]);
  const score = (
    pid: string,
    points: number,
    criteria?: Partial<Record<Decision, boolean | null>>,
    rememberUndo = true,
  ) => {
    const row = round.answers.find((answer) => answer.player_id === pid);
    if (!row) return false;
    if (rememberUndo)
      setUndo(
        row.reviewed
          ? {
              playerId: pid,
              revision: (row.score_revision ?? 0) + 1,
              points: row.points_draft,
              criteria:
                row.judgement === "criteria"
                  ? Object.fromEntries(
                      criteriaFor(view.rules).map((key) => [
                        `${key}_correct`,
                        row[`${key}_correct`] ?? null,
                      ]),
                    )
                  : undefined,
            }
          : null,
      );
    const judgement = criteria ? "criteria" : "manual";
    const sent = game.send(
      cmd.scoreDraft(round.round_id, pid, points, {
        judgement,
        ...criteria,
        ...Object.fromEntries(
          (round.neutralized_fields ?? []).map((key) => [`${key}_correct`, false]),
        ),
        expected_revision: row.score_revision ?? 0,
      }),
    );
    setSaveError(!sent);
    if (sent) setPending((old) => new Map(old).set(pid, (row.score_revision ?? 0) + 1));
    return sent;
  };
  const mode = view.rules?.answer_mode ?? "both";
  const requested = criteriaFor(view.rules).filter(
    (key) => !round.neutralized_fields?.includes(key),
  );
  const missing = requested.filter(
    (key) =>
      key !== "custom" &&
      !round.scoring_reference?.[key] &&
      !round.scoring_reference?.aliases?.[key as "title"],
  );
  const neutralLabels = (round.neutralized_fields ?? [])
    .map((key) => criterionLabel(key as Criterion))
    .join(", ");
  const fields = requested.map((key) => `${key}_correct` as Decision);
  const weights = Object.fromEntries(
    requested.map((key) => [`${key}_correct`, criterionPoints(key, view.rules)]),
  ) as Record<Decision, number>;
  const checked = round.answers.filter((row) => row.reviewed).length;
  // Batch absent answers at two commands per second, and wait for each server acknowledgement.
  useEffect(() => {
    if (!markAbsent || pending.size || busy.size) return;
    const absent = round.answers.find((row) => !row.reviewed && row.status === "NONE" && !row.text);
    if (!absent) {
      setMarkAbsent(false);
      return;
    }
    const timer = window.setTimeout(() => {
      const sent = game.send(
        cmd.scoreDraft(round.round_id, absent.player_id, 0, {
          judgement: "manual",
          expected_revision: absent.score_revision ?? 0,
        }),
      );
      if (!sent) {
        setSaveError(true);
        setMarkAbsent(false);
        return;
      }
      setPending((old) => new Map(old).set(absent.player_id, (absent.score_revision ?? 0) + 1));
    }, 500);
    return () => window.clearTimeout(timer);
  }, [markAbsent, pending.size, busy.size, round.answers, round.round_id, game]);
  const markBusy = (id: string, value: boolean) =>
    setBusy((old) => {
      const next = new Set(old);
      if (value) next.add(id);
      else next.delete(id);
      return next;
    });
  return (
    <section className="stack review-section">
      <div className="review-context stack">
        <div className="review-heading">
          <p className="eyebrow">
            {t(presented ? "repair.scoringRound" : "experience.preparing", {
              number: round.number,
            })}
          </p>
          <h2 dir="auto">{trackTitle(round.track)}</h2>
          {round.track?.artist && (
            <p className="track-artist" dir="auto">
              {round.track.artist}
            </p>
          )}
          <details className="track-options" open={editTrack || undefined}>
            <summary>{t("finale.trackOptions")}</summary>
            <p className="muted">{t("flow.metadataScope")}</p>
            <Button disabled={trackBusy} onClick={() => setEditTrack(!editTrack)}>
              {t("ux.editTrack")}
            </Button>
            <p className="muted">
              {[round.track?.featuring, round.track?.album, round.track?.year]
                .filter(Boolean)
                .join(" · ")}
            </p>
            <Modal
              open={editTrack}
              title={t("ux.editTrack")}
              onClose={() => {
                if (!trackBusy) setEditTrack(false);
              }}
            >
              {editTrack && (
                <TrackEditor
                  key={round.round_id}
                  round={round}
                  onBusy={setTrackBusy}
                  onSaved={() => {
                    setEditTrack(false);
                    setTrackBusy(false);
                  }}
                  onCancel={() => {
                    setEditTrack(false);
                    setTrackBusy(false);
                  }}
                />
              )}
            </Modal>
            <details className="track-original">
              <summary>{t("finale.original")}</summary>
              <p dir="auto">{round.track?.display_name}</p>
            </details>
          </details>
        </div>
        {!view.play && <ReviewAudio key={round.round_id} round={round} />}
        {!round.included && <p className="notice">{t("review.cancelled")}</p>}
        {round.recovery_interrupted && (
          <p className="notice" role="status">
            {t("ux.interruptedRound")}
          </p>
        )}
        <section className="expected-answer" aria-label={t("experience.expected")}>
          <p className="eyebrow">{t("experience.expected")}</p>
          {mode === "custom" ? (
            <p>{view.rules?.instructions || t("experience.noCustomReference")}</p>
          ) : (
            <dl>
              {requested
                .filter((key) => key !== "custom")
                .map((key) => (
                  <div key={key}>
                    <dt>{criterionLabel(key)}</dt>
                    <dd>
                      {(view.rules?.scoring_mode === "auto"
                        ? round.scoring_reference?.[key]
                        : round.track?.[key]) || t("auto.missing_reference")}
                    </dd>
                  </div>
                ))}
            </dl>
          )}
          {mode !== "custom" &&
            requested.some(
              (key) =>
                key !== "custom" &&
                !(view.rules?.scoring_mode === "auto"
                  ? round.scoring_reference?.[key]
                  : round.track?.[key]),
            ) && (
              <div className="metadata-check">
                <p className="notice">{t("repair.missingHint")}</p>
                {view.rules?.scoring_mode === "auto" &&
                  missing.length > 0 &&
                  !round.reference_changed && (
                    <Button
                      disabled={neutralPending !== null || trackBusy}
                      onClick={() => setNeutralConfirm(true)}
                    >
                      {t("repair.neutralize")}
                    </Button>
                  )}
                <Button disabled={trackBusy} onClick={() => setEditTrack(true)}>
                  {t("ux.editTrack")}
                </Button>
              </div>
            )}
        </section>
        {view.rules?.scoring_mode === "auto" && (
          <p className="muted">
            {t(round.reference_changed ? "auto.referenceChanged" : "auto.frozenReference")}
          </p>
        )}
      </div>
      <ConfirmDialog
        open={neutralConfirm}
        title={t("repair.neutralize")}
        message={t("repair.neutralizeConfirm", {
          fields: missing.map((key) => criterionLabel(key)).join(", "),
        })}
        confirmLabel={t("repair.neutralize")}
        onCancel={() => setNeutralConfirm(false)}
        onConfirm={() => {
          const sent = game.send(
            cmd.neutralizeMissing(
              round.round_id,
              [...(round.neutralized_fields ?? []), ...missing].filter((key) => key !== "custom"),
              round.metadata_revision,
            ),
          );
          setSaveError(!sent);
          if (sent) setNeutralPending(round.metadata_revision);
          setNeutralConfirm(false);
        }}
      />
      {neutralLabels && (
        <p className="notice">
          {t("repair.neutralized", { fields: neutralLabels })}{" "}
          <Button
            disabled={neutralPending !== null}
            onClick={() => {
              const sent = game.send(
                cmd.neutralizeMissing(round.round_id, [], round.metadata_revision),
              );
              setSaveError(!sent);
              if (sent) setNeutralPending(round.metadata_revision);
            }}
          >
            {t("repair.restoreCriteria")}
          </Button>
        </p>
      )}
      <div className="phase-band">
        <strong>
          {t("experience.received", {
            count: round.answers.filter((a) => a.text).length,
            absent: round.answers.filter((a) => !a.text).length,
          })}
        </strong>
        <span role="status">
          {t("ux.reviewed", { count: checked, total: round.answers.length })}
        </span>
      </div>
      {round.answers.some((row) => !row.reviewed && row.status === "NONE" && !row.text) && (
        <Button
          disabled={
            !round.included ||
            markAbsent ||
            busy.size > 0 ||
            pending.size > 0 ||
            !round.answers.some((row) => !row.reviewed && row.status === "NONE" && !row.text)
          }
          onClick={() => setMarkAbsent(true)}
        >
          {t("flow.markAbsent")}
        </Button>
      )}
      <p className="eligible-count muted">
        {t("experience.eligible", { count: round.answers.length })}
      </p>
      <ScoreScroll
        scope={round.round_id}
        controls
        rows={round.answers.map((row) => ({
          id: row.player_id,
          reviewed: row.reviewed,
          revision: row.score_revision ?? 0,
        }))}
      >
        <div className="review answer-cards">
          {round.answers.map((row) => {
            const capturedZero =
              row.status === "CAPTURED" && view.rules?.captured_policy === "zero";
            if (row.status === "NONE" && !row.text)
              return (
                <article
                  key={row.player_id}
                  className={`absent-answer ${row.reviewed ? "reviewed" : "unreviewed"}`}
                  data-scroll-id={row.player_id}
                >
                  <div>
                    <strong>{nameOf(view, row.player_id)}</strong>
                    <p className="muted">{t("round.noAnswer")}</p>
                  </div>
                  {row.reviewed ? (
                    <strong className="absence-award">
                      {t("standings.points", { score: row.points_draft })}{" "}
                      <small>{t("ux.checked")}</small>
                    </strong>
                  ) : (
                    <Button
                      disabled={
                        !round.included ||
                        markAbsent ||
                        pending.has(row.player_id) ||
                        busy.has(row.player_id)
                      }
                      onClick={() => score(row.player_id, 0)}
                    >
                      {t("experience.absenceZero")}
                    </Button>
                  )}
                  <details className="manual-score absence-options">
                    <summary>{t("experience.absenceOptions")}</summary>
                    <NumericDraft
                      value={row.points_draft}
                      label={t("hostui.pointsFor", { name: nameOf(view, row.player_id) })}
                      disabled={!round.included || markAbsent || pending.has(row.player_id)}
                      onBusy={(value) => markBusy(row.player_id, value)}
                      onCommit={(value) => score(row.player_id, value)}
                    />
                  </details>
                </article>
              );
            return (
              <article
                key={row.player_id}
                className={`answer-card ${row.reviewed ? "reviewed" : "unreviewed"}`}
                data-scroll-id={row.player_id}
              >
                <div className="answer-player">
                  <strong>{nameOf(view, row.player_id)}</strong>
                  <small className="review-status">
                    {row.reviewed
                      ? t("ux.checked")
                      : t("polish.criteriaProgress", {
                          count: fields.filter(
                            (field) => row.judgement === "criteria" && row[field] != null,
                          ).length,
                          total: fields.length,
                        })}
                  </small>
                </div>
                <div className="answer-text" dir="auto">
                  {row.text ?? t("round.noAnswer")}
                  <small className="answer-status">
                    {row.status === "LOCKED"
                      ? t("ux.validated")
                      : row.status === "CAPTURED"
                        ? t("ux.captured")
                        : ""}
                  </small>
                </div>
                <details className="answer-time">
                  <summary>{t("finale.answerDetails")}</summary>
                  <span>{formatRank(row.order, row.near_tie)} · </span>
                  {row.elapsed_ms !== null ? formatSeconds(row.elapsed_ms) : "—"}
                  {row.received_at_wall_ms != null && (
                    <time
                      className="muted"
                      dateTime={new Date(row.received_at_wall_ms).toISOString()}
                    >
                      {new Date(row.received_at_wall_ms).toLocaleTimeString(getLanguage())}
                    </time>
                  )}
                  {formatLate(row.late_start_ms) && (
                    <span className="late-notice">{formatLate(row.late_start_ms)}</span>
                  )}
                </details>
                <div className="score-cell">
                  {row.status === "CAPTURED" &&
                    view.rules?.captured_policy === "manual" &&
                    !row.reviewed &&
                    !row.auto_overridden &&
                    !!row.auto_evidence?.some((item) => item.status === "matched") && (
                      <div className="draft-proposal">
                        <strong>
                          {t("repair.draftPoints", {
                            points: row.auto_evidence
                              .filter(
                                (item) =>
                                  item.status === "matched" &&
                                  !round.neutralized_fields?.includes(item.criterion),
                              )
                              .reduce(
                                (sum, item) =>
                                  sum + criterionPoints(item.criterion as Criterion, view.rules),
                                0,
                              ),
                          })}
                        </strong>
                        <Button
                          disabled={busy.has(row.player_id) || pending.has(row.player_id)}
                          onClick={() => {
                            const decisions = Object.fromEntries(
                              fields.map((field) => {
                                const evidence = row.auto_evidence?.find(
                                  (item) => `${item.criterion}_correct` === field,
                                );
                                return [
                                  field,
                                  evidence?.status === "matched"
                                    ? true
                                    : evidence?.status === "not_found"
                                      ? false
                                      : null,
                                ];
                              }),
                            ) as Partial<Record<Decision, boolean | null>>;
                            score(
                              row.player_id,
                              fields.reduce(
                                (sum, field) => sum + (decisions[field] ? weights[field] : 0),
                                0,
                              ),
                              decisions,
                            );
                          }}
                        >
                          {t("repair.acceptProposal")}
                        </Button>
                      </div>
                    )}
                  {!!row.auto_evidence?.length && (
                    <p className="auto-reasons">
                      {row.auto_overridden
                        ? t("auto.overridden")
                        : row.status === "CAPTURED" && view.rules?.captured_policy === "manual"
                          ? t("auto.draftSuggestion")
                          : row.reviewed
                            ? t("repair.scoringComplete")
                            : row.auto_evidence.some(
                                  (item) =>
                                    item.status !== "matched" && item.status !== "neutralized",
                                )
                              ? t("polish.autoSummary", {
                                  count: row.auto_evidence.filter(
                                    (item) => item.status === "matched",
                                  ).length,
                                  total: row.auto_evidence.filter(
                                    (item) => item.status !== "neutralized",
                                  ).length,
                                })
                              : t(row.auto_overridden ? "auto.overridden" : "auto.confirmed")}
                    </p>
                  )}
                  <div className="score-controls">
                    {fields.map((field) => (
                      <div key={field} className="criterion row">
                        <span>
                          {criterionLabel(field.replace("_correct", "") as Criterion)} ·{" "}
                          {weights[field]}
                        </span>
                        {[true, false].map((value) => (
                          <Button
                            key={String(value)}
                            aria-pressed={row.judgement === "criteria" && row[field] === value}
                            kind={
                              row.judgement === "criteria" && row[field] === value
                                ? "primary"
                                : "secondary"
                            }
                            disabled={
                              !round.included ||
                              busy.has(row.player_id) ||
                              pending.has(row.player_id) ||
                              (capturedZero && value)
                            }
                            onClick={() => {
                              const criteria = Object.fromEntries(
                                fields.map((key) => [
                                  key,
                                  key === field
                                    ? value
                                    : row.judgement === "criteria"
                                      ? (row[key] ?? null)
                                      : null,
                                ]),
                              );
                              const points = fields.reduce(
                                (sum, key) => sum + (criteria[key] === true ? weights[key] : 0),
                                0,
                              );
                              score(row.player_id, points, criteria);
                            }}
                          >
                            {t(value ? "flow.true" : "flow.false")}
                          </Button>
                        ))}
                      </div>
                    ))}
                    {fields.length > 1 && (
                      <div className="row">
                        {[true, false].map((value) => (
                          <Button
                            key={String(value)}
                            disabled={
                              !round.included ||
                              busy.has(row.player_id) ||
                              pending.has(row.player_id) ||
                              (capturedZero && value)
                            }
                            onClick={() =>
                              score(
                                row.player_id,
                                value ? fields.reduce((sum, key) => sum + weights[key], 0) : 0,
                                Object.fromEntries(fields.map((key) => [key, value])),
                              )
                            }
                          >
                            {t(value ? "flow.allGood" : "flow.allWrong")}
                          </Button>
                        ))}
                      </div>
                    )}
                    {!row.reviewed &&
                      row.judgement === "criteria" &&
                      fields.some((field) => row[field] != null) &&
                      fields.some((field) => row[field] == null) && (
                        <Button
                          disabled={
                            !round.included || busy.has(row.player_id) || pending.has(row.player_id)
                          }
                          onClick={() =>
                            score(
                              row.player_id,
                              fields.reduce(
                                (sum, field) => sum + (row[field] === true ? weights[field] : 0),
                                0,
                              ),
                              Object.fromEntries(
                                fields.map((field) => [field, row[field] ?? false]),
                              ),
                            )
                          }
                        >
                          {t("polish.remainingWrong")}
                        </Button>
                      )}
                    <details className="manual-score">
                      <summary>{t("finale.manualPoints")}</summary>
                      <NumericDraft
                        value={row.points_draft}
                        label={t("hostui.pointsFor", { name: nameOf(view, row.player_id) })}
                        disabled={capturedZero || !round.included || pending.has(row.player_id)}
                        onBusy={(value) => markBusy(row.player_id, value)}
                        onCommit={(value) => score(row.player_id, value)}
                      />
                    </details>
                  </div>
                  {!!row.auto_evidence?.length && (
                    <details className="auto-assessment">
                      <summary>
                        {t(row.auto_overridden ? "auto.overridden" : "auto.assessment")}
                      </summary>
                      {row.auto_evidence.map((item) => (
                        <div key={item.criterion} className="auto-match">
                          <strong>
                            {t("auto.evidence", {
                              field: criterionLabel(item.criterion as Criterion),
                              score: item.similarity.toLocaleString(getLanguage(), {
                                maximumFractionDigits: 1,
                              }),
                              threshold: item.threshold,
                            })}
                          </strong>
                          <span>{t(`auto.${item.status}` as "auto.matched")}</span>
                          <small dir="auto">
                            {item.fragment ?? "—"} → {item.reference ?? "—"}
                          </small>
                        </div>
                      ))}
                    </details>
                  )}
                  {row.reviewed && row.judgement !== "criteria" && (
                    <small>{t("flow.manual")}</small>
                  )}
                  <small className="score-preview">
                    {t("ux.scorePreview", {
                      before: row.score_before ?? 0,
                      delta: formatDelta(row.points_draft),
                      after: (row.score_before ?? 0) + row.points_draft,
                    })}
                  </small>
                </div>
              </article>
            );
          })}
        </div>
      </ScoreScroll>
      <div className="publish-action">
        {undo && (
          <Button
            disabled={
              pending.size > 0 ||
              round.answers.find((row) => row.player_id === undo.playerId)?.score_revision !==
                undo.revision
            }
            onClick={() => {
              score(undo.playerId, undo.points, undo.criteria, false);
              setUndo(null);
            }}
          >
            {t("auto.undoCorrection", { name: nameOf(view, undo.playerId) })}
          </Button>
        )}
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
            {t("polish.reviewProgress", {
              count: checked,
              total: round.answers.length,
              remaining: round.answers.length - checked,
            })}
          </p>
        )}
      </div>
    </section>
  );
}
function TrackEditor({
  round,
  onBusy,
  onCancel,
  onSaved,
}: {
  readonly onCancel: () => void;
  readonly onSaved: () => void;
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
  const [aliases, setAliases] = useState<AliasValues>(track?.aliases ?? {});
  const [cleared, setCleared] = useState<NonNullable<MusicalMetadata["cleared_fields"]>>(
    (track?.cleared_fields ?? []) as NonNullable<MusicalMetadata["cleared_fields"]>,
  );
  const regrade = true;
  const [pending, setPending] = useState<number | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(false);
  const metadata: MusicalMetadata = {
    cleared_fields: cleared,
    aliases,
    title: title.trim() || null,
    artist: artist.trim() || null,
    featuring: featuring.trim() || null,
    album: album.trim() || null,
    year: year ? Number(year) : null,
  };
  const applyMetadata = (draft: MusicalMetadata) => {
    setTitle(draft.title ?? "");
    setArtist(draft.artist ?? "");
    setFeaturing(draft.featuring ?? "");
    setAlbum(draft.album ?? "");
    setYear(String(draft.year ?? ""));
    setCleared(draft.cleared_fields ?? []);
  };
  const key = JSON.stringify(metadata);
  const actual = JSON.stringify({
    cleared_fields: track?.cleared_fields ?? [],
    aliases: track?.aliases ?? {},
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
      setAliases(track?.aliases ?? {});
      setCleared((track?.cleared_fields ?? []) as NonNullable<MusicalMetadata["cleared_fields"]>);
      onSaved();
    }
  }, [round.metadata_revision, track, pending, onSaved]);
  useEffect(() => {
    onBusy(pending !== null || key !== actual);
    return () => onBusy(false);
  }, [pending, key, actual, onBusy]);
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
        const sent = game.send(
          cmd.trackMetadata(round.round_id, metadata, regrade, round.metadata_revision),
        );
        setError(!sent);
        if (sent) setPending(round.metadata_revision);
      }}
    >
      <label>
        {t("ux.trackTitle")}
        <input
          aria-label={t("ux.trackTitle")}
          maxLength={256}
          value={title}
          onChange={(e) => {
            setTitle(e.target.value);
            setCleared((old) => old.filter((key) => key !== "title"));
          }}
        />
        <MetadataFieldActions field="title" draft={metadata} onChange={applyMetadata} />
      </label>
      <label>
        {t("ux.artist")}
        <input
          aria-label={t("ux.artist")}
          maxLength={256}
          value={artist}
          onChange={(e) => {
            setArtist(e.target.value);
            setCleared((old) => old.filter((key) => key !== "artist"));
          }}
        />
        <MetadataFieldActions field="artist" draft={metadata} onChange={applyMetadata} />
      </label>
      <label>
        {t("review.featuring")}
        <input
          aria-label={t("review.featuring")}
          maxLength={256}
          value={featuring}
          onChange={(e) => {
            setFeaturing(e.target.value);
            setCleared((old) => old.filter((key) => key !== "featuring"));
          }}
        />
        <MetadataFieldActions field="featuring" draft={metadata} onChange={applyMetadata} />
      </label>
      <label>
        {t("review.album")}
        <input
          aria-label={t("review.album")}
          maxLength={256}
          value={album}
          onChange={(e) => {
            setAlbum(e.target.value);
            setCleared((old) => old.filter((key) => key !== "album"));
          }}
        />
        <MetadataFieldActions field="album" draft={metadata} onChange={applyMetadata} />
      </label>
      <label>
        {t("review.year")}
        <input
          type="number"
          aria-label={t("review.year")}
          min={1000}
          max={9999}
          value={year}
          onChange={(e) => {
            setYear(e.target.value);
            setCleared((old) => old.filter((key) => key !== "year"));
          }}
        />
        <MetadataFieldActions field="year" draft={metadata} onChange={applyMetadata} />
      </label>
      <AliasEditor value={aliases} onChange={setAliases} />
      <p className="notice">{t("repair.regradeHint")}</p>
      <div className="metadata-save-actions">
        <Button
          kind="primary"
          type="submit"
          disabled={
            pending !== null ||
            (!!year &&
              (!Number.isInteger(Number(year)) || Number(year) < 1000 || Number(year) > 9999))
          }
        >
          {t(pending !== null ? "ux.saving" : "repair.saveRegrade")}
        </Button>
        <Button
          disabled={
            pending !== null ||
            (!!year &&
              (!Number.isInteger(Number(year)) || Number(year) < 1000 || Number(year) > 9999))
          }
          onClick={() => {
            setSaved(false);
            const sent = game.send(
              cmd.trackMetadata(round.round_id, metadata, false, round.metadata_revision),
            );
            setError(!sent);
            if (sent) setPending(round.metadata_revision);
          }}
        >
          {t("repair.saveFuture")}
        </Button>
        <Button disabled={pending !== null} onClick={onCancel}>
          {t("hostui.cancel")}
        </Button>
      </div>
      {saved && key === actual && <p role="status">{t("hostui.saved")}</p>}
      {error && (
        <p role="alert" className="error">
          {t("ux.saveTimeout")}
        </p>
      )}
    </form>
  );
}
