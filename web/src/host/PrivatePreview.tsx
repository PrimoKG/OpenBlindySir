import { useEffect, useRef, useState } from "react";
import { useEngine } from "../app/hooks";
import { t } from "../i18n";
import type { LibraryTrack } from "../protocol";
import { Button } from "../ui/components";

/** One bounded, private midpoint segment; no public game PLAY or track consumption. */
export function PrivatePreview({ track }: { readonly track: LibraryTrack }) {
  const audio = useRef<HTMLAudioElement>(null);
  const request = useRef<AbortController | null>(null);
  const objectUrl = useRef<string | null>(null);
  const generation = useRef(0);
  const engine = useEngine();
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [position, setPosition] = useState(0);
  const identity = `library:${track.bridge_id}:${track.track_id}`;
  const stop = () => {
    generation.current++;
    request.current?.abort();
    request.current = null;
    audio.current?.pause();
    setPlaying(false);
    setLoading(false);
  };
  const mediaError = () => {
    const player = audio.current;
    if (!player?.hasAttribute("src")) return;
    stop();
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = null;
    player.removeAttribute("src");
    player.load();
    setLoaded(false);
    setPosition(0);
    setError(true);
  };
  useEffect(() => {
    const player = audio.current;
    const onPrivate = (event: Event) => {
      if ((event as CustomEvent<string>).detail !== identity) {
        generation.current++;
        request.current?.abort();
        player?.pause();
        setPlaying(false);
        setLoading(false);
      }
    };
    window.addEventListener("openblindysir:private-audio", onPrivate);
    return () => {
      generation.current++;
      request.current?.abort();
      player?.pause();
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      window.removeEventListener("openblindysir:private-audio", onPrivate);
    };
  }, [identity]);
  useEffect(() => {
    if (audio.current) audio.current.volume = engine.volume;
  }, [engine.volume]);
  const listen = async () => {
    window.dispatchEvent(new CustomEvent("openblindysir:private-audio", { detail: identity }));
    setError(false);
    const player = audio.current;
    if (!player) return;
    const version = ++generation.current;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    try {
      if (!loaded) {
        setLoading(true);
        const response = await fetch(
          `/api/host/library/${track.bridge_id}/${track.track_id}/preview`,
          { credentials: "same-origin", cache: "no-store", signal: controller.signal },
        );
        if (!response.ok) throw new Error("preview");
        const blob = await response.blob();
        if (generation.current !== version) return;
        if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
        objectUrl.current = URL.createObjectURL(blob);
        player.src = objectUrl.current;
        player.volume = engine.volume;
        setLoaded(true);
      }
      if (generation.current !== version) return;
      setLoading(false);
      player.currentTime = 0;
      await player.play();
    } catch {
      if (version === generation.current && !controller.signal.aborted) {
        setLoading(false);
        setError(true);
      }
    }
  };
  // biome-ignore lint/correctness/useExhaustiveDependencies: start this identity once when the host chooses its preview.
  useEffect(() => {
    void listen();
  }, [identity]);
  return (
    <section className="private-preview stack" aria-label={t("library.previewPrivate")}>
      <p className="muted">{t("library.previewPrivate")}</p>
      <div className="row wrap">
        <Button onClick={() => void listen()} disabled={loading || playing}>
          {t(loading ? "library.previewBusy" : "library.preview")}
        </Button>
        {(loading || playing) && <Button onClick={stop}>{t("library.previewStop")}</Button>}
        {loaded && (
          <span>
            {Math.floor(position)} / {Math.ceil(audio.current?.duration || 15)} s
          </span>
        )}
      </div>
      {error && (
        <p className="error" role="alert">
          {t("library.previewError")}
        </p>
      )}
      {/* biome-ignore lint/a11y/useMediaCaption: Private music identification excerpt; no spoken UI instructions. */}
      <audio
        ref={audio}
        onError={mediaError}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={() => setPosition(audio.current?.currentTime || 0)}
      />
    </section>
  );
}
