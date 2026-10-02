// Audio unlock recipes (spec §9.7), called INSIDE a user gesture.

interface AudioSessionNavigator {
  audioSession?: { type: string };
}

/** 0.5 s of silence as a WAV blob URL (allowed by the CSP `media-src 'self' blob:`). */
function silentWavUrl(): string {
  const sampleRate = 8000;
  const samples = sampleRate / 2;
  const buffer = new ArrayBuffer(44 + samples);
  const view = new DataView(buffer);
  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + samples, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate, true);
  view.setUint16(32, 1, true);
  view.setUint16(34, 8, true);
  text(36, "data");
  view.setUint32(40, samples, true);
  new Uint8Array(buffer, 44).fill(128);
  return URL.createObjectURL(new Blob([buffer], { type: "audio/wav" }));
}

let silentLoop: HTMLAudioElement | null = null;

/** iOS: Web Audio is muted by the silent switch unless the audio session is "playback". */
export function applyPlaybackSession(): void {
  const nav = navigator as Navigator & AudioSessionNavigator;
  if (nav.audioSession) {
    try {
      nav.audioSession.type = "playback";
      return;
    } catch {
      // fall back to the silent loop
    }
  }
  if (!silentLoop && /iPhone|iPad|iPod/.test(navigator.userAgent)) {
    silentLoop = new Audio(silentWavUrl());
    silentLoop.loop = true;
    void silentLoop.play().catch(() => undefined);
  }
}
