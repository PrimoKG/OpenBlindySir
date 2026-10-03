import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";
import * as cmd from "../app/commands";
import { useGame } from "../app/hooks";
import { t, tCode } from "../i18n";
import { api } from "../net/api";
import type { HostView, LibraryIssue, ViewPlayer } from "../protocol";
import { Button } from "../ui/components";
import { HistoryPanel } from "./HistoryPanel";

export function Invite() {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const [address, setAddress] = useState(`${location.origin}/`);
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  let url = "";
  try {
    const parsed = new URL(address);
    if (["http:", "https:"].includes(parsed.protocol) && !parsed.username && !parsed.password) {
      parsed.pathname = "/";
      parsed.search = "";
      parsed.hash = "";
      url = parsed.href;
    }
  } catch {
    /* incomplete URL while typing */
  }
  useEffect(() => {
    setCopied(false);
    setFailed(false);
    if (canvas.current && url)
      void QRCode.toCanvas(canvas.current, url, {
        width: 192,
        margin: 4,
        errorCorrectionLevel: "M",
      }).catch(() => setFailed(true));
  }, [url]);
  return (
    <details className="disclosure invite">
      <summary>{t("ux.invite")}</summary>
      <div className="stack">
        <label>
          {t("ux.inviteAddress")}
          <input type="url" value={address} onChange={(e) => setAddress(e.target.value)} />
        </label>
        <p className="muted">{t("ux.inviteHint")}</p>
        {url && <canvas ref={canvas} role="img" aria-label={t("ux.qrLabel")} />}
        {!url && <p className="error">{t("ux.invalidUrl")}</p>}
        <Button
          disabled={!url}
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(url);
              setCopied(true);
            } catch {
              setFailed(true);
            }
          }}
        >
          {copied ? t("ux.copied") : t("ux.copyInvite")}
        </Button>
        {failed && (
          <p role="status">
            {t("ux.copyFallback")} {url}
          </p>
        )}
      </div>
    </details>
  );
}

export function Participation({ view }: { readonly view: HostView }) {
  const game = useGame();
  return (
    <details className="disclosure">
      <summary>{t("ux.teamsAndSpectators")}</summary>
      <p className="muted">{t("ux.teamHint")}</p>
      <ul className="list">
        {view.players.map((player) => (
          <li key={player.id}>
            <ParticipationRow
              key={`${player.id}:${player.team}:${player.spectator}`}
              player={player}
              send={(team, spectator) => game.send(cmd.participation(player.id, spectator, team))}
            />
          </li>
        ))}
      </ul>
    </details>
  );
}

function ParticipationRow({
  player,
  send,
}: {
  readonly player: ViewPlayer;
  readonly send: (team: string | null, spectator: boolean) => boolean;
}) {
  const [team, setTeam] = useState(player.team ?? "");
  return (
    <div className="participation-row">
      <strong>{player.nickname}</strong>
      <label>
        {t("ux.team")}
        <input
          maxLength={40}
          value={team}
          onChange={(e) => setTeam(e.target.value)}
          onBlur={() => {
            if (team.trim() !== (player.team ?? ""))
              send(team.trim() || null, player.spectator ?? false);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
        />
      </label>
      <label className="folder-option">
        <input
          type="checkbox"
          checked={player.spectator ?? false}
          onChange={(e) => send(team.trim() || null, e.target.checked)}
        />
        {t("ux.spectator")}
      </label>
    </div>
  );
}

export function PartyHistory({ view }: { readonly view: HostView }) {
  return <HistoryPanel view={view} />;
}

export function LibraryIssues({ view }: { readonly view: HostView }) {
  const count = view.host.pool?.unavailable ?? 0;
  const [issues, setIssues] = useState<readonly LibraryIssue[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const gameId = view.game?.game_id;
  useEffect(() => {
    if (!count || retry < 0 || !gameId) return;
    let active = true;
    void api.library().then((result) => {
      if (!active) return;
      if (result.ok) {
        setIssues(result.data.issues);
        setError(null);
      } else setError(tCode("error", result.error));
    });
    return () => {
      active = false;
    };
  }, [count, retry, gameId]);
  if (!count) return null;
  return (
    <details className="disclosure">
      <summary>
        {t("ux.libraryIssues")} ({count})
      </summary>
      {error && (
        <>
          <p className="error" role="alert">
            {error}
          </p>
          <Button onClick={() => setRetry((n) => n + 1)}>{t("app.retry")}</Button>
        </>
      )}
      <ul className="list">
        {issues.map((issue) => (
          <li key={`${issue.bridge_id}:${issue.folder}:${issue.filename}`}>
            {issue.folder ? `${issue.folder}/` : ""}
            {issue.filename} — {tCode("error", issue.code)}
          </li>
        ))}
      </ul>
    </details>
  );
}
