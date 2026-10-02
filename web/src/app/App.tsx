// "/" → player, "/host" → host (elevation form first). No router (spec §3).
import { useEffect, useMemo, useState } from "react";
import { HostApp } from "../host/HostApp";
import { t } from "../i18n";
import { api } from "../net/api";
import { PlayerApp } from "../player/PlayerApp";
import { Button } from "../ui/components";
import { GameController } from "./controller";
import { GameContext, useGame, useUi, useView } from "./hooks";
import { HostGate, JoinScreen } from "./JoinScreen";

type Stage = "checking" | "join" | "play";

export function App() {
  const [stage, setStage] = useState<Stage>("checking");
  const [isHost, setIsHost] = useState(false);
  const wantsHost = location.pathname.startsWith("/host");

  useEffect(() => {
    void api.session().then((result) => {
      if (result.ok) {
        setIsHost(result.data.role === "host");
        setStage("play");
      } else {
        setStage("join");
      }
    });
  }, []);

  if (stage === "checking") {
    return <p className="center">{t("app.loading")}</p>;
  }
  if (stage === "join") {
    return <JoinScreen onJoined={() => setStage("play")} />;
  }
  if (wantsHost && !isHost) {
    return <HostGate onElevated={() => setIsHost(true)} />;
  }
  return <Game onRejoin={() => setStage("join")} />;
}

function Game(props: { readonly onRejoin: () => void }) {
  const game = useMemo(() => new GameController(), []);
  useEffect(() => {
    game.start();
    return () => game.socket.close();
  }, [game]);
  return (
    <GameContext.Provider value={game}>
      <GameScreens onRejoin={props.onRejoin} />
    </GameContext.Provider>
  );
}

function GameScreens(props: { readonly onRejoin: () => void }) {
  const game = useGame();
  const snapshot = useView();
  const ui = useUi();
  const { onRejoin } = props;
  useEffect(() => {
    if (ui.socket === "rejoin" || ui.socket === "session_ended") {
      onRejoin();
    }
  }, [ui.socket, onRejoin]);

  if (ui.socket === "superseded") {
    return (
      <main className="center">
        <p>{t("closed.superseded")}</p>
        <Button kind="primary" onClick={() => game.socket.resume()}>
          {t("closed.resume")}
        </Button>
      </main>
    );
  }
  if (ui.socket === "kicked") {
    return (
      <main className="center">
        <p>{t("closed.kicked")}</p>
      </main>
    );
  }
  if (!snapshot) {
    return <p className="center">{t("app.loading")}</p>;
  }
  const view = snapshot.view;
  return view.kind === "player" ? <PlayerApp view={view} /> : <HostApp view={view} />;
}
