import { useEffect, useRef, useState } from "react";
import { getLanguage, t, tCode, useMessage } from "../i18n";
import { api } from "../net/api";
import { ExportResults, Recap } from "../player/Recap";
import type { GameRecord, HistoryResponse, HostView } from "../protocol";
import { Button, ConfirmDialog } from "../ui/components";

/** History is fetched on demand; its private answers never inflate game STATE messages. */
export function HistoryPanel({ view }: { readonly view: HostView }) {
  const [open, setOpen] = useState(false);
  const [list, setList] = useState<HistoryResponse | null>(null);
  const [record, setRecord] = useState<GameRecord | null>(null);
  const [error, setError] = useMessage(null);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [deletion, setDeletion] = useState<string | "all" | null>(null);
  const summary = useRef<HTMLElement>(null);
  const canRead = view.phase !== "IN_GAME" || view.kind === "host_mc";
  // biome-ignore lint/correctness/useExhaustiveDependencies: server count and explicit retries invalidate the HTTP list
  useEffect(() => {
    if (!open || !canRead) return;
    let active = true;
    setBusy(true);
    void api.history().then((result) => {
      if (!active) return;
      setBusy(false);
      if (result.ok) {
        setList(result.data);
        setError(null);
        setRecord((old) =>
          old && result.data.items.some((item) => item.game_id === old.game_id) ? old : null,
        );
      } else setError(() => tCode("error", result.error));
    });
    return () => {
      active = false;
    };
  }, [open, canRead, view.host.history_count, revision]);
  if (!canRead) return null;
  const load = async (id: string) => {
    setBusy(true);
    setError(null);
    const result = await api.historyRecord(id);
    setBusy(false);
    if (result.ok) setRecord(result.data);
    else setError(() => tCode("error", result.error));
  };
  const remove = async () => {
    if (deletion === null || busy) return;
    const target = deletion;
    setDeletion(null);
    setBusy(true);
    const result = await api.deleteHistory(target === "all" ? undefined : target);
    setBusy(false);
    if (result.ok) {
      setRecord(null);
      setRevision((n) => n + 1);
      summary.current?.focus();
    } else setError(() => tCode("error", result.error));
  };
  return (
    <details
      className="disclosure party-history"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary ref={summary}>
        {t("ux.partyHistory")} ({view.host.history_count})
      </summary>
      <div className="stack" aria-busy={busy}>
        <p className="muted">
          {t("history.privacy", { days: list?.retention_days ?? 90, count: list?.max_games ?? 50 })}
        </p>
        {busy && <p role="status">{t("app.loading")}</p>}
        {error && (
          <p className="error" role="alert">
            {error} <Button onClick={() => setRevision((n) => n + 1)}>{t("app.retry")}</Button>
          </p>
        )}
        {list && !list.durable && (
          <p role="status" className="notice">
            {t("history.notDurable")}
          </p>
        )}
        {list?.items.length === 0 && <p role="status">{t("history.empty")}</p>}
        <ul className="list history-picker">
          {list?.items.map((item) => (
            <li key={item.game_id} className="row wrap">
              <Button
                disabled={busy}
                aria-pressed={record?.game_id === item.game_id}
                onClick={() => void load(item.game_id)}
              >
                {new Date(item.finished_at).toLocaleString(getLanguage())} ·{" "}
                {t("results.rounds", { count: item.rounds_played })} ·{" "}
                {t("history.participants", { count: item.participants })}
              </Button>
              <Button
                kind="danger"
                disabled={busy}
                aria-label={t("history.deleteNamed", {
                  date: new Date(item.finished_at).toLocaleString(getLanguage()),
                })}
                onClick={() => setDeletion(item.game_id)}
              >
                {t("history.delete")}
              </Button>
            </li>
          ))}
        </ul>
        {record && (
          <section className="stack" aria-label={t("history.recap")}>
            <h3>{new Date(record.finished_at).toLocaleString(getLanguage())}</h3>
            <ExportResults record={record} />
            {record.teams.length > 0 && (
              <>
                <h3>{t("flow.teamRanking")}</h3>
                <ul className="list">
                  {record.teams.map((team) => (
                    <li key={team.team}>
                      {team.rank}. {team.team} — {t("history.score", { count: team.score })}
                    </li>
                  ))}
                </ul>
                <p>{t("flow.unassigned")}</p>
                <h3>{t("flow.individual")}</h3>
              </>
            )}
            <ul className="list">
              {record.results.standings.map((row) => (
                <li key={row.player_id}>
                  {row.rank}.{" "}
                  {record.players.find((p) => p.id === row.player_id)?.nickname ?? row.player_id} —{" "}
                  {t("history.score", { count: row.score })}
                </li>
              ))}
            </ul>
            {!!record.results.unreviewed_answers && (
              <p className="notice">
                {t("polish.incompleteResults", { count: record.results.unreviewed_answers })}
              </p>
            )}
            <Recap rows={record.results.recap} players={record.players} />
          </section>
        )}
        {!!list?.items.length && (
          <Button kind="danger" disabled={busy} onClick={() => setDeletion("all")}>
            {t("history.purge")}
          </Button>
        )}
      </div>
      <ConfirmDialog
        open={deletion !== null}
        title={t(deletion === "all" ? "history.purge" : "history.delete")}
        message={t(deletion === "all" ? "history.purgeConfirm" : "history.deleteConfirm")}
        onCancel={() => setDeletion(null)}
        onConfirm={() => void remove()}
      />
    </details>
  );
}
