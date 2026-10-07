import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { GameController } from "../src/app/controller";
import { ClockEstimator } from "../src/audio/clock";
import { AudioEngine } from "../src/audio/engine";
import { api } from "../src/net/api";
import { GameSocket } from "../src/net/socket";
import { createViewStore } from "../src/net/viewStore";
import type { AnyView, AudioStatus, SessionResponse } from "../src/protocol";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function view(id: string, play = false) {
  return {
    audio: { current: { asset_id: id, url: `/${id}` }, next: null },
    play: play
      ? { play_id: `play-${id}`, asset_id: id, start_at: performance.now(), clip_offset: 0 }
      : null,
    paused: null,
  } as unknown as AnyView;
}
let latestContext: { state: string; onstatechange: (() => void) | null };
const webSockets: { close: ReturnType<typeof vi.fn> }[] = [];
beforeEach(() => {
  vi.stubGlobal("localStorage", { getItem: () => null, setItem: vi.fn() });
  vi.stubGlobal("navigator", { userAgent: "audit" });
  vi.stubGlobal("location", { protocol: "http:", host: "localhost:8765" });
  vi.stubGlobal("window", globalThis);
  webSockets.length = 0;
  vi.stubGlobal(
    "WebSocket",
    class {
      static OPEN = 1;
      readyState = 0;
      constructor() {
        webSockets.push(this);
      }
      close = vi.fn();
      send = vi.fn();
    },
  );
  vi.stubGlobal(
    "AudioContext",
    class {
      state = "running";
      currentTime = 0;
      destination = {};
      onstatechange: (() => void) | null = null;
      constructor() {
        latestContext = this;
      }
      close() {
        this.state = "closed";
        return Promise.resolve();
      }
      resume() {
        return this.state === "closed" ? Promise.reject(new Error("closed")) : Promise.resolve();
      }
      createGain() {
        return { gain: { value: 0 }, connect: vi.fn() };
      }
      decodeAudioData() {
        return Promise.resolve({ duration: 12 });
      }
      createBufferSource() {
        return { connect: vi.fn(), start: vi.fn(), stop: vi.fn(), onended: null };
      }
    },
  );
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("ignores an obsolete download failure while the next clip is playing", async () => {
  vi.useFakeTimers();
  const old = deferred<Response>();
  const clip = { ok: true, arrayBuffer: () => Promise.resolve(new ArrayBuffer(10)) };
  let oldAttempts = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn((url) => {
      if (url === "/old")
        return oldAttempts++ === 0 ? old.promise : Promise.reject(new Error("old failed"));
      return Promise.resolve(clip);
    }),
  );
  const engine = new AudioEngine(new ClockEstimator(), () => true);
  await engine.unlock();
  engine.syncWithView(view("old"));
  engine.syncWithView(view("new", true));
  await vi.advanceTimersByTimeAsync(0);
  expect(engine.getSnapshot().state).toBe("PLAYING");
  old.reject(new Error("old failed"));
  await vi.advanceTimersByTimeAsync(4000);
  expect(engine.getSnapshot().state).toBe("PLAYING");
  expect(engine.status().asset_id).toBe("new");
});

function socket() {
  return new GameSocket({
    store: createViewStore(),
    clock: new ClockEstimator(),
    onCritical: vi.fn(),
    onStatus: vi.fn(),
    audioStatus: () => ({}) as AudioStatus,
  });
}
it("closing during the session check prevents a late socket", async () => {
  const session = deferred<{ ok: true; data: SessionResponse }>();
  vi.spyOn(api, "session").mockReturnValue(session.promise);
  const client = socket();
  const connecting = client.connect();
  client.close();
  session.resolve({ ok: true, data: {} as SessionResponse });
  await connecting;
  expect(webSockets).toHaveLength(0);
});
it("overlapping connect attempts share one socket", async () => {
  const session = deferred<{ ok: true; data: SessionResponse }>();
  vi.spyOn(api, "session").mockReturnValue(session.promise);
  const client = socket();
  const first = client.connect();
  const second = client.connect();
  session.resolve({ ok: true, data: {} as SessionResponse });
  await Promise.all([first, second]);
  expect(webSockets).toHaveLength(1);
  client.close();
  expect(webSockets[0]?.close).toHaveBeenCalledTimes(1);
});
it("a user gesture recovers a permanently closed audio context", async () => {
  const engine = new AudioEngine(new ClockEstimator(), () => true);
  await engine.unlock();
  const context = latestContext;
  context.state = "closed";
  context.onstatechange?.();
  await engine.unlock();
  expect(latestContext).not.toBe(context);
  expect(engine.getSnapshot().contextState).toBe("running");
  expect(engine.getSnapshot().state).toBe("IDLE");
});
it("disposing the controller stops audio and removes document listeners", async () => {
  const addEventListener = vi.fn();
  const removeEventListener = vi.fn();
  vi.stubGlobal("document", { addEventListener, removeEventListener });
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({ ok: true, arrayBuffer: () => Promise.resolve(new ArrayBuffer(10)) }),
    ),
  );
  vi.spyOn(api, "session").mockResolvedValue({ ok: true, data: {} as SessionResponse });
  const game = new GameController();
  game.start();
  await game.engine.unlock();
  game.engine.syncWithView(view("current", true));
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  expect(game.engine.getSnapshot().state).toBe("PLAYING");
  game.dispose();
  expect(game.engine.getSnapshot().state).toBe("LOCKED");
  expect(addEventListener).toHaveBeenCalledTimes(1);
  expect(removeEventListener).toHaveBeenCalledWith(
    "visibilitychange",
    addEventListener.mock.calls[0]?.[1],
  );
});
