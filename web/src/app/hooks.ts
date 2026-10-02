import { createContext, useContext, useEffect, useState, useSyncExternalStore } from "react";
import type { EngineSnapshot } from "../audio/engine";
import type { ViewSnapshot } from "../net/viewStore";
import type { GameController, UiState } from "./controller";

export const GameContext = createContext<GameController | null>(null);

export function useGame(): GameController {
  const game = useContext(GameContext);
  if (!game) {
    throw new Error("GameContext missing");
  }
  return game;
}

export function useView(): ViewSnapshot | null {
  const game = useGame();
  return useSyncExternalStore(game.store.subscribe, game.store.getSnapshot);
}

export function useEngine(): EngineSnapshot {
  const game = useGame();
  return useSyncExternalStore(game.engine.subscribe, game.engine.getSnapshot);
}

export function useUi(): UiState {
  const game = useGame();
  return useSyncExternalStore(game.subscribeUi, game.getUi);
}

/** Server time estimate (ms), refreshed every animation frame while ``active``. */
export function useServerNow(active: boolean): number {
  const game = useGame();
  const [now, setNow] = useState(() => performance.now() + (game.clock.estimate()?.offset ?? 0));
  useEffect(() => {
    if (!active) {
      return;
    }
    let frame = 0;
    const tick = () => {
      setNow(performance.now() + (game.clock.estimate()?.offset ?? 0));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [active, game]);
  return now;
}
