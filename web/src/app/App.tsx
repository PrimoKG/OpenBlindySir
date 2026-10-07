// "/" → player, "/host" → host (elevation form first). No router (spec §3).
import { useCallback, useEffect, useMemo, useState } from "react";
import { HostApp } from "../host/HostApp";
import { t, tCode, useLanguage, useMessage } from "../i18n";
import { api } from "../net/api";
import { PlayerApp } from "../player/PlayerApp";
import type { Compatibility } from "../protocol";
import { Button, ConnectionScreen } from "../ui/components";
import { GameController } from "./controller";
import { GameContext, useGame, useUi, useView } from "./hooks";
import { HostGate, JoinScreen } from "./JoinScreen";

type Stage = "checking" | "join" | "play";

export function App() {
  useLanguage();
  const [stage, setStage] = useState<Stage>("checking");
  const [isHost, setIsHost] = useState(false);
  const [checkError, setCheckError] = useMessage(null);
  const [joinNotice, setJoinNotice] = useMessage(null);
  const wantsHost = location.pathname.startsWith("/host");

  const check = useCallback(() => {
    setCheckError(null);
    void api.session().then((result) => {
      if (result.ok) {
        if (new URLSearchParams(location.hash.slice(1)).has("join"))
          history.replaceState(null, "", location.pathname + location.search);
        setIsHost(result.data.role === "host");
        setStage("play");
      } else if (result.error === "unauthenticated") {
        setStage("join");
      } else {
        setCheckError(() => tCode("error", result.error));
      }
    });
  }, [setCheckError]);
  useEffect(check, [check]);

  const rejoin = useCallback(
    (reason: "rejoin" | "session_ended") => {
      setIsHost(false);
      setJoinNotice(() =>
        reason === "session_ended" ? t("closed.ended") : t("error.unauthenticated"),
      );
      setStage("join");
    },
    [setJoinNotice],
  );

  if (stage === "checking") {
    return (
      <ConnectionScreen
        title={checkError ?? t("app.loading")}
        description={t("app.connectionHint")}
      >
        {checkError && (
          <Button kind="primary" onClick={check}>
            {t("app.retry")}
          </Button>
        )}
      </ConnectionScreen>
    );
  }
  if (stage === "join") {
    return (
      <JoinScreen
        notice={joinNotice}
        onJoined={() => {
          if (new URLSearchParams(location.hash.slice(1)).has("join"))
            history.replaceState(null, "", location.pathname + location.search);
          setIsHost(false);
          setStage("play");
        }}
      />
    );
  }
  if (wantsHost && !isHost) {
    return <HostGate onElevated={() => setIsHost(true)} />;
  }
  return <Game onRejoin={rejoin} />;
}

function Game(props: { readonly onRejoin: (reason: "rejoin" | "session_ended") => void }) {
  const game = useMemo(() => new GameController(), []);
  useEffect(() => {
    game.start();
    return () => game.dispose();
  }, [game]);
  return (
    <GameContext.Provider value={game}>
      <GameScreens onRejoin={props.onRejoin} />
    </GameContext.Provider>
  );
}

function GameScreens(props: { readonly onRejoin: (reason: "rejoin" | "session_ended") => void }) {
  const game = useGame();
  const snapshot = useView();
  const ui = useUi();
  const { onRejoin } = props;
  useEffect(() => {
    if (ui.socket === "rejoin" || ui.socket === "session_ended") {
      onRejoin(ui.socket);
    }
  }, [ui.socket, onRejoin]);

  if (ui.socket === "incompatible") return <Incompatible initial={ui.compatibility} />;

  if (ui.socket === "superseded") {
    return (
      <ConnectionScreen title={t("closed.superseded")}>
        <Button kind="primary" onClick={() => game.socket.resume()}>
          {t("closed.resume")}
        </Button>
      </ConnectionScreen>
    );
  }
  if (ui.socket === "kicked") {
    return <ConnectionScreen title={t("closed.kicked")} />;
  }
  if (!snapshot) {
    return (
      <ConnectionScreen
        title={ui.socket === "reconnecting" ? t("banner.reconnecting") : t("app.loading")}
        description={t("app.connectionHint")}
      />
    );
  }
  const view = snapshot.view;
  return view.kind === "player" ? <PlayerApp view={view} /> : <HostApp view={view} />;
}

function Incompatible({ initial }: { readonly initial: Compatibility | null }) {
  const [info, setInfo] = useState(initial);
  useEffect(() => {
    if (initial) return;
    let active = true;
    void api.compatibility().then((result) => {
      if (active && result.ok) setInfo(result.data);
    });
    return () => {
      active = false;
    };
  }, [initial]);
  return (
    <ConnectionScreen title={t("error.protocol_mismatch")} description={t("compatibility.action")}>
      {info && (
        <p role="status">
          {t("compatibility.required", {
            version: info.server_version,
            min: info.protocol_min,
            max: info.protocol_max,
          })}
        </p>
      )}
      <Button kind="primary" onClick={() => location.reload()}>
        {t("compatibility.reload")}
      </Button>
    </ConnectionScreen>
  );
}
