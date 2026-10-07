import { useEffect, useState } from "react";
import { useEngine, useGame } from "../app/hooks";
import { t } from "../i18n";
import { readLocal, writeLocal } from "../storage";
import { Button } from "../ui/components";

/** Reuses the page's audio context and volume; never interrupts a musical clip. */
export function FinaleSoundControls() {
  const game = useGame();
  const engine = useEngine();
  const [enabled, setEnabled] = useState(() => readLocal("finaleSounds") !== "off");
  const motion = useFinaleMotion();
  return (
    <section className="finale-sound-options stack">
      <label className="folder-option">
        <input
          type="checkbox"
          checked={motion}
          onChange={(event) => {
            writeLocal("finaleMotion", event.target.checked ? "on" : "off");
            window.dispatchEvent(new Event("openblindysir:finale-motion"));
          }}
        />
        {t("finale.animations")}
      </label>
      <label className="folder-option">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => {
            const next = event.target.checked;
            writeLocal("finaleSounds", next ? "on" : "off");
            setEnabled(next);
          }}
        />
        {t("experience.effects")}
      </label>
      {enabled && engine.contextState !== "running" && (
        <Button onClick={() => void game.engine.unlock()}>{t("experience.enableEffects")}</Button>
      )}
    </section>
  );
}

export function useFinaleMotion() {
  const [motion, setMotion] = useState(
    () =>
      readLocal("finaleMotion") !== "off" &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const refresh = () => setMotion(readLocal("finaleMotion") !== "off" && !media.matches);
    window.addEventListener("openblindysir:finale-motion", refresh);
    media.addEventListener("change", refresh);
    return () => {
      window.removeEventListener("openblindysir:finale-motion", refresh);
      media.removeEventListener("change", refresh);
    };
  }, []);
  return motion;
}
