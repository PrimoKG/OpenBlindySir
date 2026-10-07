import { describe, expect, it } from "vitest";
import { selectedCapacity, settingsKey } from "../src/host/SetupPanel";
import { recapCsv } from "../src/player/Recap";
import type { GameRecord, GameSettings, LibraryResponse } from "../src/protocol";

describe("library preflight", () => {
  const library: LibraryResponse = {
    issues: [],
    bridges: [
      {
        bridge_id: "example",
        name: "Example",
        online: true,
        scanned_folders: [""],
        source_error: null,
        track_count: 10,
        root: {
          name: "Example",
          prefix: "",
          track_count: 10,
          fresh_count: 5,
          available_count: 8,
          children: [
            {
              name: "Subset",
              prefix: "Subset",
              track_count: 4,
              fresh_count: 2,
              available_count: 3,
              children: [],
            },
          ],
        },
      },
    ],
  };
  it("counts parent and child selections once and distinguishes heard/unreadable tracks", () => {
    const selected = new Set(["example|", "example|Subset"]);
    expect(selectedCapacity(library, selected, false)).toBe(5);
    expect(selectedCapacity(library, selected, true)).toBe(8);
    expect(selectedCapacity(library, new Set(["example|Subset"]), false)).toBe(2);
    expect(
      selectedCapacity(
        { ...library, bridges: library.bridges.map((b) => ({ ...b, online: false })) },
        selected,
        true,
      ),
    ).toBe(0);
  });
  it("accepts a server echo that reorders selected folders", () => {
    const settings: GameSettings = {
      rounds: 2,
      clip_seconds: 25,
      answer_grace_s: 15,
      sources: [
        { bridge_id: "example", folder_prefix: "B" },
        { bridge_id: "example", folder_prefix: "A" },
      ],
      auto_start: true,
      auto_advance: true,
      intermission_s: 2,
      custom_points: 1,
      prefetch_depth: 1,
      allow_repeats: false,
      scoring_mode: "manual",
      acceptance_threshold: 90,
      answer_fields: ["title", "artist"],
      album_points: 1,
      year_points: 1,
      featuring_points: 1,
      answer_mode: "both",
      title_points: 1,
      artist_points: 1,
      instructions: "",
      captured_policy: "manual",
      normalize_audio: true,
      avoid_silence: true,
      balance_folders: false,
    };
    expect(settingsKey(settings)).toBe(
      settingsKey({ ...settings, sources: [...settings.sources].reverse() }),
    );
  });
});

describe("recap export", () => {
  it("retains manual corrections and escapes spreadsheet formulas and quoted answers", () => {
    const record: GameRecord = {
      version: 2,
      started_at: null,
      settings: null,
      sources: [],
      game_id: "g_example",
      finished_at: 42,
      teams: [],
      players: [
        {
          id: "p_example",
          nickname: "=Example",
          online: false,
          is_host: false,
          is_me: false,
          spectator: false,
          team: "Example team",
        },
      ],
      results: {
        podium_started_at: null,
        finished_at: 42,
        standings: [],
        podium: [],
        rounds_played: 1,
        final_adjustments: [{ player_id: "p_example", delta: -1, note: null }],
        recap: [
          {
            player_id: "p_example",
            score_before: 2,
            draft_note: null,
            draft_delta: 0,
            score_after: 1,
            adjustments: [{ kind: "adjustment", delta: 1, round_number: 1, note: "+Example note" }],
            history: [
              {
                round_id: "r_example",
                number: 1,
                text: 'Example; "answer"',
                status: "LOCKED",
                elapsed_ms: 1234,
                order: 1,
                near_tie: false,
                points: 1,
                judgement: "criteria",
                title_correct: true,
                artist_correct: false,
                album_correct: null,
                year_correct: null,
                featuring_correct: null,
                custom_correct: null,
                received_at_wall_ms: 42,
                included: true,
                track: {
                  title: "Example title",
                  artist: "Example artist",
                  featuring: "Guest",
                  album: "Album",
                  year: 2026,
                  cleared_fields: [],
                  aliases: null,
                  display_name: "Example",
                  folder: "Example",
                },
              },
            ],
          },
        ],
      },
    };
    const csv = recapCsv(record);
    expect(csv.startsWith("\uFEFF")).toBe(true);
    expect(csv).toContain('"\'=Example"');
    expect(csv).toContain('"Example; ""answer"""');
    expect(csv).toContain('"\'+Example note"');
    expect(csv).toContain('"final_adjustment"');
    expect(csv).toContain('"-1"');
    expect(csv).toContain('"criteria";"true";"false";""');
    expect(
      csv
        .trim()
        .split("\r\n")
        .map((line) => [...line.matchAll(/"(?:[^"]|"")*"/g)].length),
    ).toEqual([24, 24, 24, 24]);
    expect(csv.split("\r\n")).toHaveLength(5);
  });
});
