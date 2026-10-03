import { describe, expect, it } from "vitest";
import * as cmd from "../src/app/commands";
import { en } from "../src/i18n/en";
import {
  formatCount,
  formatDelta,
  formatLate,
  formatRank,
  formatSeconds,
} from "../src/i18n/format";
import { fr } from "../src/i18n/fr";
import { format } from "../src/i18n/index";
import { nextDelay } from "../src/net/backoff";
import { closeAction } from "../src/net/closeCodes";
import { createViewStore } from "../src/net/viewStore";
import type { AnyView, HostView, StateMsg } from "../src/protocol";
import { ERROR_CODES, HOST_WARNINGS, START_BLOCKERS } from "../src/protocol";

describe("formats (French typography)", () => {
  it("rounds times to the tenth with a comma", () => {
    expect(formatSeconds(4237)).toBe("4,2 s");
    expect(formatSeconds(4250)).toBe("4,3 s");
    expect(formatSeconds(0)).toBe("0,0 s");
  });

  it("formats deltas, ranks, counts and late badges", () => {
    expect(formatDelta(2)).toBe("+2");
    expect(formatDelta(-1)).toBe("−1");
    expect(formatDelta(0)).toBe("0");
    expect(formatRank(1, false)).toBe("1.");
    expect(formatRank(2, true)).toBe("2≈");
    expect(formatRank(null, false)).toBe("—");
    expect(formatCount(5273)).toBe("5 273");
    expect(formatLate(2300)).toBe("⚠ audio +2,3 s");
    expect(formatLate(100)).toBeNull();
    expect(formatLate(null)).toBe("⚠ audio ?");
  });
});

describe("i18n", () => {
  const params = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

  it("has the same parameters in every language", () => {
    for (const key of Object.keys(fr) as (keyof typeof fr)[]) {
      expect(params(en[key]), key).toEqual(params(fr[key]));
    }
  });

  it("covers every error code, start blocker and host warning", () => {
    for (const code of ERROR_CODES) {
      expect(`error.${code}` in fr, code).toBe(true);
    }
    for (const blocker of START_BLOCKERS) {
      expect(`blocker.${blocker}` in fr, blocker).toBe(true);
    }
    for (const warning of HOST_WARNINGS) {
      expect(`warning.${warning}` in fr, warning).toBe(true);
    }
  });

  it("replaces placeholders", () => {
    expect(format("{a}/{b} ont validé", { a: 5, b: 8 })).toBe("5/8 ont validé");
  });
});

describe("network helpers", () => {
  it("backs off up to 10 s with jitter", () => {
    expect(nextDelay(0, () => 0.5)).toBe(500);
    expect(nextDelay(10, () => 0.5)).toBe(10_000);
    expect(nextDelay(10, () => 1)).toBeCloseTo(12_000);
  });

  it("maps close codes", () => {
    expect(closeAction(4001, null)).toBe("superseded");
    expect(closeAction(4003, null)).toBe("kicked");
    expect(closeAction(4004, null)).toBe("session_ended");
    expect(closeAction(1008, "protocol_mismatch")).toBe("reload");
    expect(closeAction(1008, null)).toBe("check");
    expect(closeAction(1006, null)).toBe("reconnect");
  });
});

function fakeView(overrides: Record<string, unknown> = {}): AnyView {
  return {
    kind: "player",
    session: {
      epoch: "e1",
      protocol: 2,
      server_version: "0",
      recovered: false,
      persistence_status: "disabled",
    },
    me: { player_id: "p_0001", nickname: "A", role: "player", host_mode: null, participant: true },
    phase: "IN_GAME",
    players: [],
    standings: [],
    game: null,
    audio: { current: null, next: null },
    play: { play_id: "pl_000002", asset_id: "a_x", start_at: 1, clip_offset: 0 },
    final_results: null,
    rules: null,
    paused: null,
    team_standings: [],
    round: {
      state: "OPEN",
      round_id: "r_000001",
      number: 1,
      official_start_at: 1,
      deadline: 99,
      my_answer: { status: "NONE", text: null, draft_text: null },
      progress: null,
    },
    ...overrides,
  } as AnyView;
}

describe("view store", () => {
  it("accepts newer versions and the first STATE of a connection", () => {
    const store = createViewStore();
    const msg = (v: number): StateMsg => ({ t: "STATE", v, view: fakeView() });
    expect(store.apply(msg(3), true)).toBe(true);
    expect(store.apply(msg(2), false)).toBe(false);
    expect(store.apply(msg(4), false)).toBe(true);
    expect(store.apply(msg(1), true)).toBe(true); // v restarts on a new connection
  });
});

describe("host commands read their keys from the displayed view", () => {
  const host = {
    ...fakeView(),
    kind: "host_player",
    host: { undo_round_id: "r_000000", last_play_id: "pl_000002" },
  } as unknown as HostView;

  it("uses round ids, play ids and deadlines from the view", () => {
    expect(cmd.roundCmd(host, "close")).toEqual({
      t: "HOST",
      cmd: "close",
      round_id: "r_000001",
      args: {},
    });
    expect(cmd.replay(host).args).toEqual({ play_id: "pl_000002" });
    expect(cmd.stop(host).args).toEqual({ play_id: "pl_000002" });
    expect(cmd.addTime(host).args).toEqual({ expected_deadline: 99 });
  });

  it("undoes the most recent REVEALED round, not the displayed one", () => {
    expect(cmd.undoPublish(host)).toMatchObject({ round_id: "r_000000" });
  });

  it("builds final review and adjustment commands", () => {
    expect(cmd.finalSet("p_1", 2)).toEqual({
      t: "HOST",
      cmd: "final_set",
      expected_phase: "FINAL_SCORE_REVIEW",
      args: { player_id: "p_1", delta: 2, note: null },
    });
    const op = cmd.newOpId();
    expect(op).toMatch(/^[0-9a-f]{32}$/);
    expect(cmd.adjust("p_1", -1, op).args).toEqual({ player_id: "p_1", delta: -1, op_id: op });
  });
});
