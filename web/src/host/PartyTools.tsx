import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";
import * as cmd from "../app/commands";
import { useGame } from "../app/hooks";
import { t, tCode, useMessage } from "../i18n";
import { api } from "../net/api";
import type { HostView, LibraryIssue, ViewPlayer } from "../protocol";
import { Button, ConfirmDialog } from "../ui/components";
import { HistoryPanel } from "./HistoryPanel";

export function Invite() {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const [address, setAddress] = useState(`${location.origin}/`);
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const [access, setAccess] = useState<{
    code: string;
    invitation: string;
    requests: readonly { request_id: string; nickname: string; reference: string }[];
  } | null>(null);
  const [newCode, setNewCode] = useState("");
  const [rotate, setRotate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useMessage(null);
  useEffect(() => {
    let alive = true;
    const refresh = async () => {
      const result = await api.access();
      if (!alive) return;
      if (result.ok) {
        setError(null);
        setAccess(result.data);
        window.dispatchEvent(
          new CustomEvent("openblindysir:claims", { detail: result.data.requests.length }),
        );
      } else setError(() => tCode("error", result.error));
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [setError]);
  let url = "";
  try {
    const parsed = new URL(address);
    if (["http:", "https:"].includes(parsed.protocol) && !parsed.username && !parsed.password) {
      parsed.pathname = "/";
      parsed.search = "";
      parsed.hash = access ? `join=${access.invitation}` : "";
      url = access ? parsed.href : "";
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
    <details className="disclosure invite" open={access?.requests.length ? true : undefined}>
      <summary>{t("ux.invite")}</summary>
      <div className="stack">
        <label>
          {t("ux.inviteAddress")}
          <input type="url" value={address} onChange={(e) => setAddress(e.target.value)} />
        </label>
        <p className="muted">{t("session.invitationHint")}</p>
        {access && (
          <p>
            <strong>
              {t("session.commonCode")} : {access.code}
            </strong>
          </p>
        )}
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
        <p className="muted">{t("session.rotateHint")}</p>
        <details className="disclosure https-help">
          <summary>{t("https.title")}</summary>
          <p>{t("https.explanation")}</p>
          <p>{t("https.host")}</p>
          <p>
            <strong>Windows</strong> · {t("https.windows")}
          </p>
          <p>
            <strong>iPhone / iPad</strong> · {t("https.apple")}
          </p>
          <p>
            <strong>Android</strong> · {t("https.android")}
          </p>
          <p className="muted">{t("https.verify")}</p>
        </details>
        <label>
          {t("session.newCode")}
          <input
            value={newCode}
            minLength={6}
            maxLength={16}
            pattern="[A-Z2-9]{6,16}"
            onChange={(event) => setNewCode(event.target.value.toUpperCase())}
          />
        </label>
        <div className="row wrap">
          <Button
            disabled={busy}
            onClick={() => {
              setNewCode("");
              setRotate(true);
            }}
          >
            {t("session.rotate")}
          </Button>
          <Button
            disabled={busy || !/^[A-Z2-9]{6,16}$/.test(newCode)}
            onClick={() => setRotate(true)}
          >
            {t("session.changeCode")}
          </Button>
        </div>
        <ConfirmDialog
          open={rotate}
          title={t("session.rotate")}
          message={t("session.rotateHint")}
          onCancel={() => {
            if (!busy) setRotate(false);
          }}
          onConfirm={() => {
            if (busy) return;
            setBusy(true);
            setError(null);
            void api.rotateAccess(newCode || undefined).then(async (result) => {
              if (result.ok) {
                const updated = await api.access();
                if (updated.ok) setAccess(updated.data);
                setRotate(false);
              } else setError(() => tCode("error", result.error));
              setBusy(false);
            });
          }}
        />
        {!!access?.requests.length && <p className="muted">{t("session.claimHostHint")}</p>}
        {access?.requests.map((item) => (
          <div className="row wrap" key={item.request_id}>
            <strong>{item.nickname}</strong>
            <span>{t("session.claimReference", { reference: item.reference })}</span>
            {[true, false].map((approve) => (
              <Button
                key={String(approve)}
                disabled={busy}
                onClick={() => {
                  setBusy(true);
                  void api.decideAccess(item.request_id, approve).then(async (result) => {
                    if (result.ok) {
                      const updated = await api.access();
                      if (updated.ok) {
                        setAccess(updated.data);
                        window.dispatchEvent(
                          new CustomEvent("openblindysir:claims", {
                            detail: updated.data.requests.length,
                          }),
                        );
                      }
                    } else setError(() => tCode("error", result.error));
                    setBusy(false);
                  });
                }}
              >
                {t(approve ? "session.approveClaim" : "session.rejectClaim", {
                  name: item.nickname,
                })}
              </Button>
            ))}
          </div>
        ))}
        {error && (
          <p role="alert" className="error">
            {error}
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
  const [error, setError] = useMessage(null);
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
      } else setError(() => tCode("error", result.error));
    });
    return () => {
      active = false;
    };
  }, [count, retry, gameId, setError]);
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
