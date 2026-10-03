import { t } from "../i18n";
import { formatDelta, formatRank, formatSeconds } from "../i18n/format";
import type { FinalReviewRow, GameRecord, ViewPlayer } from "../protocol";
import { Button } from "../ui/components";

export function PlayerHistory({ row }: { readonly row: FinalReviewRow }) {
  return (
    <div className="history-details">
      <ol className="history-list">
        {row.history.map((entry) => (
          <li key={entry.round_id}>
            <div className="row wrap">
              <strong>{t("ux.historyRound", { number: entry.number })}</strong>
              <span>{entry.track?.title ?? entry.track?.display_name ?? "—"}</span>
              {entry.track?.artist && <small>{entry.track.artist}</small>}
              <small>
                {[entry.track?.featuring, entry.track?.album, entry.track?.year]
                  .filter(Boolean)
                  .join(" · ")}
              </small>
              {!entry.included && <small>{t("review.cancelledShort")}</small>}
            </div>
            <p className="history-answer">{entry.text ?? t("round.noAnswer")}</p>
            <div className="history-meta">
              <span>
                {entry.status === "CAPTURED"
                  ? t("ux.captured")
                  : entry.status === "LOCKED"
                    ? t("ux.validated")
                    : t("round.noAnswer")}
              </span>
              <span>{entry.elapsed_ms !== null ? formatSeconds(entry.elapsed_ms) : "—"}</span>
              {entry.received_at_wall_ms != null && (
                <time dateTime={new Date(entry.received_at_wall_ms).toISOString()}>
                  {new Date(entry.received_at_wall_ms).toLocaleTimeString()}
                </time>
              )}
              <span>{formatRank(entry.order, entry.near_tie)}</span>
              <strong>{formatDelta(entry.points)}</strong>
            </div>
          </li>
        ))}
      </ol>
      {row.adjustments.length > 0 && (
        <ul className="list">
          {row.adjustments.map((entry, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: immutable journal entries have no public id
            <li key={`${index}:${entry.delta}:${entry.note}`}>
              {t("final.correction")} {formatDelta(entry.delta)}
              {entry.round_number
                ? ` · ${t("ux.historyRound", { number: entry.round_number })}`
                : ""}
              {entry.note ? ` · ${entry.note}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function recapCsv(record: GameRecord): string {
  const cell = (value: string | number | null | undefined): string => {
    let text = String(value ?? "");
    if (typeof value === "string" && /^[\s]*[=+\-@]/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  };
  const name = (id: string) => record.players.find((p) => p.id === id)?.nickname ?? id;
  const rows: (string | number | null | undefined)[][] = [
    [
      "game",
      "player",
      "team",
      "round",
      "title",
      "artist",
      "answer",
      "status",
      "elapsed_ms",
      "order",
      "points",
      "correction",
      "note",
      "final_score",
      "featuring",
      "album",
      "year",
      "received_at_wall_ms",
      "included",
      "near_tie",
    ],
  ];
  for (const row of record.results.recap ?? []) {
    const team = record.players.find((p) => p.id === row.player_id)?.team;
    for (const h of row.history)
      rows.push([
        record.game_id,
        name(row.player_id),
        team,
        h.number,
        h.track?.title ?? h.track?.display_name,
        h.track?.artist,
        h.text,
        h.status,
        h.elapsed_ms,
        h.order,
        h.points,
        0,
        "",
        row.score_after,
        h.track?.featuring,
        h.track?.album,
        h.track?.year,
        h.received_at_wall_ms,
        h.included ? 1 : 0,
        h.near_tie ? 1 : 0,
      ]);
    for (const a of row.adjustments)
      rows.push([
        record.game_id,
        name(row.player_id),
        team,
        a.round_number,
        "",
        "",
        "",
        "adjustment",
        "",
        "",
        0,
        a.delta,
        a.note,
        row.score_after,
        "",
        "",
        "",
        "",
        "",
        "",
      ]);
    for (const a of record.results.final_adjustments.filter((a) => a.player_id === row.player_id))
      rows.push([
        record.game_id,
        name(row.player_id),
        team,
        "",
        "",
        "",
        "",
        "final_adjustment",
        "",
        "",
        0,
        a.delta,
        "",
        row.score_after,
        "",
        "",
        "",
        "",
        "",
        "",
      ]);
    if (row.history.length === 0 && row.adjustments.length === 0)
      rows.push([
        record.game_id,
        name(row.player_id),
        team,
        "",
        "",
        "",
        "",
        "summary",
        "",
        "",
        0,
        0,
        "",
        row.score_after,
        "",
        "",
        "",
        "",
        "",
        "",
      ]);
  }
  return `\uFEFF${rows.map((row) => row.map(cell).join(";")).join("\r\n")}\r\n`;
}

function download(data: string, type: string, filename: string) {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ExportResults({ record }: { readonly record: GameRecord }) {
  return (
    <div className="row wrap">
      <Button
        onClick={() =>
          download(
            recapCsv(record),
            "text/csv;charset=utf-8",
            `openblindysir-${record.game_id}.csv`,
          )
        }
      >
        {t("ux.exportCsv")}
      </Button>
      <Button
        onClick={() =>
          download(
            JSON.stringify(record, null, 2),
            "application/json",
            `openblindysir-${record.game_id}.json`,
          )
        }
      >
        {t("ux.exportJson")}
      </Button>
    </div>
  );
}

export function Recap({
  rows,
  players,
}: {
  readonly rows: readonly FinalReviewRow[];
  readonly players: readonly ViewPlayer[];
}) {
  return (
    <section className="recap">
      <h2>{t("ux.recap")}</h2>
      {rows.map((row) => (
        <details className="disclosure" key={row.player_id}>
          <summary>
            {players.find((p) => p.id === row.player_id)?.nickname ?? "?"} ·{" "}
            {t("standings.points", { score: row.score_after })}
          </summary>
          <PlayerHistory row={row} />
        </details>
      ))}
    </section>
  );
}
