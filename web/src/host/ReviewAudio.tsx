import { useEffect, useRef, useState } from "react";
import { t } from "../i18n";
import type { ReviewRound } from "../protocol";
import { Button } from "../ui/components";

/** An independent host player. Only one short reencoded segment is held in the browser. */
export function ReviewAudio({ round }: { readonly round: ReviewRound }) {
  const audio = useRef<HTMLAudioElement>(null);
  const objectUrl = useRef<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const seeking = useRef(false);
  const latestVolume = useRef(0.8);
  const [mode, setMode] = useState<"excerpt" | "full">("excerpt");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [base, setBase] = useState(0);
  const [position, setPosition] = useState(0);
  const [volume, setVolume] = useState(0.8);
  const duration = (mode === "full" ? round.track_duration_ms : round.excerpt_duration_ms) ?? 0;
  useEffect(
    () => () => {
      generation.current++;
      request.current?.abort();
      audio.current?.pause();
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    },
    [],
  );
  const load = async (selected: "excerpt" | "full", offset = 0, autoplay = true) => {
    const version = ++generation.current;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    audio.current?.pause();
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = null;
    if (audio.current) {
      audio.current.removeAttribute("src");
      audio.current.load();
    }
    seeking.current = false;
    setPlaying(false);
    setMode(selected);
    setBase(offset);
    setPosition(offset);
    setLoaded(false);
    setLoading(true);
    setError(false);
    try {
      const response = await fetch(
        `/api/host/review/${round.round_id}/audio?mode=${selected}&offset=${offset}`,
        { credentials: "same-origin", cache: "no-store", signal: controller.signal },
      );
      if (!response.ok) throw new Error("unavailable");
      const data = await response.blob();
      if (version !== generation.current) return;
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      objectUrl.current = URL.createObjectURL(data);
      const player = audio.current;
      if (!player) return;
      player.src = objectUrl.current;
      player.volume = latestVolume.current;
      player.load();
      setLoaded(true);
      setBase(offset);
      setPosition(offset);
      setLoading(false);
      if (autoplay) await player.play();
    } catch {
      if (version === generation.current) {
        setLoading(false);
        setError(true);
      }
    }
  };
  const seek = (value: number) => {
    const player = audio.current;
    if (player && loaded && value >= base && value < base + (player.duration || 0)) {
      player.currentTime = value - base;
      setPosition(value);
    } else if (mode === "full") void load("full", value, playing);
  };
  const clock = (seconds: number) =>
    `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
  const play = () => {
    setError(false);
    void audio.current?.play().catch(() => setError(true));
  };
  return (
    <section className="review-audio stack" aria-label={t("review.listen")}>
      <div className="row wrap">
        <strong>{t(mode === "full" ? "review.full" : "review.excerpt")}</strong>
        <Button
          disabled={loading}
          onClick={() => {
            if (!loaded) void load(mode, base);
            else if (playing) audio.current?.pause();
            else play();
          }}
        >
          {t(playing ? "review.pause" : "review.play")}
        </Button>
        <Button disabled={loading} onClick={() => void load(mode === "full" ? "excerpt" : "full")}>
          {t(mode === "full" ? "review.backExcerpt" : "review.listenFull")}
        </Button>
      </div>
      {/* biome-ignore lint/a11y/useMediaCaption: audio-only musical clips have no speech captions */}
      <audio
        ref={audio}
        preload="none"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onTimeUpdate={() => {
          if (loaded && !seeking.current) setPosition(base + (audio.current?.currentTime ?? 0));
        }}
        onError={() => {
          if (objectUrl.current) {
            setLoaded(false);
            setPlaying(false);
            setError(true);
          }
        }}
        onEnded={() => {
          if (mode === "full" && base + (audio.current?.duration ?? 0) < duration / 1000 - 0.1)
            void load("full", Math.min(duration / 1000 - 0.1, base + 30));
          else setPlaying(false);
        }}
      />
      <label>
        {t("review.progress")}
        <input
          type="range"
          min={0}
          max={Math.max(0, duration / 1000 - 0.05)}
          step={0.1}
          value={Math.min(position, duration / 1000)}
          aria-valuetext={`${clock(position)} / ${clock(duration / 1000)}`}
          disabled={!loaded || loading}
          onChange={(e) => {
            seeking.current = true;
            setPosition(Number(e.target.value));
          }}
          onPointerUp={(e) => {
            seeking.current = false;
            seek(Number(e.currentTarget.value));
          }}
          onKeyUp={(e) => {
            seeking.current = false;
            seek(Number(e.currentTarget.value));
          }}
          onBlur={(e) => {
            if (seeking.current) {
              seeking.current = false;
              seek(Number(e.currentTarget.value));
            }
          }}
        />
      </label>
      <p className="muted">
        {clock(position)} / {clock(duration / 1000)}
      </p>
      <label>
        {t("audio.volume")}
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={volume}
          onChange={(e) => {
            const value = Number(e.target.value);
            latestVolume.current = value;
            setVolume(value);
            if (audio.current) audio.current.volume = value;
          }}
        />
      </label>
      {loading && <p role="status">{t("app.loading")}</p>}
      {error && (
        <p role="alert" className="error">
          {t("review.audioError")}{" "}
          <Button
            onClick={() => {
              if (loaded) play();
              else void load(mode, base);
            }}
          >
            {t("app.retry")}
          </Button>
        </p>
      )}
      {mode === "full" && <p className="muted">{t("review.fullHint")}</p>}
    </section>
  );
}
