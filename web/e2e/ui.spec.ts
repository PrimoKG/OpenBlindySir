import { selectedCapacity } from "../src/host/SetupPanel";
import { emptyTheme } from "../src/host/ThemeSelector";
// Deterministic UI states supplement the real-game tests; no server/game rule is mocked
// into production. These fixtures contain synthetic names and answers only.

import { Buffer } from "node:buffer";
import {
  chromium,
  expect,
  type Page,
  type Route,
  test,
  type WebSocketRoute,
} from "@playwright/test";
import { en } from "../src/i18n/en";
import { fr } from "../src/i18n/fr";
import type {
  AnyView,
  GameRecord,
  HostView,
  LibraryResponse,
  LibraryTrack,
  PlayerView,
  RevealTrack,
  ReviewRow,
  StandingRow,
} from "../src/protocol";

const players = [
  {
    id: "p_example1",
    nickname: "UnPseudoDe24CaracteresABC",
    online: true,
    is_host: true,
    is_me: true,
    spectator: false,
    team: null,
  },
  {
    id: "p_example2",
    nickname: "Exemple Alice",
    online: true,
    is_host: false,
    is_me: false,
    spectator: false,
    team: null,
  },
  {
    id: "p_example3",
    nickname: "Exemple Bob",
    online: false,
    is_host: false,
    is_me: false,
    spectator: false,
    team: null,
  },
] as const;
const standings: StandingRow[] = players.map((p, i) => ({
  player_id: p.id,
  rank: i + 1,
  score: 3 - i,
}));
const myAnswer = { status: "DRAFT" as const, text: null, draft_text: "Exemple de brouillon" };
const roundId = "r_example1";

for (const language of ["fr", "en"] as const) {
  test(`library remains usable after saving metadata (${language})`, async ({ page }) => {
    const { library, track } = manualFixture();
    await harness(page, hostView(), library);
    const copy = language === "fr" ? fr : en;
    if (language === "en") await page.getByRole("button", { name: "English", exact: true }).click();
    await page.route("**/api/host/library/search**", (route) =>
      route.fulfill({ json: { total: 1, tracks: [track], tags: [], linked_to: [] } }),
    );
    await page.route("**/api/host/metadata", (route) => route.fulfill({ json: { ok: true } }));
    await page.getByRole("button", { name: copy["library.manage"], exact: true }).click();
    const dialog = page.getByRole("dialog", { name: copy["library.manage"], exact: true });
    await dialog.getByRole("button", { name: copy["ux.editTrack"], exact: true }).click();
    const editor = dialog.locator(".metadata-editor");
    await editor
      .getByRole("textbox", { name: copy["review.title"], exact: true })
      .fill("Updated example");
    await editor.getByRole("button", { name: copy["hostui.save"], exact: true }).click();
    await expect(editor).toHaveCount(0);
    await expect(
      dialog.getByRole("button", { name: copy["library.disable"], exact: true }),
    ).toBeEnabled();
    await dialog.locator(".library-extra-filters > summary").click();
    await dialog.getByRole("button", { name: "Rap", exact: true }).click();
    await expect(
      dialog.getByRole("combobox", { name: copy["theme.genres"], exact: true }),
    ).toHaveValue("Rap");
    await dialog.getByRole("button", { name: copy["flow.close"], exact: true }).click();
    await expect(dialog).toHaveCount(0);
  });

  test(`library toggle and bulk preserve concurrent changes (${language})`, async ({ page }) => {
    const { view, library, track } = manualFixture();
    const copy = language === "fr" ? fr : en;
    await harness(page, view, library);
    if (language === "en") await page.getByRole("button", { name: "English", exact: true }).click();
    let revision = 7;
    const tracks = [track, { ...track, track_id: "b".repeat(24), title: "Second example" }];
    await page.route("**/api/host/library/search**", (route) =>
      route.fulfill({
        json: {
          total: 2,
          tracks: tracks.map((row) => ({ ...row, metadata_revision: revision })),
          tags: [],
          linked_to: [],
        },
      }),
    );
    const requests: { expected_revision?: number }[] = [];
    let saved = 0;
    await page.route("**/api/host/metadata", (route) => {
      const body = route.request().postDataJSON();
      requests.push(body);
      if (body.expected_revision !== undefined && body.expected_revision !== revision)
        return route.fulfill({ status: 409, json: { error: "stale_command" } });
      saved++;
      revision++;
      // A second host edits between the two bulk requests.
      if (saved === 1) revision++;
      return route.fulfill({ json: { ok: true } });
    });
    await page.getByRole("button", { name: copy["library.manage"], exact: true }).click();
    const dialog = page.getByRole("dialog", { name: copy["library.manage"], exact: true });
    await expect(dialog.locator(".library-tracks > li")).toHaveCount(2);
    await expect(
      dialog
        .locator(".library-tracks > li")
        .first()
        .getByRole("button", { name: copy["library.disable"], exact: true }),
    ).toBeEnabled();
    revision = 9;
    await dialog
      .locator(".library-tracks > li")
      .first()
      .getByRole("button", { name: copy["library.disable"], exact: true })
      .click();
    await expect(dialog.getByRole("alert")).toContainText(copy["library.editConflict"]);
    expect(saved).toBe(0);
    expect(requests[0]?.expected_revision).toBe(7);
    await dialog.getByRole("button", { name: copy["library.refresh"], exact: true }).last().click();
    await expect(dialog.getByRole("alert")).toHaveCount(0);
    for (const card of await dialog.locator(".library-tracks > li").all())
      await card.getByRole("checkbox").check();
    const bulk = dialog.locator(".library-bulk");
    await bulk.locator("summary").click();
    await bulk.getByRole("textbox").first().fill("Example tag");
    await bulk.getByRole("button", { name: copy["library.bulk"], exact: true }).click();
    await expect.poll(() => requests.length).toBe(3);
    expect(requests.map((row) => row.expected_revision)).toEqual([7, 9, 10]);
    expect(saved).toBe(1);
    await expect(dialog.getByRole("status")).toContainText([
      copy["library.bulkSaved"].replace("{count}", "1").replace("{total}", "2"),
    ]);
    await expect(dialog.getByRole("status")).toContainText([copy["library.editConflict"]]);
  });
}

function silentWav(seconds: number): Buffer {
  const clip = Buffer.alloc(44 + 16000 * seconds);
  clip.write("RIFF", 0);
  clip.writeUInt32LE(clip.length - 8, 4);
  clip.write("WAVEfmt ", 8);
  clip.writeUInt32LE(16, 16);
  clip.writeUInt16LE(1, 20);
  clip.writeUInt16LE(1, 22);
  clip.writeUInt32LE(8000, 24);
  clip.writeUInt32LE(16000, 28);
  clip.writeUInt16LE(2, 32);
  clip.writeUInt16LE(16, 34);
  clip.write("data", 36);
  clip.writeUInt32LE(16000 * seconds, 40);
  return clip;
}

function playerView(): PlayerView {
  return {
    kind: "player",
    session: {
      epoch: "example-epoch",
      protocol: 14,
      server_version: "0.1.0",
      recovered: false,
      persistence_status: "disabled",
    },
    me: {
      player_id: players[0].id,
      nickname: players[0].nickname,
      role: "player",
      host_mode: null,
      participant: true,
    },
    phase: "LOBBY",
    players,
    standings: [],
    game: null,
    audio: { current: null, next: null },
    play: null,
    final_results: null,
    finale: null,
    round: null,
    rules: null,
    paused: null,
    team_standings: [],
  };
}

function manualFixture() {
  const base = hostView(true);
  if (base.kind !== "host_mc") throw new Error("MC fixture");
  const bridgeId = "12345678-1234-1234-1234-123456789abc";
  const library: LibraryResponse = {
    issues: [],
    bridges: [
      {
        bridge_id: bridgeId,
        name: "Synth Bridge",
        online: true,
        track_count: 4,
        scanned_folders: [""],
        source_error: null,
        root: {
          name: "Synth",
          prefix: "",
          track_count: 4,
          fresh_count: 4,
          available_count: 4,
          children: [],
        },
      },
    ],
  };
  const track: LibraryTrack = {
    genres: [],
    languages: [],
    metadata_revision: 0,
    missing_references: [],
    enabled: true,
    tags: [],
    linked_to: [],
    cleared_fields: [],
    aliases: null,
    consumption: "available",
    bridge_id: bridgeId,
    bridge_name: "Synth Bridge",
    track_id: "a".repeat(24),
    filename: "exemple-très-long-pour-un-petit-téléphone.mp4",
    folder: "Synth",
    ext: ".mp4",
    available: true,
    title: "Titre synthétique privé",
    artist: "Artiste test",
    featuring: null,
    album: null,
    year: null,
    duration_ms: 90000,
    played: false,
    reserved: false,
    in_pool: true,
  };
  const view = {
    ...base,
    host: {
      ...base.host,
      commands: [...base.host.commands, "select_track", "start_game"],
      auto_missing_references: 0,
      start_blockers: [],
      settings: {
        ...base.host.settings,
        rounds: 2,
        sources: [{ bridge_id: bridgeId, folder_prefix: "" }],
      },
      pool: {
        size: 4,
        remaining: 4,
        fresh: 4,
        played: 0,
        unavailable: 0,
        reserved: 0,
        exhausted: false,
      },
    },
    mc: {
      ...base.mc,
      selection_revision: 0,
      manual_choices: [1, 2].map((number) => ({
        round_number: number,
        bridge_id: null,
        track_id: null,
        filename: null,
        bridge_name: null,
        folder: null,
        title: null,
        artist: null,
        locked: false,
        manual: false,
        error: null,
      })),
    },
  } as typeof base;
  return { view, library, track };
}

test("MC confirms a numbered choice before launch, including mobile keyboard access", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 850 });
  const { view, library, track } = manualFixture();
  const h = await harness(page, view, library);
  await page.route("**/api/host/library/search**", (route) =>
    route.fulfill({ json: { total: 1, tracks: [track] } }),
  );
  await page
    .getByRole("button", { name: "Sources et recherche de bibliothèque", exact: true })
    .click();
  await page.getByRole("combobox", { name: "Manche à préparer", exact: true }).selectOption("2");
  const choose = page.getByRole("button", { name: "Choisir pour la manche 2", exact: true });
  await choose.focus();
  await page.keyboard.press("Enter");
  await expect
    .poll(() =>
      h.sent.some((raw) => {
        const msg = JSON.parse(raw);
        return (
          msg.cmd === "select_track" &&
          msg.args.round_number === 2 &&
          msg.args.expected_revision === 0 &&
          msg.args.track_id === track.track_id
        );
      }),
    )
    .toBe(true);
  await expect(page.locator(".host-toolbar")).toHaveAttribute("disabled", "");
  h.show(view); // an unrelated state echo is not a confirmation
  await expect(choose).toBeDisabled();
  const confirmed = {
    ...view,
    mc: {
      ...view.mc,
      selection_revision: 1,
      manual_choices: view.mc.manual_choices.map((c) =>
        c.round_number === 2
          ? {
              ...c,
              bridge_id: track.bridge_id,
              track_id: track.track_id,
              title: track.title,
              filename: track.filename,
              manual: true,
            }
          : c,
      ),
    },
  };
  h.show(confirmed);
  await expect(page.getByText("Choix enregistré par le serveur.", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Choix confirmé : Titre synthétique privé", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".host-toolbar")).not.toHaveAttribute("disabled", "");
  await layout(page);
  h.show({
    ...confirmed,
    mc: {
      ...confirmed.mc,
      manual_choices: confirmed.mc.manual_choices.map((c) => ({ ...c, locked: true })),
    },
  });
  await expect(choose).toBeDisabled();
});

test("MC acknowledgement deadline is not extended by repeated states", async ({ page }) => {
  const { view, library, track } = manualFixture();
  const h = await harness(page, view, library);
  await page.route("**/api/host/library/search**", (route) =>
    route.fulfill({ json: { total: 1, tracks: [track] } }),
  );
  await page
    .getByRole("button", { name: "Sources et recherche de bibliothèque", exact: true })
    .click();
  const choose = page.getByRole("button", { name: "Choisir pour la manche 1", exact: true });
  await expect(choose).toBeEnabled();
  await page.clock.install();
  await choose.click();
  await page.clock.fastForward(6000);
  h.show(view);
  await page.clock.fastForward(4500);
  await expect(
    page.getByText("Choix non confirmé. Actualise la bibliothèque puis réessaie.", { exact: true }),
  ).toBeVisible();
  await expect(choose).toBeEnabled();
  await page.keyboard.press("Escape");
  await page.locator("header").getByRole("button", { name: "English", exact: true }).click();
  await page.getByRole("button", { name: "Library sources and search", exact: true }).click();
  await expect(page.getByText("Choose tracks (MC)", { exact: true })).toBeVisible();
});

function hostView(mc = false): HostView {
  return {
    ...playerView(),
    kind: mc ? "host_mc" : "host_player",
    me: {
      player_id: players[0].id,
      nickname: players[0].nickname,
      role: "host",
      host_mode: mc ? "mc" : "player",
      participant: !mc,
    },
    host: {
      commands: ["set_mode", "configure", "kick", "end_session"],
      settings: {
        selection_filter: emptyTheme(),
        rounds: 20,
        clip_seconds: 25,
        answer_grace_s: 15,
        sources: [],
        auto_start: true,
        auto_advance: true,
        intermission_s: 2,
        custom_points: 1,
        prefetch_depth: 1,
        allow_repeats: false,
        scoring_mode: "manual",
        ready_only: false,
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
      },
      limits: {
        max_players: 15,
        clip_min_s: 5,
        clip_max_s: 60,
        answer_max_chars: 200,
        near_tie_ms: 300,
        ready_timeout_s: 10,
        clip_format: "opus",
      },
      auto_missing_references: 0,
      start_blockers: ["no_sources"],
      bridge: { state: "ONLINE", name: "Exemple", track_count: 12, jobs_in_flight: 0 },
      pool: null,
      players_ops: [],
      ready_check: null,
      undo_round_id: null,
      last_play_id: null,
      final_review: null,
      review_rounds: [],
      joins_locked: false,
      warnings: [],
      history: [],
      history_count: 0,
      bridges: [],
    },
    ...(mc
      ? {
          mc: {
            current_track: {
              bridge_name: "Exemple",
              folder: "Dossier exemple",
              filename: "exemple",
              cleared_fields: [],
              aliases: null,
              display_name: "Morceau visible au MC",
              asset_state: "STORED",
            },
            upcoming: [],
          },
        }
      : {}),
  } as HostView;
}

function globalReview(
  base: HostView,
  answers: readonly ReviewRow[],
  track: RevealTrack | null = null,
): HostView {
  return {
    ...base,
    phase: "FINAL_SCORE_REVIEW",
    round: null,
    finale: {
      round: {
        awards_pending: false,
        round_id: roundId,
        number: 1,
        track,
        included: true,
        answers: answers.map((a) => ({
          player_id: a.player_id,
          text: a.text,
          points: a.points_draft,
          reviewed: a.reviewed,
          revision: a.score_revision,
          title_correct: a.title_correct,
          artist_correct: a.artist_correct,
          album_correct: null,
          year_correct: null,
          featuring_correct: null,
          custom_correct: a.custom_correct,
        })),
      },
      revealed_round_ids: [roundId],
      rounds_total: 1,
      reviewed: 0,
      expected: answers.length,
      standings: players.map((p) => ({ player_id: p.id, score: 0, rank: 1 })),
      teams: [],
    },
    host: {
      ...base.host,
      commands: [
        "score_draft",
        "track_metadata",
        "final_set",
        "final_reset",
        "final_validate",
        "end_game",
        "join_lock",
      ],
      auto_missing_references: 0,
      start_blockers: [],
      review_rounds: [
        {
          scoring_reference: track
            ? {
                title: track.title,
                artist: track.artist,
                album: track.album,
                featuring: track.featuring,
                year: track.year,
              }
            : null,
          reference_changed: false,
          neutralized_fields: [],
          played: true,
          round_id: roundId,
          number: 1,
          state: "REVIEW",
          included: true,
          close_reason: "host",
          recovery_interrupted: false,
          excerpt_duration_ms: 25000,
          track_duration_ms: 120000,
          metadata_revision: 0,
          full_review_allowed: true,
          bridge_online: true,
          track,
          answers,
        },
      ],
      final_review: players.map((p) => ({
        player_id: p.id,
        score_before: 0,
        draft_note: null,
        draft_delta: 0,
        score_after: 0,
        history: [],
        adjustments: [],
      })),
    },
  };
}

async function harness(
  page: Page,
  initial: AnyView,
  library: LibraryResponse = { bridges: [], issues: [] },
) {
  let view = initial;
  let version = 0;
  let socket: WebSocketRoute | undefined;
  const sent: string[] = [];
  await page.route("**/api/session", (route) => route.fulfill({ json: { role: initial.me.role } }));
  await page.route("**/api/host/library/search**", (route) =>
    route.fulfill({ json: { total: 0, tracks: [] } }),
  );
  await page.route("**/api/host/library", (route) => route.fulfill({ json: library }));
  await page.route("**/api/host/library/selection", (route) => {
    const body = route.request().postDataJSON();
    const selected = new Set<string>(
      (body.sources ?? []).map(
        (source: { bridge_id: string; folder_prefix: string }) =>
          `${source.bridge_id}|${source.folder_prefix}`,
      ),
    );
    const available = selectedCapacity(library, selected, true);
    const fresh = selectedCapacity(library, selected, false);
    return route.fulfill({
      json: {
        matching: available,
        available,
        fresh,
        unclassified: 0,
        genres: [],
        languages: [],
        tags: [],
        linked_to: [],
        years: [],
        examples: [],
      },
    });
  });
  await page.route("**/api/host/session/access", (route) =>
    route.fulfill({ json: { code: "EXAMPLE2", invitation: "synthetic-invitation", requests: [] } }),
  );
  await page.route("**/api/session/access-code", (route) =>
    route.fulfill({ json: { code: "EXAMPLE2" } }),
  );
  await page.route("**/api/host/diagnostics", (route) =>
    route.fulfill({ json: { example: true } }),
  );
  await page.routeWebSocket("**/api/ws", (ws) => {
    socket = ws;
    ws.onMessage((raw) => {
      const message = String(raw);
      sent.push(message);
      if (JSON.parse(message).t === "HELLO")
        ws.send(JSON.stringify({ t: "STATE", v: ++version, view }));
    });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Tout le monde s’installe." })).toBeVisible();
  return {
    sent,
    error(code: string) {
      socket?.send(JSON.stringify({ t: "ERROR", code }));
    },
    show(next: AnyView) {
      view = next;
      if (!socket) throw new Error("Example socket not connected");
      socket.send(JSON.stringify({ t: "STATE", v: ++version, view }));
    },
    disconnect(code: number) {
      socket?.close({ code });
    },
  };
}

async function settings(page: Page, tab: string) {
  const dialog = page
    .locator(".workspace-modal")
    .filter({ has: page.getByRole("tab", { name: tab, exact: true }) });
  if (!(await dialog.isVisible()))
    await page
      .getByRole("button", { name: "Préparer la partie", exact: true })
      .or(page.getByRole("button", { name: "Paramètres", exact: true }))
      .click();
  await dialog.getByRole("tab", { name: tab, exact: true }).click();
}

async function layout(page: Page) {
  const overflow = await page.evaluate(() => ({
    width: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    elements: [...document.querySelectorAll("body *")]
      .filter(
        (element) =>
          element.getBoundingClientRect().right > window.innerWidth + 1 ||
          element.scrollWidth > element.clientWidth + 1,
      )
      .slice(-24)
      .map((element) => ({
        tag: element.tagName,
        class: element.className,
        right: element.getBoundingClientRect().right,
        width: element.clientWidth,
        scrollWidth: element.scrollWidth,
        text: element.textContent?.slice(0, 160),
      })),
  }));
  expect(overflow.scrollWidth, JSON.stringify(overflow)).toBeLessThanOrEqual(overflow.width);
  for (const button of await page.getByRole("button").all()) {
    if (!(await button.isVisible())) continue;
    const box = await button.boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(44);
    expect(box?.width).toBeGreaterThanOrEqual(44);
  }
}

test("V0.5 history is fetched on demand, exported and deleted with keyboard confirmation", async ({
  page,
}) => {
  const view = hostView();
  const historical: GameRecord = {
    version: 3,
    game_id: "g_history1",
    finished_at: 1780000000000,
    started_at: 1779990000000,
    settings: view.host.settings,
    sources: [{ bridge_id: "12345678-1234-1234-1234-123456789abc", name: "Ancienne source" }],
    players: [...players],
    teams: [],
    results: {
      unreviewed_answers: 0,
      podium_started_at: null,
      standings,
      podium: standings,
      rounds_played: 1,
      final_adjustments: [],
      recap: [],
      finished_at: 1780000000000,
    },
  };
  let rows = [
    {
      game_id: historical.game_id,
      finished_at: historical.finished_at,
      rounds_played: 1,
      participants: 3,
    },
  ];
  let requests = 0;
  let deleted = 0;
  await page.route("**/api/host/history", (route) => {
    requests++;
    if (route.request().method() === "DELETE") {
      expect(route.request().postDataJSON()).toEqual({ confirm: true });
      rows = [];
      deleted++;
      return route.fulfill({ json: { ok: true } });
    }
    return route.fulfill({
      json: {
        version: 3,
        items: rows,
        retained_bytes: 1000,
        max_games: 50,
        max_bytes: 16777216,
        retention_days: 90,
        durable: true,
      },
    });
  });
  await page.route("**/api/host/history/g_history1", (route) => {
    if (route.request().method() === "DELETE") {
      expect(route.request().postDataJSON()).toEqual({ confirm: true });
      deleted++;
      rows = [];
      return route.fulfill({ json: { ok: true } });
    }
    return route.fulfill({ json: historical });
  });
  await harness(page, { ...view, host: { ...view.host, history_count: 1 } });
  expect(requests).toBe(0);
  await settings(page, "Avancé");
  const summary = page.locator(".party-history > summary");
  await summary.focus();
  await summary.press("Enter");
  await expect(page.locator(".history-picker")).toContainText("3 participants");
  await page.locator(".history-picker button").first().click();
  await expect(
    page.getByRole("region", { name: "Récapitulatif de la soirée passée" }),
  ).toContainText(players[0].nickname);
  await expect(
    page.getByRole("button", { name: "Exporter les résultats JSON", exact: true }),
  ).toBeVisible();
  const remove = page.getByRole("button", { name: /Supprimer la partie du/ });
  await remove.focus();
  await remove.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Supprimer cette partie", exact: true });
  await expect(dialog.getByRole("button", { name: "Annuler", exact: true })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(remove).toBeFocused();
  expect(deleted).toBe(0);
  await remove.press("Enter");
  await dialog.getByRole("button", { name: "Confirmer", exact: true }).press("Enter");
  await expect(page.getByText("Aucune partie terminée conservée.", { exact: true })).toBeVisible();
  await expect(summary).toBeFocused();
  expect(deleted).toBe(1);
  await layout(page);
});

test("V0.5 history purge errors are announced and retry stays available", async ({ page }) => {
  const view = hostView();
  await page.route("**/api/host/history", (route) =>
    route.request().method() === "DELETE"
      ? route.fulfill({ status: 503, json: { error: "invalid_state" } })
      : route.fulfill({
          json: {
            version: 3,
            items: [
              {
                game_id: "g_history1",
                finished_at: 1780000000000,
                rounds_played: 2,
                participants: 3,
              },
            ],
            retained_bytes: 1000,
            max_games: 50,
            max_bytes: 16777216,
            retention_days: 90,
            durable: false,
          },
        }),
  );
  await harness(page, { ...view, host: { ...view.host, history_count: 1 } });
  await settings(page, "Avancé");
  await page.locator(".party-history > summary").click();
  await expect(page.locator(".party-history").getByRole("status")).toContainText(
    "Sauvegarde indisponible",
  );
  await page.getByRole("button", { name: "Supprimer tout l’historique", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirmer", exact: true }).click();
  await expect(page.locator(".party-history").getByRole("alert")).toBeVisible();
  await expect(
    page.locator(".party-history").getByRole("button", { name: "Réessayer" }),
  ).toBeEnabled();
});

test("V0.5 separate Bridges expose readable states and revoke only the chosen identity", async ({
  page,
}) => {
  const view = hostView();
  const first = "12345678-1234-1234-1234-123456789abc";
  const second = "12345678-1234-1234-1234-123456789abd";
  let revoked = "";
  await page.route("**/api/host/bridges/*/revoke", (route) => {
    revoked = route.request().url();
    expect(route.request().postDataJSON()).toEqual({ confirm: true });
    return route.fulfill({ json: { ok: true } });
  });
  await harness(page, {
    ...view,
    host: {
      ...view.host,
      bridges: [
        {
          bridge_id: first,
          name: "Appareil salon",
          version: "0.5.0.dev0",
          protocol: 14,
          state: "ONLINE",
          track_count: 8,
          jobs_in_flight: 0,
          formats: ["aac"],
          allow_full_review: false,
          source_error: null,
        },
        {
          bridge_id: second,
          name: "Appareil absent",
          version: "0.5.0.dev0",
          protocol: 14,
          state: "OFFLINE",
          track_count: 4,
          jobs_in_flight: 0,
          formats: ["aac"],
          allow_full_review: false,
          source_error: null,
        },
      ],
    },
  });
  await page.setViewportSize({ width: 320, height: 900 });
  await settings(page, "Avancé");
  await page.locator(".bridge-connections > summary").click();
  await expect(page.locator(".bridge-card").last()).toContainText("Hors ligne");
  await expect(page.locator(".bridge-card").last()).toContainText("45");
  await settings(page, "Avancé");
  const revoke = page.getByRole("button", {
    name: "Révoquer le secret du Bridge Appareil absent",
    exact: true,
  });
  await revoke.focus();
  await revoke.press("Enter");
  await page
    .getByRole("dialog")
    .last()
    .getByRole("button", { name: "Confirmer", exact: true })
    .press("Enter");
  await expect.poll(() => revoked).toContain(second);
  await expect(page.locator(".bridge-connections").getByRole("status")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Révoquer le secret du Bridge Appareil salon", exact: true }),
  ).toBeEnabled();
  await layout(page);
});

test("V0.5 skip links and 200 percent text sizing retain keyboard and phone layout", async ({
  page,
}) => {
  await harness(page, hostView());
  const skip = page.getByRole("link", { name: "Aller à la partie", exact: true });
  await skip.focus();
  await skip.press("Enter");
  await expect(page.locator("#stage-content")).toBeFocused();
  await page.getByRole("link", { name: "Aller aux commandes hôte", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#host-controls")).toBeFocused();
  await page.setViewportSize({ width: 640, height: 1000 });
  await page.evaluate(() => {
    const sheet = document.styleSheets[0];
    sheet?.insertRule(":root { font-size: 34px; }", sheet.cssRules.length);
  });
  await layout(page);
});

test("V0.5 incompatible client stops reload loops and shows the required range", async ({
  page,
}) => {
  const h = await harness(page, playerView());
  await page.evaluate(() => sessionStorage.setItem("openblindysir:protocolReload", "1"));
  await page.route("**/api/compatibility", (route) =>
    route.fulfill({
      json: {
        server_version: "0.5.0.dev0",
        protocol: 14,
        protocol_min: 8,
        protocol_max: 8,
        snapshot_format: 4,
        history_format: 2,
      },
    }),
  );
  h.error("protocol_mismatch");
  h.disconnect(1008);
  await expect(page.getByRole("heading", { name: "Version incompatible" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("8 à 8");
  await expect(
    page.getByRole("button", { name: "Recharger après mise à jour", exact: true }),
  ).toBeEnabled();
});

test("local score editing waits for acknowledgement and confirms unchecked answers", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 850 });
  const base = hostView();
  const ui = await harness(page, base);
  const review = globalReview(
    base,
    players.map((p) => ({
      player_id: p.id,
      text: "Exemple",
      status: "LOCKED",
      elapsed_ms: 1000,
      order: 1,
      near_tie: false,
      late_start_ms: 0,
      judgement: "manual",
      title_correct: null,
      artist_correct: null,
      album_correct: null,
      year_correct: null,
      featuring_correct: null,
      custom_correct: null,
      auto_evidence: [],
      auto_overridden: false,
      score_revision: 0,
      points_draft: 0,
      reviewed: false,
      score_before: 4,
      received_at_wall_ms: null,
    })),
    {
      title: "Titre privé exemple",
      artist: "Artiste exemple",
      cleared_fields: [],
      aliases: null,
      display_name: "Exemple",
      folder: "Exemple",
      featuring: null,
      album: null,
      year: null,
    },
  );
  ui.show(review);
  await expect(
    page
      .locator(".review-heading")
      .getByRole("heading", { name: "Titre privé exemple", exact: true }),
  ).toBeVisible();
  const input = page.getByLabel(`Points pour ${players[0].nickname}`, { exact: true });
  await page.locator(".manual-score > summary").first().click();
  await input.fill("-");
  ui.show(review); // unrelated STATE must preserve incomplete local typing
  await expect(input).toHaveValue("-");
  expect(ui.sent.some((raw) => JSON.parse(raw).cmd === "score_draft")).toBe(false);
  await expect(page.getByRole("button", { name: "Lancer le podium", exact: true })).toBeDisabled();
  await input.fill("12");
  await input.press("Enter");
  await expect(input).toBeDisabled();
  await expect.poll(() => ui.sent.some((raw) => JSON.parse(raw).args?.points === 12)).toBe(true);
  ui.show({
    ...review,
    host: {
      ...review.host,
      review_rounds: review.host.review_rounds.map((r) => ({
        ...r,
        answers: r.answers.map((row, i) =>
          i === 0
            ? {
                ...row,
                judgement: "manual",
                title_correct: null,
                artist_correct: null,
                album_correct: null,
                year_correct: null,
                featuring_correct: null,
                custom_correct: null,
                auto_evidence: [],
                auto_overridden: false,
                score_revision: 1,
                points_draft: 12,
                reviewed: true,
              }
            : row,
        ),
      })),
    },
  });
  await expect(input).toBeEnabled();
  await expect(page.locator(".review")).toContainText("Total provisoire 4 · +12 cette manche → 16");
  await page.getByRole("button", { name: "Lancer le podium", exact: true }).click();
  const dialog = page.getByRole("dialog").last();
  await expect(dialog).toContainText("2 réponses restent à vérifier");
  await expect(
    dialog.getByRole("button", { name: fr["finale.reviewRemaining"], exact: true }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: fr["finale.publishCurrent"], exact: true }).click();
  await expect
    .poll(() =>
      ui.sent.some(
        (raw) =>
          JSON.parse(raw).cmd === "final_validate" &&
          JSON.parse(raw).args.confirm_unreviewed === true,
      ),
    )
    .toBe(true);
  await layout(page);
  await page.screenshot({ path: info.outputPath("review-ack.png"), fullPage: true });
});

test("final correction buttons and reset wait for the server echo before publication", async ({
  page,
}) => {
  const base = hostView();
  const ui = await harness(page, base);
  const review = globalReview(base, []);
  ui.show(review);
  const panel = page.locator(".final-review");
  await panel.locator(".finale-adjustments > summary").click();
  const increase = panel.getByRole("button", {
    name: `Ajouter un point à ${players[0].nickname}`,
  });
  const input = panel.getByLabel(`Correction pour ${players[0].nickname}`, { exact: true });
  const validate = panel.getByRole("button", {
    name: "Lancer le podium",
    exact: true,
  });
  await increase.click();
  await expect(validate).toBeDisabled({ timeout: 2000 });
  await expect(increase).toBeDisabled();
  await expect(input).toBeDisabled();
  ui.show(review); // An unrelated STATE is not the correction acknowledgement.
  await expect(validate).toBeDisabled();
  const corrected: HostView = {
    ...review,
    host: {
      ...review.host,
      final_review:
        review.host.final_review?.map((row, i) =>
          i === 0 ? { ...row, draft_note: null, draft_delta: 1, score_after: 1 } : row,
        ) ?? null,
    },
  };
  ui.show(corrected);
  await expect(validate).toBeEnabled();
  await expect(input).toHaveValue("1");
  await panel.getByRole("button", { name: "Réinitialiser les corrections" }).click();
  await expect(validate).toBeDisabled({ timeout: 2000 });
  ui.show(corrected);
  await expect(validate).toBeDisabled();
  ui.show(review);
  await expect(validate).toBeEnabled();
  await expect(input).toHaveValue("0");
});

test("numeric round scores cannot overwrite a preset awaiting confirmation", async ({ page }) => {
  const base = hostView();
  const ui = await harness(page, base);
  ui.show(
    globalReview(base, [
      {
        player_id: players[0].id,
        text: "Example",
        status: "LOCKED",
        elapsed_ms: 1000,
        order: 1,
        near_tie: false,
        late_start_ms: 0,
        judgement: "manual",
        title_correct: null,
        artist_correct: null,
        album_correct: null,
        year_correct: null,
        featuring_correct: null,
        custom_correct: null,
        auto_evidence: [],
        auto_overridden: false,
        score_revision: 0,
        points_draft: 0,
        reviewed: false,
        score_before: 0,
        received_at_wall_ms: null,
      },
    ]),
  );
  await page
    .locator(".answer-cards")
    .getByRole("button", { name: "Tout bon", exact: true })
    .click();
  await expect(page.getByLabel(`Points pour ${players[0].nickname}`, { exact: true })).toBeDisabled(
    { timeout: 2000 },
  );
});

test("metadata clearing waits for the server revision and restores the fallback", async ({
  page,
}) => {
  const base = hostView();
  const ui = await harness(page, base);
  const review = globalReview(base, [], {
    title: "Correction",
    artist: "Artiste",
    cleared_fields: [],
    aliases: null,
    display_name: "Source",
    folder: "Test",
    featuring: null,
    album: null,
    year: null,
  });
  ui.show(review);
  await page.locator(".track-options > summary").click();
  await page.getByRole("button", { name: "Corriger les informations du morceau" }).click();
  const editor = page.locator(".metadata-editor");
  await editor.getByLabel("Titre", { exact: true }).fill("");
  await editor.getByRole("button", { name: fr["repair.saveRegrade"], exact: true }).click();
  await expect(editor.getByRole("button", { name: "Enregistrement…", exact: true })).toBeDisabled();
  ui.show(review);
  await expect(editor.getByRole("button", { name: "Enregistrement…", exact: true })).toBeDisabled();
  ui.show({
    ...review,
    host: {
      ...review.host,
      review_rounds: review.host.review_rounds.map((r) => ({
        ...r,
        metadata_revision: 1,
        track: r.track && { ...r.track, title: "Titre importé" },
      })),
    },
  });
  await expect(editor).toHaveCount(0); // close only after server acknowledgement
  await page.locator(".track-options > summary").click();
  await page
    .getByRole("button", { name: "Corriger les informations du morceau", exact: true })
    .click();
  await expect(editor.getByLabel("Titre", { exact: true })).toHaveValue("Titre importé");
  await expect(
    editor.getByRole("button", { name: fr["repair.saveRegrade"], exact: true }),
  ).toBeEnabled();
});

test("private replay downloads only on demand and exposes an accessible retry", async ({
  page,
}) => {
  const ui = await harness(page, hostView());
  let requests = 0;
  await page.route("**/api/host/review/**/audio**", (route) => {
    requests++;
    return route.fulfill({ status: 503, json: { error: "review_unavailable" } });
  });
  ui.show(globalReview(hostView(), []));
  await page.locator(".track-options > summary").click();
  const player = page.getByRole("region", { name: "Réécoute privée" });
  await expect(player.getByRole("button", { name: "Écouter", exact: true })).toBeVisible();
  expect(requests).toBe(0);
  await player.getByRole("button", { name: "Écouter", exact: true }).click();
  await expect(player.getByRole("alert")).toBeVisible();
  expect(requests).toBe(1);
  await player.getByRole("button", { name: "Réessayer", exact: true }).click();
  await expect.poll(() => requests).toBe(2);
  expect(ui.sent.some((raw) => ["PLAY", "STOP"].includes(JSON.parse(raw).t))).toBe(false);
});

test("failed full listening seeks retry the requested position", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(HTMLMediaElement.prototype, "duration", { get: () => 30 });
    HTMLMediaElement.prototype.play = function () {
      this.dispatchEvent(new Event("play"));
      return Promise.resolve();
    };
    HTMLMediaElement.prototype.pause = function () {
      this.dispatchEvent(new Event("pause"));
    };
    HTMLMediaElement.prototype.load = () => {};
  });
  const ui = await harness(page, hostView());
  const offsets: number[] = [];
  const clip = Buffer.alloc(44 + 16000); // One second of synthetic mono PCM, no personal media.
  clip.write("RIFF", 0);
  clip.writeUInt32LE(clip.length - 8, 4);
  clip.write("WAVEfmt ", 8);
  clip.writeUInt32LE(16, 16);
  clip.writeUInt16LE(1, 20);
  clip.writeUInt16LE(1, 22);
  clip.writeUInt32LE(8000, 24);
  clip.writeUInt32LE(16000, 28);
  clip.writeUInt16LE(2, 32);
  clip.writeUInt16LE(16, 34);
  clip.write("data", 36);
  clip.writeUInt32LE(16000, 40);
  await page.route("**/api/host/review/**/audio**", (route) => {
    const offset = Number(new URL(route.request().url()).searchParams.get("offset"));
    offsets.push(offset);
    return offsets.length === 2
      ? route.fulfill({ status: 503, json: { error: "review_unavailable" } })
      : route.fulfill({ contentType: "audio/wav", body: clip });
  });
  ui.show(globalReview(hostView(), []));
  await page.locator(".track-options > summary").click();
  const player = page.getByRole("region", { name: "Réécoute privée" });
  await player.getByRole("button", { name: "Écouter le morceau complet" }).click();
  const progress = player.getByRole("slider", { name: "Position de lecture" });
  await expect(progress).toBeEnabled();
  await progress.evaluate((element) => {
    const input = element as HTMLInputElement;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, "75");
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
  });
  await expect.poll(() => offsets).toEqual([0, 75]);
  await expect(player.getByRole("alert")).toBeVisible();
  await player.getByRole("button", { name: "Réessayer", exact: true }).click();
  await expect.poll(() => offsets).toEqual([0, 75, 75]);
});

test("library search sends filters and gives keyboard access to an empty result", async ({
  page,
}) => {
  const queries: string[] = [];
  await page.route("**/api/host/library/search**", (route) => {
    queries.push(route.request().url());
    return route.fulfill({ json: { total: 0, tracks: [] } });
  });
  await harness(page, hostView());
  // Register after the harness's default empty response.
  await page.route("**/api/host/library/search**", (route) => {
    queries.push(route.request().url());
    return route.fulfill({ json: { total: 0, tracks: [] } });
  });
  await page
    .getByRole("button", { name: "Sources et recherche de bibliothèque", exact: true })
    .click();
  await page.getByLabel("Rechercher un morceau", { exact: true }).fill("Été");
  await page.locator(".library-extra-filters > summary").click();
  await page.getByRole("combobox", { name: "Format source", exact: true }).selectOption(".mp4");
  await expect
    .poll(() =>
      queries.some((url) => {
        const params = new URL(url).searchParams;
        return params.get("q") === "Été" && params.get("ext") === ".mp4";
      }),
    )
    .toBe(true);
  await expect(
    page.getByText("Aucun morceau ne correspond aux filtres.", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Rechercher un morceau", { exact: true }).press("Tab");
  await expect(page.getByRole("combobox", { name: "Trier par", exact: true })).toBeFocused();
});

test("source edits wait for a completed scan before allowing another folder change", async ({
  page,
}) => {
  const bridge = {
    bridge_id: "12345678-1234-1234-1234-123456789abc",
    name: "Example Bridge",
    online: true,
    track_count: 0,
    root: {
      name: "Example",
      prefix: "",
      track_count: 0,
      fresh_count: 0,
      available_count: 0,
      children: [],
    },
    scanned_folders: ["A"],
    source_error: null,
  };
  let library: LibraryResponse = { bridges: [bridge], issues: [] };
  let revision = 1;
  const updates: string[][] = [];
  await harness(page, hostView(), library);
  await page.route("**/api/host/library", (route) =>
    route.fulfill({
      json: library,
      headers: { "X-Catalog-Revisions": JSON.stringify({ [bridge.bridge_id]: revision }) },
    }),
  );
  await page.route("**/api/host/library/sources", (route) => {
    updates.push(route.request().postDataJSON().folders);
    return route.fulfill({
      status: 202,
      json: { ok: true, status: "requested", scan_revision: revision },
    });
  });
  await page
    .getByRole("button", { name: "Sources et recherche de bibliothèque", exact: true })
    .click();
  await page.locator(".advanced-sources > summary").click();
  const source = page.locator(".source-card");
  const add = source.getByRole("button", { name: "Ajouter au scan", exact: true });
  await source.getByRole("textbox").fill("B");
  await add.click();
  await expect(source.getByRole("status")).toBeVisible();
  await expect(add).toBeDisabled({ timeout: 2000 });
  library = { bridges: [{ ...bridge, scanned_folders: ["A", "B"] }], issues: [] };
  revision = 2;
  await expect(add).toBeEnabled();
  await expect(source.getByText("B", { exact: true })).toBeVisible();
  await source.getByRole("textbox").fill("C");
  await add.click();
  await expect
    .poll(() => updates)
    .toEqual([
      ["A", "B"],
      ["A", "B", "C"],
    ]);
  library = {
    bridges: [{ ...bridge, scanned_folders: ["A", "B", "C"] }],
    issues: [],
  };
  revision = 3;
  await expect(add).toBeEnabled();
});

test("source confirmation cancels a stalled library request at its deadline", async ({ page }) => {
  const library: LibraryResponse = {
    issues: [],
    bridges: [
      {
        bridge_id: "12345678-1234-1234-1234-123456789abc",
        name: "Example",
        online: true,
        track_count: 0,
        scanned_folders: ["A"],
        source_error: null,
        root: {
          name: "Example",
          prefix: "",
          track_count: 0,
          fresh_count: 0,
          available_count: 0,
          children: [],
        },
      },
    ],
  };
  await harness(page, hostView(), library);
  await page
    .getByRole("button", { name: "Sources et recherche de bibliothèque", exact: true })
    .click();
  await page.locator(".advanced-sources > summary").click();
  const source = page.locator(".source-card");
  await expect(source).toBeVisible();
  await page.clock.install();
  const stalled: Route[] = [];
  await page.route("**/api/host/library", (route) => {
    stalled.push(route);
  });
  await page.route("**/api/host/library/sources", (route) =>
    route.fulfill({
      status: 202,
      json: { ok: true, status: "requested", scan_revision: 1 },
    }),
  );
  const add = source.getByRole("button", { name: "Ajouter au scan", exact: true });
  try {
    await source.getByRole("textbox").fill("B");
    await add.click();
    await expect(source.getByRole("status")).toContainText("Scan en cours");
    await page.clock.fastForward(1000);
    await expect.poll(() => stalled.length).toBe(1);
    await page.clock.fastForward(75000);
    await expect(source.getByRole("status")).toContainText("Le scan n’a pas été confirmé");
    await expect(add).toBeEnabled();
  } finally {
    for (const route of stalled) await route.abort().catch(() => {});
  }
});

test("preflight reduces the requested rounds and saves before starting atomically", async ({
  page,
}) => {
  const base = hostView();
  const ui = await harness(page, base, {
    issues: [],
    bridges: [
      {
        bridge_id: "example",
        name: "Exemple",
        track_count: 4,
        online: true,
        scanned_folders: [""],
        source_error: null,
        root: {
          name: "Exemple",
          prefix: "",
          track_count: 4,
          fresh_count: 2,
          available_count: 3,
          children: [],
        },
      },
    ],
  });
  await settings(page, "Musique");
  await page.locator(".tree input").first().check();
  await expect(page.getByRole("button", { name: "Enregistrer et lancer" })).toBeDisabled();
  await expect(page.getByText("2 morceaux neufs pour 20 manches", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Prévoir 2 manches", exact: true }).click();
  await page.getByRole("button", { name: "Enregistrer et lancer", exact: true }).click();
  await expect
    .poll(() =>
      ui.sent.some((raw) => {
        const message = JSON.parse(raw);
        return (
          message.cmd === "configure" &&
          message.start_game &&
          message.args.rounds === 2 &&
          message.args.sources.length === 1
        );
      }),
    )
    .toBe(true);
});

test("invitation draws a QR code without embedding the password", async ({ page }) => {
  await harness(page, hostView());
  await page.getByText("Inviter les joueurs", { exact: true }).click();
  const address = page.getByLabel("Adresse accessible depuis les téléphones", { exact: true });
  await address.fill("https://example.org/path?password=example-private#fragment");
  const canvas = page.getByRole("img", { name: "QR code pour rejoindre la partie" });
  await expect(canvas).toBeVisible();
  await expect
    .poll(async () => canvas.evaluate((element) => (element as HTMLCanvasElement).width))
    .toBe(192);
  await address.fill("invalid");
  await expect(page.getByRole("button", { name: "Copier le lien d’invitation" })).toBeDisabled();
});

for (const width of [320, 390, 1280]) {
  test(`player phase hierarchy and mobile layout (${width}px)`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 850 });
    const base = playerView();
    const ui = await harness(page, base);
    await expect(page.getByRole("button", { name: "Tester mon audio" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Je l'entends ✓" })).toBeDisabled();
    await layout(page);

    const game = { game_id: "g_example", rounds_total: 20, round_number: 1, clip_seconds: 25 };
    for (const state of ["PREPARING", "LOADING"] as const) {
      ui.show({
        ...base,
        phase: "IN_GAME",
        game,
        round: { state, round_id: roundId, number: 1, wait_reason: null },
      });
      await expect(
        page.getByRole("heading", {
          name: state === "PREPARING" ? "Préparation de l'extrait…" : "Chargement de l'extrait…",
        }),
      ).toBeVisible();
      await layout(page);
    }
    const now = await page.evaluate(() => performance.now());
    ui.show({
      ...base,
      phase: "IN_GAME",
      game,
      round: { state: "COUNTDOWN", round_id: roundId, number: 1, official_start_at: now + 3000 },
    });
    await expect(page.locator(".countdown")).toBeVisible();
    await layout(page);
    const open = {
      ...base,
      phase: "IN_GAME" as const,
      game,
      round: {
        state: "OPEN" as const,
        round_id: roundId,
        number: 1,
        official_start_at: now,
        deadline: now + 60000,
        my_answer: myAnswer,
        progress: null,
      },
    };
    ui.show(open);
    await expect(page.getByLabel("Ta réponse", { exact: true })).toHaveValue(myAnswer.draft_text);
    for (const nickname of [base.me.nickname, "Exemple"]) {
      ui.show({ ...open, me: { ...base.me, nickname } });
      await expect(page.locator(".identity")).toHaveText(nickname);
      await page.getByRole("button", { name: "Son", exact: true }).click();
      const soundBox = await page.getByRole("dialog", { name: "Son", exact: true }).boundingBox();
      expect(soundBox?.x).toBeGreaterThanOrEqual(0);
      expect((soundBox?.x ?? 0) + (soundBox?.width ?? 0)).toBeLessThanOrEqual(width);
      await layout(page);
      await page.keyboard.press("Escape");
    }
    await expect(page.locator(".answer-progress")).toHaveCount(0); // server hides the counter
    await expect(page.getByText("Valider rend ta réponse définitive.")).toBeVisible();
    await page.getByLabel("Ta réponse", { exact: true }).fill("   ");
    await expect(page.getByRole("button", { name: "VALIDER", exact: true })).toBeDisabled();
    await page.getByLabel("Ta réponse", { exact: true }).fill("Exemple de réponse");
    await page.getByLabel("Ta réponse", { exact: true }).press("Enter");
    await expect
      .poll(() => ui.sent.some((raw) => JSON.parse(raw).t === "ANSWER_SUBMIT"))
      .toBe(true);
    ui.show({
      ...open,
      round: {
        ...open.round,
        my_answer: { status: "LOCKED", text: "Exemple de réponse", draft_text: null },
        progress: { validated: 1, expected: 3 },
      },
    });
    await expect(page.getByText("✓ Réponse enregistrée")).toBeVisible();
    await expect(page.getByLabel("Ta réponse", { exact: true })).toHaveCount(0);
    await expect(page.getByText("1/3 ont validé")).toBeVisible();
    await layout(page);
    await page.screenshot({ path: info.outputPath("player-locked.png"), fullPage: true });

    ui.show({
      ...base,
      phase: "IN_GAME",
      game,
      round: {
        state: "REVIEW",
        auto_advance_at: null,
        round_id: roundId,
        number: 1,
        my_answer: { status: "CAPTURED", text: "Exemple de réponse", draft_text: null },
      },
    });
    await expect(page.getByRole("heading", { name: "Les réponses sont closes" })).toBeVisible();
    await expect(page.getByText("(non validée)")).toBeVisible();
    await expect(page.locator("table")).toHaveCount(0);
    await expect(page.locator(".standings")).toHaveCount(0);
    await layout(page);

    ui.show({
      ...base,
      phase: "IN_GAME",
      game,
      standings,
      round: {
        state: "REVEALED",
        round_id: roundId,
        number: 1,
        track: {
          cleared_fields: [],
          aliases: null,
          display_name:
            "Un très long titre de morceau pour vérifier le retour à la ligne sur téléphone",
          folder: "Exemple de dossier long",
          title: null,
          artist: null,
          featuring: null,
          album: null,
          year: null,
        },
        rows: players.map((p, i) => ({
          player_id: p.id,
          text: "Une réponse exemple qui reste lisible quand le téléphone est étroit.",
          status: "LOCKED",
          elapsed_ms: 4237 + i * 50,
          order: i + 1,
          near_tie: i > 0,
          points: i,
        })),
      },
    });
    await expect(page.locator(".answer-table")).toContainText("4,2 s");
    await expect(page.locator(".answer-table")).toContainText("2≈");
    await layout(page);
    await page.screenshot({ path: info.outputPath("player-reveal.png"), fullPage: true });
    ui.show({
      ...base,
      phase: "FINAL_SCORE_REVIEW",
      standings,
      finale: globalReview(hostView(), []).finale,
    });
    await expect(page.getByRole("heading", { name: "Le grand final" })).toBeVisible();
    await layout(page);
    ui.show({
      ...base,
      phase: "FINAL_RESULTS",
      standings,
      final_results: {
        unreviewed_answers: 0,
        podium_started_at: null,
        standings,
        podium: standings,
        rounds_played: 20,
        recap: [],
        finished_at: 0,
        final_adjustments: [{ player_id: players[1].id, delta: -1, note: null }],
      },
    });
    await expect(page.getByRole("heading", { name: "Résultats", exact: true })).toBeVisible();
    await expect(page.getByText("ajustement final : Exemple Alice −1")).toBeVisible();
    await layout(page);
  });

  test(`host review, final corrections and MC (${width}px)`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 850 });
    const base = hostView();
    const ui = await harness(page, base);
    await settings(page, "Avancé");
    await expect(page.getByText("Participants et connexion", { exact: true })).toBeVisible();
    await expect(page.locator(".player-ops")).not.toHaveAttribute("open", "");
    await layout(page);
    ui.show({
      ...base,
      phase: "IN_GAME",
      round: { state: "LOADING", round_id: roundId, number: 1, wait_reason: null },
      host: {
        ...base.host,
        auto_missing_references: 0,
        start_blockers: [],
        commands: ["force_start", "skip", "end_game"],
        ready_check: { ready: 2, expected: 3, can_force: true, timeout_at: 60000 },
      },
    });
    await settings(page, "Actions de la partie");
    await expect(page.getByText("2/3 prêts")).toBeVisible();
    await page.getByRole("button", { name: "Lancer quand même" }).click();
    await expect
      .poll(() => ui.sent.some((raw) => JSON.parse(raw).cmd === "force_start"))
      .toBe(true);
    await layout(page);
    const answers = players.map((p, i) => ({
      player_id: p.id,
      text: i === 2 ? "Exemple non validé" : "Exemple de réponse",
      status: i === 2 ? ("CAPTURED" as const) : ("LOCKED" as const),
      elapsed_ms: i === 2 ? null : 4200 + i * 100,
      order: i === 2 ? null : i + 1,
      near_tie: i === 1,
      late_start_ms: i === 1 ? 2300 : 0,
      judgement: "manual",
      title_correct: null,
      artist_correct: null,
      album_correct: null,
      year_correct: null,
      featuring_correct: null,
      custom_correct: null,
      auto_evidence: [],
      auto_overridden: false,
      score_revision: 0,
      points_draft: 0,
      reviewed: false,
      score_before: 0,
      received_at_wall_ms: null,
    }));
    ui.show(globalReview(base, answers));
    await expect(page.getByText("3 participants sur cette manche", { exact: true })).toBeVisible();
    await page.locator(".answer-time > summary").nth(1).click();
    await expect(page.locator(".review")).toContainText("⚠ audio +2,3 s");
    await page.locator(".manual-score > summary").first().click();
    await page.getByLabel(`Points pour ${players[0].nickname}`, { exact: true }).fill("-2");
    await page.getByLabel(`Points pour ${players[0].nickname}`, { exact: true }).press("Enter");
    await expect
      .poll(() =>
        ui.sent.some(
          (raw) => JSON.parse(raw).cmd === "score_draft" && JSON.parse(raw).args.points === -2,
        ),
      )
      .toBe(true);
    await layout(page);
    await page.screenshot({ path: info.outputPath("host-review.png"), fullPage: true });
    ui.show(
      globalReview(
        base,
        answers.map((row, i) =>
          i === 0
            ? {
                ...row,
                judgement: "manual",
                title_correct: null,
                artist_correct: null,
                album_correct: null,
                year_correct: null,
                featuring_correct: null,
                custom_correct: null,
                auto_evidence: [],
                auto_overridden: false,
                score_revision: 1,
                points_draft: -2,
                reviewed: true,
              }
            : row,
        ),
      ),
    );
    await expect(
      page.getByLabel(`Points pour ${players[0].nickname}`, { exact: true }),
    ).toBeEnabled();

    ui.show({
      ...base,
      phase: "FINAL_SCORE_REVIEW",
      standings,
      finale: globalReview(base, []).finale,
      host: {
        ...base.host,
        auto_missing_references: 0,
        start_blockers: [],
        commands: ["final_set", "final_reset", "final_validate"],
        final_review: players.map((p) => ({
          player_id: p.id,
          score_before: 3,
          draft_note: null,
          draft_delta: -1,
          score_after: 2,
          history: [],
          adjustments: [],
        })),
      },
    });
    await expect(page.getByRole("heading", { name: "Le grand final", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Lancer le podium" }).click();
    const dialog = page.getByRole("dialog").last();
    await expect(dialog).toContainText("3 Corrections finales");
    await expect(dialog.getByRole("button", { name: "Annuler" })).toBeFocused();
    await dialog.press("Escape");
    await expect(dialog).not.toBeVisible();
    await layout(page);
    await page.screenshot({ path: info.outputPath("host-final.png"), fullPage: true });

    const mc = hostView(true);
    const now = await page.evaluate(() => performance.now());
    ui.show({
      ...mc,
      phase: "IN_GAME",
      round: {
        state: "OPEN",
        round_id: roundId,
        number: 1,
        official_start_at: now,
        deadline: now + 60000,
        validated: 1,
        expected: 2,
        per_player: players.slice(1).map((p, i) => ({
          player_id: p.id,
          validated: i === 0,
          text: i === 0 ? "Live answer" : null,
          status: i === 0 ? "LOCKED" : "NONE",
        })),
      },
      host: { ...mc.host, start_blockers: [], commands: ["close", "add_time", "skip", "end_game"] },
    } as HostView);
    await expect(page.getByRole("heading", { name: "La manche est en cours." })).toBeVisible();
    await expect(page.getByText("Morceau visible au MC")).toBeVisible();
    await expect(page.getByLabel("Ta réponse", { exact: true })).toHaveCount(0);
    await expect(
      page.getByRole("button", {
        name: "Lancer le podium",
        exact: true,
      }),
    ).toHaveCount(0);
    await expect(page.locator(".mc-progress")).toContainText("✓ Réponse validée");
    await layout(page);
    await page.screenshot({ path: info.outputPath("host-mc.png"), fullPage: true });
  });
}

for (const width of [320, 1280]) {
  test(`joining has one clear primary action (${width}px)`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 850 });
    await page.route("**/api/session", (route) =>
      route.fulfill({ status: 401, json: { error: "unauthenticated" } }),
    );
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "À l’oreille. Entre amis." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Rejoindre la partie" })).toBeVisible();
    await page.getByLabel("Pseudo", { exact: true }).focus();
    await expect(page.getByLabel("Pseudo", { exact: true })).toBeFocused();
    await expect(page.getByRole("button", { name: "Entrer", exact: true })).toHaveCount(1);
    await layout(page);
    await page.screenshot({ path: info.outputPath("join.png"), fullPage: true });
  });
}

test("the entry copy remains translated in English", async ({ page }) => {
  await page.route("**/api/session", (route) =>
    route.fulfill({ status: 401, json: { error: "unauthenticated" } }),
  );
  await page.goto("/?lang=en");
  await expect(page.getByRole("heading", { name: "By ear. With friends." })).toBeVisible();
  await expect(page.getByLabel("Nickname", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Game password", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Join", exact: true })).toBeVisible();
});

test("recovery submits nickname and shared session code without a password", async ({ page }) => {
  await page.route("**/api/session", (route) =>
    route.fulfill({ status: 401, json: { error: "unauthenticated" } }),
  );
  let submitted: { code: string; nickname: string; invitation: string } | undefined;
  await page.route("**/api/session/access", (route) => {
    submitted = route.request().postDataJSON();
    return route.fulfill({ status: 401, json: { error: "recovery_invalid" } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Retrouver ma place", exact: true }).click();
  await expect(page.getByRole("button", { name: "Entrer", exact: true })).toHaveCount(1);
  await page.getByLabel("Pseudo", { exact: true }).fill("Alice");
  await page.getByLabel("Code de session", { exact: true }).fill("ab2xyz");
  await expect(page.getByLabel("Mot de passe de la partie", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Entrer", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Code de session ou invitation invalide.");
  expect(submitted).toEqual({ code: "AB2XYZ", nickname: "Alice", invitation: "" });
  await page.getByRole("button", { name: "Rejoindre avec un nouveau pseudo", exact: true }).click();
  await expect(page.getByLabel("Pseudo", { exact: true })).toBeVisible();
});

test("connection errors and joining recover with clear feedback", async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 850 });
  let connected = false;
  await page.route("**/api/session", (route) =>
    connected ? route.fulfill({ status: 401, json: { error: "unauthenticated" } }) : route.abort(),
  );
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Serveur injoignable" })).toBeVisible();
  connected = true;
  await page.getByRole("button", { name: "Réessayer" }).click();
  await expect(page.getByRole("heading", { name: "Rejoindre la partie" })).toBeVisible();
  await page.route("**/api/session/join", (route) =>
    route.fulfill({ status: 401, json: { error: "bad_password" } }),
  );
  await page.getByLabel("Pseudo", { exact: true }).fill("Exemple");
  await page.getByLabel("Mot de passe de la partie").fill("example-wrong-password");
  await page.getByRole("button", { name: "Entrer", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Mot de passe incorrect");
  await expect(page.getByLabel("Pseudo", { exact: true })).toHaveValue("Exemple");
  await layout(page);
  await page.screenshot({ path: info.outputPath("join-mobile.png"), fullPage: true });
});

test("reconnection disables host commands until the connection returns", async ({ page }) => {
  const base = hostView();
  const ui = await harness(page, base);
  ui.disconnect(1001);
  await expect(page.getByText("Reconnexion…", { exact: true })).toBeVisible();
  await expect(page.locator("fieldset.host")).toHaveAttribute("disabled", "");
  await expect(page.locator("fieldset.host")).not.toHaveAttribute("disabled", "");
  await expect(page.getByText("Reconnexion…", { exact: true })).toHaveCount(0);
});

test("library and diagnostic requests expose loading, errors and retry", async ({ page }) => {
  await harness(page, hostView());
  let fail = true;
  await page.route("**/api/host/library/search**", (route) =>
    route.fulfill({ json: { total: 0, tracks: [] } }),
  );
  await page.route("**/api/host/library", (route) =>
    fail
      ? route.fulfill({ status: 503, json: { error: "network" } })
      : route.fulfill({ json: { bridges: [] } }),
  );
  // A new catalogue causes the existing UI to reload the folder tree.
  await page.reload();
  await settings(page, "Musique");
  await expect(page.locator(".setup").getByRole("alert")).toContainText("Serveur injoignable");
  fail = false;
  await page.locator(".setup").getByRole("button", { name: "Réessayer" }).click();
  await expect(page.getByText("Aucun Bridge connecté")).toBeVisible();
  await page.route("**/api/host/diagnostics", (route) =>
    route.fulfill({ status: 503, json: { error: "network" } }),
  );
  await settings(page, "Avancé");
  await page.getByText("Diagnostic", { exact: true }).click();
  const diagnostics = page.locator("details", {
    has: page.getByText("Diagnostic", { exact: true }),
  });
  await expect(diagnostics.getByRole("alert")).toHaveText("Serveur injoignable");
  await page.route("**/api/host/diagnostics", (route) =>
    route.fulfill({ json: { example: true } }),
  );
  await diagnostics.getByRole("button", { name: "Réessayer" }).click();
  await diagnostics.getByText("Avancé", { exact: true }).click();
  await expect(diagnostics.locator("pre")).toContainText('"example": true');
});

test("clip download errors can be retried without hiding the answer form", async ({
  page,
  browserName,
}) => {
  const base = playerView();
  const ui = await harness(page, base);
  test.skip(
    browserName === "webkit" && (await page.evaluate(() => typeof AudioContext === "undefined")),
    "This WebKit build has no Web Audio support; verify audio on Safari separately.",
  );
  await page.getByRole("button", { name: "Tester mon audio", exact: true }).click();
  let requests = 0;
  await page.route("**/api/audio/a_example", (route) => {
    requests += 1;
    return route.abort();
  });
  const now = await page.evaluate(() => performance.now());
  ui.show({
    ...base,
    phase: "IN_GAME",
    audio: {
      current: { asset_id: "a_example", url: "/api/audio/a_example", duration_ms: 8000 },
      next: null,
    },
    round: {
      state: "OPEN",
      round_id: roundId,
      number: 1,
      official_start_at: now,
      deadline: now + 60000,
      my_answer: myAnswer,
      progress: null,
    },
  });
  await expect(page.locator(".audio-gate")).toContainText("⚠ Erreur audio");
  await expect(page.getByLabel("Ta réponse", { exact: true })).toBeEnabled();
  await page.locator(".audio-gate").getByRole("button", { name: "Réessayer" }).click();
  await expect.poll(() => requests).toBeGreaterThan(4);
});

test("text colours meet AA contrast and reduced motion stops the record", async ({ page }) => {
  await harness(page, playerView());
  const colours = await page.evaluate(() => {
    const style = getComputedStyle(document.documentElement);
    return Object.fromEntries(
      [
        "bg",
        "surface",
        "surface-alt",
        "text",
        "muted",
        "accent",
        "accent-text",
        "danger",
        "warn",
      ].map((name) => [name, style.getPropertyValue(`--${name}`).trim()]),
    );
  });
  const luminance = (hex: string | undefined) => {
    if (!hex) throw new Error("Missing colour token");
    const full =
      hex.length === 4
        ? `#${hex
            .slice(1)
            .split("")
            .map((digit) => digit.repeat(2))
            .join("")}`
        : hex;
    const values = [1, 3, 5]
      .map((i) => Number.parseInt(full.slice(i, i + 2), 16) / 255)
      .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    const [r = 0, g = 0, b = 0] = values;
    return r * 0.2126 + g * 0.7152 + b * 0.0722;
  };
  for (const [foreground, background] of [
    ["text", "bg"],
    ["muted", "bg"],
    ["muted", "surface"],
    ["muted", "surface-alt"],
    ["accent-text", "accent"],
    ["danger", "surface"],
    ["warn", "surface-alt"],
  ]) {
    const [a = 0, b = 0] = [
      luminance(colours[foreground ?? ""]),
      luminance(colours[background ?? ""]),
    ].sort((x, y) => y - x);
    expect((a + 0.05) / (b + 0.05), `${foreground}/${background}`).toBeGreaterThanOrEqual(4.5);
  }
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(
    await page.evaluate(() => {
      const record = document.querySelector(".record");
      if (!record) return false;
      record.classList.add("record-playing");
      return getComputedStyle(record).animationName === "none";
    }),
  ).toBe(true);
});

test("superseded sessions can resume and removed players get an explicit state", async ({
  page,
}) => {
  const ui = await harness(page, playerView());
  ui.disconnect(4001);
  await expect(
    page.getByRole("heading", { name: "Ouvert ailleurs — reprendre ici" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Reprendre ici", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Tout le monde s’installe." })).toBeVisible();
  ui.disconnect(4003);
  await expect(page.getByRole("heading", { name: "Tu as été retiré de la partie" })).toBeVisible();
});

test("audio failure leaves the game reachable and offers a retry", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "AudioContext", { value: undefined });
  });
  await harness(page, playerView());
  await page.getByRole("button", { name: "Tester mon audio", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Le son n’a pas pu démarrer.");
  await expect(page.getByRole("heading", { name: "Joueurs (3)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Tester mon audio", exact: true })).toBeEnabled();
});

test("preparation tabs preserve drafts, guard Escape and restore opening focus", async ({
  page,
}) => {
  const base = hostView();
  const ui = await harness(page, base);
  await expect(page.locator(".setup")).not.toBeVisible();
  const opener = page.getByRole("button", { name: "Préparer la partie", exact: true });
  await opener.focus();
  await opener.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Préparer la partie", exact: true });
  const music = dialog.getByRole("tab", { name: "Musique", exact: true });
  await music.focus();
  await music.press("ArrowRight");
  await expect(dialog.getByRole("tab", { name: "Règles", exact: true })).toBeFocused();
  await page.keyboard.press("ArrowRight");
  const clip = dialog.getByLabel("Durée des extraits (s)", { exact: true });
  await clip.fill("9");
  await dialog.getByRole("tab", { name: "Musique", exact: true }).click();
  await dialog.getByRole("tab", { name: "Rythme", exact: true }).click();
  await expect(clip).toHaveValue("9");
  await page.keyboard.press("Escape");
  const confirmation = page.getByRole("dialog", {
    name: "Abandonner les modifications ?",
    exact: true,
  });
  await expect(confirmation).toBeVisible();
  await confirmation.getByRole("button", { name: "Annuler", exact: true }).click();
  await expect(dialog).toBeVisible();
  ui.show({
    ...base,
    host: { ...base.host, settings: { ...base.host.settings, clip_seconds: 9 } },
  });
  await expect(dialog.getByText("✓ Enregistré", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(opener).toBeFocused();
});

test("equal score acknowledgements still retain distinct title and artist decisions", async ({
  page,
}) => {
  const base = hostView();
  const ui = await harness(page, base);
  const row: ReviewRow = {
    player_id: players[0].id,
    text: "Example answer",
    status: "LOCKED",
    elapsed_ms: 1000,
    order: 1,
    near_tie: false,
    late_start_ms: 0,
    points_draft: 0,
    reviewed: false,
    score_before: 0,
    received_at_wall_ms: null,
    judgement: "manual",
    title_correct: null,
    artist_correct: null,
    album_correct: null,
    year_correct: null,
    featuring_correct: null,
    custom_correct: null,
    auto_evidence: [],
    auto_overridden: false,
    score_revision: 0,
  };
  const review = globalReview(
    {
      ...base,
      rules: {
        answer_max_chars: 1000,
        scoring_mode: "manual",
        acceptance_threshold: 90,
        answer_fields: ["title", "artist"],
        album_points: 1,
        year_points: 1,
        featuring_points: 1,
        answer_mode: "both",
        title_points: 2,
        artist_points: 3,
        custom_points: 1,
        instructions: "",
        captured_policy: "manual",
      },
    },
    [row],
  );
  ui.show(review);
  const title = page.locator(".criterion").first();
  const artist = page.locator(".criterion").last();
  await title.getByRole("button", { name: "Trouvé", exact: true }).click();
  await expect(artist.getByRole("button", { name: "Manqué", exact: true })).toBeDisabled();
  const echo = (changes: Partial<ReviewRow>) =>
    ui.show({
      ...review,
      host: {
        ...review.host,
        review_rounds: review.host.review_rounds.map((round) => ({
          ...round,
          answers: [{ ...row, ...changes }],
        })),
      },
    });
  echo({ points_draft: 2, judgement: "criteria", title_correct: true, score_revision: 1 });
  await expect(artist.getByRole("button", { name: "Manqué", exact: true })).toBeEnabled();
  await expect(page.locator(".review-status")).toHaveText("1 / 2 critères notés");
  await artist.getByRole("button", { name: "Manqué", exact: true }).click();
  echo({ points_draft: 2, judgement: "criteria", title_correct: true, score_revision: 1 });
  await expect(artist.getByRole("button", { name: "Manqué", exact: true })).toBeDisabled();
  echo({
    points_draft: 2,
    judgement: "criteria",
    title_correct: true,
    artist_correct: false,
    reviewed: true,
    auto_evidence: [],
    auto_overridden: false,
    score_revision: 2,
  });
  await expect(artist.getByRole("button", { name: "Manqué", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.locator(".review-status")).toHaveText("✓ Vérifiée");
  await page.getByRole("button", { name: "Tout bon", exact: true }).click();
  await expect
    .poll(() =>
      ui.sent.some((raw) => {
        const message = JSON.parse(raw);
        return (
          message.cmd === "score_draft" &&
          message.args.points === 5 &&
          message.args.expected_revision === 2
        );
      }),
    )
    .toBe(true);
});

test("correction reasons block publication until the combined server echo", async ({ page }) => {
  const base = hostView();
  const ui = await harness(page, base);
  const review = globalReview(base, []);
  const rows =
    review.host.final_review?.map((row, index) =>
      index === 0 ? { ...row, draft_delta: 1, score_after: 1 } : row,
    ) ?? [];
  const corrected = { ...review, host: { ...review.host, final_review: rows } };
  ui.show(corrected);
  await page.locator(".finale-adjustments > summary").click();
  const row = page.locator(".final-table tr", { hasText: players[0].nickname });
  const publish = page.getByRole("button", {
    name: "Lancer le podium",
    exact: true,
  });
  await row.getByLabel("Motif facultatif", { exact: true }).fill("Example bonus reason");
  await expect(publish).toBeDisabled();
  await row.getByRole("button", { name: "Enregistrer le motif", exact: true }).click();
  ui.show(corrected);
  await expect(publish).toBeDisabled();
  ui.show({
    ...corrected,
    host: {
      ...corrected.host,
      final_review: rows.map((value, index) =>
        index === 0 ? { ...value, draft_note: "Example bonus reason" } : value,
      ),
    },
  });
  await expect(publish).toBeEnabled();
  await expect
    .poll(() =>
      ui.sent.some((raw) => {
        const message = JSON.parse(raw);
        return (
          message.cmd === "final_set" &&
          message.args.note === "Example bonus reason" &&
          message.args.delta === 1 &&
          message.args.expected_delta === 1
        );
      }),
    )
    .toBe(true);
});

test("the library modal remembers its page and sends sorting before pagination", async ({
  page,
}) => {
  await harness(page, hostView());
  const requests: URLSearchParams[] = [];
  await page.route("**/api/host/library/search**", (route) => {
    requests.push(new URL(route.request().url()).searchParams);
    return route.fulfill({ json: { total: 80, tracks: [] } });
  });
  const opener = page.getByRole("button", {
    name: "Sources et recherche de bibliothèque",
    exact: true,
  });
  await opener.click();
  const dialog = page.getByRole("dialog", {
    name: "Sources et recherche de bibliothèque",
    exact: true,
  });
  await dialog.getByRole("combobox", { name: "Trier par", exact: true }).selectOption("artist");
  await expect.poll(() => requests.at(-1)?.get("sort")).toBe("artist");
  await dialog.getByRole("button", { name: "Page suivante", exact: true }).click();
  await expect.poll(() => requests.at(-1)?.get("offset")).toBe(requests.at(-1)?.get("limit"));
  await page.keyboard.press("Escape");
  await expect(opener).toBeFocused();
  await opener.click();
  await expect(dialog.getByRole("combobox", { name: "Trier par", exact: true })).toHaveValue(
    "artist",
  );
  await expect(dialog).toContainText(
    `Page 2 sur ${Math.ceil(80 / Number(requests.at(-1)?.get("limit")))}`,
  );
});

test("team podium comes first and restarting the full library requires explicit confirmation", async ({
  page,
}) => {
  const base = hostView();
  const ui = await harness(page, base);
  ui.show({
    ...base,
    phase: "FINAL_RESULTS",
    team_standings: [
      { team: "Example team", score: 10, rank: 1, members: [players[0].id, players[1].id] },
    ],
    final_results: {
      unreviewed_answers: 0,
      podium_started_at: null,
      finished_at: 60,
      rounds_played: 2,
      standings,
      podium: standings,
      recap: [],
      final_adjustments: [],
    },
    host: { ...base.host, commands: ["new_game", "end_session"] },
  });
  await expect(page.locator(".podium")).toContainText("Example team");
  await expect(page.locator(".podium")).not.toContainText(players[0].nickname);
  await expect(
    page.getByRole("heading", { name: "Classement individuel", exact: true }),
  ).toBeVisible();
  const opener = page.getByRole("button", {
    name: "Recommencer avec toute la bibliothèque",
    exact: true,
  });
  await opener.click();
  const dialog = page.getByRole("dialog", {
    name: "Recommencer avec toute la bibliothèque",
    exact: true,
  });
  await page.keyboard.press("Escape");
  expect(ui.sent.some((raw) => JSON.parse(raw).cmd === "new_game")).toBe(false);
  await expect(opener).toBeFocused();
  await opener.click();
  await dialog.getByRole("button", { name: "Confirmer", exact: true }).click();
  await expect
    .poll(() =>
      ui.sent.some((raw) => {
        const message = JSON.parse(raw);
        return message.cmd === "new_game" && message.args.reset_library === true;
      }),
    )
    .toBe(true);
});

test("live finale shows confirmed points, pending answers and stable mobile layouts", async ({
  page,
}, info) => {
  const base = playerView();
  const ui = await harness(page, base);
  const host = globalReview(hostView(), []);
  const finale = host.finale;
  if (!finale) throw new Error("Finale fixture");
  const round = {
    awards_pending: false,
    round_id: roundId,
    number: 1,
    included: true,
    track: {
      title: "Zouhair Bahaoui - DÉCAPOTABLE (EXCLUSIVE Music Video) | زهير البهاوي",
      artist: "Zouhair Bahaoui",
      cleared_fields: [],
      aliases: null,
      display_name: "Zouhair Bahaoui - DÉCAPOTABLE (EXCLUSIVE Music Video) | زهير البهاوي.mp4",
      folder: "",
      featuring: null,
      album: null,
      year: null,
    },
    answers: players.map((p, index) => ({
      player_id: p.id,
      text: index === 2 ? null : "DÉCAPOTABLE",
      points: 0,
      reviewed: false,
      revision: 0,
      title_correct: null,
      artist_correct: null,
      album_correct: null,
      year_correct: null,
      featuring_correct: null,
      custom_correct: null,
    })),
  };
  const live: PlayerView = {
    ...base,
    phase: "FINAL_SCORE_REVIEW",
    finale: { ...finale, round, expected: 3 },
  };
  ui.show(live);
  await expect(page.getByRole("heading", { name: "Le grand final", exact: true })).toBeVisible();
  await expect(page.locator(".finale-answer").first()).toContainText("En attente");
  await expect(page.locator(".score-changed")).toHaveCount(0);
  const scored: PlayerView = {
    ...live,
    finale: {
      ...finale,
      expected: 3,
      reviewed: 1,
      round: {
        ...round,
        answers: round.answers.map((answer, index) =>
          index === 0 ? { ...answer, points: 2, reviewed: true, revision: 1 } : answer,
        ),
      },
      standings: finale.standings.map((row, index) => ({
        ...row,
        score: index === 0 ? 2 : 0,
        rank: index === 0 ? 1 : 2,
      })),
    },
  };
  ui.show(scored);
  await expect(page.locator(".finale-answer").first()).toContainText("2 pts");
  await expect(page.locator(".my-finale-score > strong")).toContainText("2");
  await expect(page.locator(".finale-activity")).toContainText("+2 points");
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 950 });
    await layout(page);
    await page.screenshot({ path: info.outputPath(`finale-player-${width}.png`), fullPage: true });
  }
  await page.reload();
  await expect(page.locator(".my-finale-score > strong")).toContainText("2");
  await expect(page.locator(".score-changed")).toHaveCount(0);
  await expect(page.locator(".finale-activity")).toHaveText("Suivez les points en direct");
});

test("shared finale keeps audio recovery reachable for players and hosts", async ({ page }) => {
  const base = playerView();
  const ui = await harness(page, base);
  const finale = globalReview(hostView(), []).finale;
  const now = await page.evaluate(() => performance.now());
  const audio = {
    asset_id: "a_example1",
    url: "/api/audio/a_example1",
    duration_ms: 20000,
    bytes: 32,
    format: "opus" as const,
  };
  const play = {
    play_id: "play_example1",
    asset_id: audio.asset_id,
    start_at: now + 1000,
    clip_offset: 0,
  };
  ui.show({
    ...base,
    phase: "FINAL_SCORE_REVIEW",
    finale,
    audio: { current: audio, next: null },
    play,
  });
  await expect(
    page.locator("header").getByRole("button", { name: "Tester mon audio", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Le grand final", exact: true })).toBeVisible();
  const host = globalReview(hostView(), []);
  ui.show({ ...host, audio: { current: audio, next: null }, play });
  await expect(
    page.locator("header").getByRole("button", { name: "Tester mon audio", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Arrêter la réécoute", exact: true }),
  ).toBeEnabled();
  await page.getByRole("link", { name: "Aller à la partie", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#host-controls")).toBeFocused();
});

test("podium reveals tied winners together and restored results stay immediate", async ({
  page,
}, info) => {
  const base = hostView();
  const ui = await harness(page, base);
  const now = await page.evaluate(() => performance.now());
  const tied = standings.map((row, i) => ({ ...row, rank: i < 2 ? 1 : 3, score: i < 2 ? 6 : 2 }));
  const results: HostView = {
    ...base,
    phase: "FINAL_RESULTS",
    standings: tied,
    final_results: {
      unreviewed_answers: 0,
      podium_started_at: now + 600,
      finished_at: 60,
      rounds_played: 2,
      standings: tied,
      podium: tied,
      recap: [],
      final_adjustments: [],
    },
    host: { ...base.host, commands: ["new_game", "end_session"] },
  };
  ui.show(results);
  const podium = page.locator(".ceremony-podium");
  await expect(podium.locator(".podium-visible")).toHaveCount(0);
  await expect(page.locator(".end-actions")).toHaveCount(0);
  await expect(podium.locator(".podium-visible")).toHaveCount(1);
  await expect(podium.locator(".podium-visible")).toContainText(players[2].nickname);
  await expect(podium.locator(".podium-visible")).toHaveCount(3);
  await expect(page.getByRole("heading", { name: "Nos vainqueurs ex æquo !" })).toBeVisible();
  await expect(page.locator(".podium-announcement")).toContainText(players[0].nickname);
  await expect(page.locator(".podium-announcement")).toContainText(players[1].nickname);
  await expect(page.locator(".end-actions")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Résultats", exact: true })).toBeVisible();
  await expect(page.locator(".end-actions")).toBeVisible();
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 950 });
    await layout(page);
    await page.screenshot({ path: info.outputPath(`finale-podium-${width}.png`), fullPage: true });
  }
  ui.show({
    ...results,
    final_results: results.final_results && {
      ...results.final_results,
      unreviewed_answers: 0,
      podium_started_at: null,
    },
  });
  await page.reload();
  await expect(podium.locator(".podium-visible")).toHaveCount(3);
  await expect(page.locator(".celebration-sparks")).toHaveCount(0);
  await expect(page.locator(".end-actions")).toBeVisible();
});

test("host preparation stays separate from the presented round and shared replay", async ({
  page,
}, info) => {
  const base = hostView();
  const ui = await harness(page, base);
  const track = {
    title: "La kiffance",
    artist: "Naps",
    cleared_fields: [],
    aliases: null,
    display_name: "Naps - La kiffance (Official Video).mp4",
    folder: "",
    featuring: null,
    album: null,
    year: null,
  };
  const review = globalReview(
    base,
    players.map((p, i) => ({
      player_id: p.id,
      text: i === 2 ? null : "La kiffance — Naps",
      status: i === 2 ? "NONE" : "LOCKED",
      elapsed_ms: i === 2 ? null : 3200,
      order: i === 2 ? null : i + 1,
      near_tie: false,
      late_start_ms: 0,
      judgement: "manual",
      title_correct: null,
      artist_correct: null,
      album_correct: null,
      year_correct: null,
      featuring_correct: null,
      custom_correct: null,
      auto_evidence: [],
      auto_overridden: false,
      score_revision: 0,
      points_draft: 0,
      reviewed: false,
      score_before: 0,
      received_at_wall_ms: null,
    })),
    track,
  );
  const first = review.host.review_rounds[0];
  if (!first) throw new Error("Review fixture");
  const second = {
    ...first,
    round_id: "r_example2",
    number: 2,
    track: { ...track, title: "Aïcha" },
  };
  const state: HostView = {
    ...review,
    finale: review.finale && { ...review.finale, rounds_total: 2 },
    host: { ...review.host, review_rounds: [...review.host.review_rounds, second] },
  };
  ui.show(state);
  await page.getByLabel("Corriger une autre manche en privé").selectOption(second.round_id);
  await expect(page.locator(".finale-track h2")).toHaveText("La kiffance");
  await expect(page.locator(".review-heading > h2")).toHaveText("Aïcha");
  await page.getByRole("button", { name: "Présenter la manche 2", exact: true }).click();
  await expect
    .poll(() =>
      ui.sent.some((raw) => {
        const message = JSON.parse(raw);
        return message.cmd === "finale_reveal" && message.args.round_id === second.round_id;
      }),
    )
    .toBe(true);
  ui.show({
    ...state,
    finale: state.finale && {
      ...state.finale,
      round: {
        awards_pending: false,
        round_id: second.round_id,
        number: 2,
        track: second.track,
        included: true,
        answers: [],
      },
      revealed_round_ids: [roundId, second.round_id],
    },
  });
  await expect(page.locator(".finale-track h2")).toHaveText("Aïcha");
  await expect(page.getByRole("button", { name: "Réécouter ensemble", exact: true })).toBeEnabled();
  await page.route("**/api/host/finale/**/listen", (route) =>
    route.fulfill({ status: 503, json: { error: "review_unavailable" } }),
  );
  await page.getByRole("button", { name: "Réécouter ensemble", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("La réécoute n'a pas pu démarrer");
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 950 });
    await layout(page);
    await page.screenshot({ path: info.outputPath(`finale-host-${width}.png`), fullPage: true });
  }
});

test("small rankings keep their height during animated position changes", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  const ui = await harness(page, hostView());
  ui.show(globalReview(hostView(), []));
  const pane = page.locator(".finale-scoreboard .score-scroll");
  await expect.poll(() => pane.evaluate((el) => el.clientHeight)).toBeGreaterThan(150);
  const height = await pane.evaluate((el) => el.clientHeight);
  await pane.evaluate((el) => {
    const rows = el.querySelectorAll<HTMLElement>("[data-scroll-id]");
    const first = rows[0];
    const last = rows[rows.length - 1];
    if (!first || !last) throw new Error("Ranking fixture missing rows");
    first.style.transform = "translateY(250px)";
    last.style.transform = "translateY(-250px)";
    window.dispatchEvent(new Event("resize"));
  });
  await expect.poll(() => pane.evaluate((el) => el.clientHeight)).toBe(height);
  await pane.evaluate((el) => {
    for (const row of el.querySelectorAll<HTMLElement>("[data-scroll-id]"))
      row.style.transform = "";
  });
  await expect(pane).toHaveAttribute("data-overflow", "false");
  await expect.poll(() => pane.evaluate((el) => el.scrollHeight - el.clientHeight)).toBeLessThan(2);
});

for (const viewport of [
  { width: 1920, height: 900 },
  { width: 1366, height: 650 },
  { width: 1280, height: 720 },
  { width: 390, height: 700 },
  { width: 320, height: 640 },
  { width: 320, height: 640, font: "DejaVu Sans" },
]) {
  for (const host of [false, true]) {
    test(`answer remains in the viewport before interaction and after clip end (${viewport.width}, ${host ? "host" : "player"}${"font" in viewport ? `, ${viewport.font}` : ""})`, async ({
      page,
    }, info) => {
      await page.setViewportSize(viewport);
      const base = host ? (hostView() as Extract<HostView, { kind: "host_player" }>) : playerView();
      const ui = await harness(page, base);
      if ("font" in viewport)
        await page.evaluate((font) => {
          document.documentElement.style.fontFamily = `"${font}", sans-serif`;
        }, viewport.font);
      await page.getByRole("button", { name: "Tester mon audio", exact: true }).click();
      await page.route("**/api/audio/viewport", (route) =>
        route.fulfill({ contentType: "audio/wav", body: silentWav(8) }),
      );
      const now = await page.evaluate(() => performance.now());
      const audio = { asset_id: "viewport", url: "/api/audio/viewport", duration_ms: 8000 };
      const open = {
        ...base,
        ...(base.kind === "host_player"
          ? { host: { ...base.host, commands: [...base.host.commands, "pause"] } }
          : {}),
        rules: {
          answer_max_chars: 1000,
          scoring_mode: "manual",
          ready_only: false,
          acceptance_threshold: 90,
          answer_fields: ["title", "artist"],
          album_points: 1,
          year_points: 1,
          featuring_points: 1,
          answer_mode: "both",
          title_points: 1,
          artist_points: 1,
          custom_points: 1,
          instructions: "",
          captured_policy: "host",
        },
        phase: "IN_GAME" as const,
        game: { game_id: "g_viewport", rounds_total: 8, round_number: 3, clip_seconds: 8 },
        audio: { current: audio, next: null },
        play: {
          play_id: "play_viewport",
          asset_id: audio.asset_id,
          start_at: now + 700,
          clip_offset: 0,
        },
        round: {
          state: "OPEN" as const,
          round_id: roundId,
          number: 3,
          official_start_at: now + 700,
          deadline: now + 30000,
          my_answer: { ...myAnswer, draft_text: "" },
          progress: null,
        },
      };
      ui.show(open);
      await expect(page.locator(".open-round .record")).toHaveClass(/record-playing/);
      const input = page.getByLabel("Ta réponse", { exact: true });
      const submit = page.getByRole("button", { name: "VALIDER", exact: true });
      const before = await input.boundingBox();
      const submitBefore = await submit.boundingBox();
      await page.screenshot({ path: info.outputPath("before-any-answer-interaction.png") });
      expect(before?.y).toBeGreaterThanOrEqual(0);
      expect((submitBefore?.y ?? Infinity) + (submitBefore?.height ?? 0)).toBeLessThanOrEqual(
        viewport.height,
      );
      if (host)
        await expect(
          page.getByRole("button", { name: "Mettre en pause", exact: true }),
        ).toBeVisible();
      ui.show({ ...open, play: null });
      await expect(page.getByText("Extrait terminé", { exact: true })).toBeVisible();
      const after = await input.boundingBox();
      expect(Math.abs((after?.y ?? Infinity) - (before?.y ?? 0))).toBeLessThanOrEqual(1);
      const submitAfter = await submit.boundingBox();
      expect((submitAfter?.y ?? Infinity) + (submitAfter?.height ?? 0)).toBeLessThanOrEqual(
        viewport.height,
      );
      expect(await page.evaluate(() => window.scrollY)).toBe(0);
      await input.fill("Réponse sans défilement");
      await submit.click();
      await expect
        .poll(() => ui.sent.some((raw) => JSON.parse(raw).t === "ANSWER_SUBMIT"))
        .toBe(true);
      await layout(page);
      await page.screenshot({ path: info.outputPath("answer-viewport.png") });
    });
  }
}

for (const viewport of [
  { width: 1024, height: 560 },
  { width: 1093, height: 500 },
  { width: 1280, height: 600 },
  { width: 1440, height: 700 },
]) {
  for (const host of [false, true]) {
    test(`landscape laptop uses side columns without hiding validation (${viewport.width}, ${host ? "host" : "player"})`, async ({
      page,
    }, info) => {
      await page.setViewportSize(viewport);
      const base = host ? (hostView() as Extract<HostView, { kind: "host_player" }>) : playerView();
      const ui = await harness(page, base);
      const participants = await page.locator(".lobby .participants").boundingBox();
      const audioSetup = await page.locator(".lobby .audio-setup").boundingBox();
      expect(participants?.y).toBeCloseTo(audioSetup?.y ?? Infinity, 0);
      expect(audioSetup?.x).toBeGreaterThan((participants?.x ?? 0) + (participants?.width ?? 0));
      const header = await page.locator(".header").boundingBox();
      expect(header?.width).toBeGreaterThan(viewport.width * 0.88);
      await page.screenshot({ path: info.outputPath("lobby-laptop.png"), fullPage: true });
      await page.getByRole("button", { name: "Tester mon audio", exact: true }).click();
      await page.route("**/api/audio/laptop", (route) =>
        route.fulfill({ contentType: "audio/wav", body: silentWav(6) }),
      );
      const now = await page.evaluate(() => performance.now());
      const audio = { asset_id: "laptop", url: "/api/audio/laptop", duration_ms: 6000 };
      const open = {
        ...base,
        ...(base.kind === "host_player"
          ? { host: { ...base.host, commands: ["pause", "configure"], start_blockers: [] } }
          : {}),
        phase: "IN_GAME" as const,
        game: { game_id: "g_laptop", rounds_total: 8, round_number: 5, clip_seconds: 6 },
        rules: {
          answer_max_chars: 1000,
          scoring_mode: "manual",
          ready_only: false,
          acceptance_threshold: 90,
          answer_fields: ["title", "artist"],
          album_points: 1,
          year_points: 1,
          featuring_points: 1,
          answer_mode: "both",
          title_points: 1,
          artist_points: 1,
          custom_points: 1,
          captured_policy: "zero",
          instructions:
            "Donnez le titre et l’artiste. Une autre formulation est acceptée. Pour les titres longs, indiquez le nom principal du morceau ; les détails supplémentaires sont facultatifs.",
        },
        audio: { current: audio, next: null },
        play: {
          play_id: "laptop-play",
          asset_id: audio.asset_id,
          start_at: now + 500,
          clip_offset: 0,
        },
        round: {
          state: "OPEN" as const,
          round_id: roundId,
          number: 5,
          official_start_at: now + 500,
          deadline: now + 30000,
          my_answer: { ...myAnswer, draft_text: "" },
          progress: { validated: 1, expected: 3 },
        },
      };
      ui.show(open);
      await expect(page.locator(".open-round .record")).toHaveClass(/record-playing/);
      const input = page.getByLabel("Ta réponse", { exact: true });
      const submit = page.getByRole("button", { name: "VALIDER", exact: true });
      const field = await input.boundingBox();
      const rules = await page.locator(".open-round .game-rules").boundingBox();
      const button = await submit.boundingBox();
      expect(field?.x).toBeGreaterThan((rules?.x ?? 0) + (rules?.width ?? 0));
      expect((button?.y ?? Infinity) + (button?.height ?? 0)).toBeLessThanOrEqual(viewport.height);
      expect(await page.evaluate(() => window.scrollY)).toBe(0);
      await page.screenshot({ path: info.outputPath("answer-laptop.png") });
      ui.show({ ...open, play: null });
      await expect(page.getByText("Extrait terminé", { exact: true })).toBeVisible();
      const ended = await input.boundingBox();
      expect(ended?.x).toBeCloseTo(field?.x ?? Infinity, 0);
      expect(ended?.y).toBeCloseTo(field?.y ?? Infinity, 0);
      await input.fill("Titre — artiste");
      await input.press("Enter");
      await expect
        .poll(() => ui.sent.some((raw) => JSON.parse(raw).t === "ANSWER_SUBMIT"))
        .toBe(true);
      ui.show({
        ...open,
        play: null,
        round: {
          ...open.round,
          my_answer: { status: "LOCKED", text: "Titre — artiste", draft_text: null },
        },
      });
      await expect(page.getByText("✓ Réponse enregistrée")).toBeVisible();
      const saved = await page.locator(".open-round .answer-saved").boundingBox();
      expect(saved?.x).toBeGreaterThan((rules?.x ?? 0) + (rules?.width ?? 0));
      await layout(page);
    });
  }
}

test("zero confirmation is visible alongside a positive award and survives the animation", async ({
  page,
}) => {
  const base = playerView();
  const ui = await harness(page, base);
  const source = globalReview(hostView(), []);
  if (!source.finale?.round) throw new Error("Finale fixture");
  const round = {
    ...source.finale.round,
    answers: players.slice(0, 2).map((p) => ({
      player_id: p.id,
      text: "Essai",
      points: 0,
      reviewed: false,
      revision: 0,
      title_correct: null,
      artist_correct: null,
      album_correct: null,
      year_correct: null,
      featuring_correct: null,
      custom_correct: null,
    })),
  };
  const live: PlayerView = {
    ...base,
    phase: "FINAL_SCORE_REVIEW",
    finale: { ...source.finale, round, expected: 2 },
  };
  ui.show(live);
  await expect(page.locator(".finale-answer")).toHaveCount(2);
  await expect(page.locator(".finale-answer").first()).toContainText("En attente");
  ui.show({
    ...live,
    finale: {
      ...source.finale,
      expected: 2,
      reviewed: 2,
      round: {
        ...round,
        answers: round.answers.map((a, i) => ({
          ...a,
          points: i === 0 ? 2 : 0,
          reviewed: true,
          revision: 1,
        })),
      },
      standings: source.finale.standings.map((r, i) => ({
        ...r,
        score: i === 0 ? 2 : 0,
        rank: i === 0 ? 1 : 2,
      })),
    },
  });
  await expect(page.locator(".finale-activity")).toContainText("+2 points");
  await expect(page.locator(".finale-activity")).toContainText(
    "Exemple Alice : 0 points confirmés",
  );
  await expect(page.locator(".finale-answer").nth(1)).toContainText("0 pts");
  await expect(page.locator(".score-changed, .award-confirmed")).toHaveCount(0, { timeout: 7000 });
  await expect(page.locator(".finale-activity")).toContainText("0 points confirmés");
  await page.reload();
  await expect(page.locator(".score-changed, .award-confirmed")).toHaveCount(0);
  await expect(page.locator(".finale-activity")).toHaveText("Suivez les points en direct");
});

test("absent answers stay compact and zero waits for the revision acknowledgement", async ({
  page,
}, info) => {
  const base = hostView();
  const ui = await harness(page, base);
  const answers: ReviewRow[] = players.slice(0, 2).map((p) => ({
    player_id: p.id,
    text: null,
    status: "NONE",
    elapsed_ms: null,
    order: null,
    near_tie: false,
    late_start_ms: null,
    judgement: "manual",
    title_correct: null,
    artist_correct: null,
    album_correct: null,
    year_correct: null,
    featuring_correct: null,
    custom_correct: null,
    auto_evidence: [],
    auto_overridden: false,
    score_revision: 0,
    points_draft: 0,
    reviewed: false,
    score_before: 0,
    received_at_wall_ms: null,
  }));
  const state = globalReview(base, answers, {
    cleared_fields: [],
    aliases: null,
    display_name: "Example.mp3",
    title: "Titre test",
    artist: null,
    folder: "",
    featuring: null,
    album: null,
    year: null,
  });
  ui.show(state);
  await expect(page.locator(".answer-card")).toHaveCount(0);
  await expect(page.locator(".absent-answer")).toHaveCount(2);
  await expect(page.getByText("2 participants sur cette manche", { exact: true })).toBeVisible(); // late/non-participating third player is not an absent answer
  await expect(page.locator(".expected-answer")).toContainText("Référence manquante : à vérifier");
  await page.locator(".expected-answer").getByRole("button").click();
  await expect(page.getByRole("dialog", { name: fr["ux.editTrack"], exact: true })).toBeVisible();
  await page
    .locator(".metadata-editor")
    .getByRole("button", { name: "Annuler", exact: true })
    .click();
  const row = page.locator(".absent-answer").first();
  await row.getByRole("button", { name: "Confirmer 0 point", exact: true }).click();
  await expect(row.getByRole("button", { name: "Confirmer 0 point", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Lancer le podium", exact: true })).toBeDisabled();
  ui.show(state); // zero in an old state is not its acknowledgement
  await expect(row.getByRole("button", { name: "Confirmer 0 point", exact: true })).toBeDisabled();
  const first = state.host.review_rounds[0];
  if (!first) throw new Error("Review fixture");
  ui.show({
    ...state,
    host: {
      ...state.host,
      review_rounds: [
        {
          ...first,
          answers: answers.map((a, i) =>
            i === 0 ? { ...a, reviewed: true, score_revision: 1 } : a,
          ),
        },
      ],
    },
  });
  await expect(row.locator(".absence-award")).toContainText("0 pts");
  await expect(row.locator(".absence-award")).toContainText("Vérifiée");
  await expect(
    page
      .locator(".absent-answer")
      .nth(1)
      .getByRole("button", { name: "Confirmer 0 point", exact: true }),
  ).toBeEnabled();
  await row.locator(".manual-score > summary").click();
  await row.getByRole("textbox").fill("3");
  await row.getByRole("textbox").press("Enter");
  await expect
    .poll(() =>
      ui.sent.some((raw) => {
        const msg = JSON.parse(raw);
        return (
          msg.cmd === "score_draft" && msg.args.points === 3 && msg.args.expected_revision === 1
        );
      }),
    )
    .toBe(true);
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 700 });
    await layout(page);
    await page.screenshot({ path: info.outputPath(`absences-${width}.png`), fullPage: true });
  }
});

test("final action bar leaves the last correction reachable above it on mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 640 });
  const base = hostView();
  const ui = await harness(page, base);
  ui.show(globalReview(base, []));
  await page.locator(".finale-adjustments > summary").click();
  const reset = page.getByRole("button", { name: "Réinitialiser les corrections", exact: true });
  await reset.evaluate((element) => element.scrollIntoView({ block: "end" }));
  const resetBox = await reset.boundingBox();
  const bar = await page.locator(".finale-action-bar").boundingBox();
  expect(resetBox?.y).toBeGreaterThanOrEqual(0);
  const metrics = await page.evaluate(() => ({
    reserve: getComputedStyle(document.documentElement).getPropertyValue("--finale-bar-reserve"),
    padding: getComputedStyle(document.querySelector(".final-review") ?? document.body)
      .paddingBottom,
    scroll: document.documentElement.scrollHeight,
    inner: innerHeight,
    y: scrollY,
  }));
  expect(
    (resetBox?.y ?? Infinity) + (resetBox?.height ?? 0),
    JSON.stringify(metrics),
  ).toBeLessThanOrEqual(bar?.y ?? 0);
  await layout(page);
});

test("answer modes retain their instructions and a reachable submit action on a short phone", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 640 });
  const base = hostView() as Extract<HostView, { kind: "host_player" }>;
  const ui = await harness(page, base);
  await page.getByRole("button", { name: "Tester mon audio", exact: true }).click();
  for (const [mode, placeholder] of [
    ["both", "Le titre et l’artiste"],
    ["title", "Le titre du morceau"],
    ["artist", "Le nom de l’artiste"],
    ["custom", "Ta réponse"],
  ]) {
    const now = await page.evaluate(() => performance.now());
    ui.show({
      ...base,
      phase: "IN_GAME",
      host: { ...base.host, commands: ["pause", "configure"], start_blockers: [] },
      game: { game_id: "g_modes", rounds_total: 8, round_number: 1, clip_seconds: 8 },
      rules: {
        answer_max_chars: 1000,
        scoring_mode: "manual",
        acceptance_threshold: 90,
        answer_fields: ["title", "artist"],
        album_points: 1,
        year_points: 1,
        featuring_points: 1,
        answer_mode: mode ?? "both",
        title_points: 1,
        artist_points: 1,
        custom_points: 2,
        instructions:
          mode === "custom"
            ? "Donnez le nom du titre, puis décrivez le thème de la chanson. Les réponses peuvent contenir plusieurs mots et vous pouvez proposer une autre formulation."
            : "",
        captured_policy: "host",
      },
      round: {
        state: "OPEN",
        round_id: roundId,
        number: 1,
        official_start_at: now,
        deadline: now + 60000,
        my_answer: { ...myAnswer, draft_text: "" },
        progress: null,
      },
    });
    await expect(page.getByLabel("Ta réponse", { exact: true })).toHaveAttribute(
      "placeholder",
      placeholder ?? "",
    );
    const button = await page.getByRole("button", { name: "VALIDER", exact: true }).boundingBox();
    expect((button?.y ?? Infinity) + (button?.height ?? 0)).toBeLessThanOrEqual(640);
    if (mode === "custom")
      await expect(page.locator(".game-rules")).toContainText(
        "Les réponses peuvent contenir plusieurs mots",
      );
    await layout(page);
  }
});

test("the selected review round retains contrast while hovered", async ({ page }) => {
  const base = hostView();
  const ui = await harness(page, base);
  ui.show(globalReview(base, []));
  await page.locator(".round-browser > summary").click();
  const selected = page.locator(".review-navigation [aria-current=step]");
  await selected.hover();
  const ratio = await selected.evaluate((element) => {
    const style = getComputedStyle(element);
    const luminance = (rgb: string) => {
      const [r = 0, g = 0, b = 0] = (rgb.match(/\d+/g) ?? [])
        .slice(0, 3)
        .map((n) => Number(n) / 255)
        .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
      return r * 0.2126 + g * 0.7152 + b * 0.0722;
    };
    const values = [luminance(style.color), luminance(style.backgroundColor)].sort((a, b) => b - a);
    return ((values[0] ?? 0) + 0.05) / ((values[1] ?? 0) + 0.05);
  });
  expect(ratio).toBeGreaterThanOrEqual(4.5);
});

test("finale respects native autoplay policy and uses the existing gesture-unlocked context", async ({
  browserName,
}, info) => {
  test.skip(browserName !== "chromium", "This check exercises Chromium's native autoplay policy.");
  const nativeBrowser = await chromium.launch({
    ...(info.project.use.channel ? { channel: info.project.use.channel } : {}),
    args: ["--autoplay-policy=document-user-activation-required"],
  });
  const context = await nativeBrowser.newContext({
    baseURL: String(info.project.use.baseURL),
    locale: "fr-FR",
  });
  try {
    const page = await context.newPage();
    await page.addInitScript(() => {
      const Original = window.AudioContext;
      Object.defineProperty(window, "audioContextCreations", { value: 0, writable: true });
      window.AudioContext = class extends Original {
        constructor(options?: AudioContextOptions) {
          super(options);
          const counter = window as unknown as { audioContextCreations: number };
          counter.audioContextCreations += 1;
        }
      };
    });
    const base = playerView();
    const ui = await harness(page, base);
    const source = globalReview(hostView(), []);
    const now = await page.evaluate(() => performance.now());
    await page.route("**/api/audio/native", (route) =>
      route.fulfill({ contentType: "audio/wav", body: silentWav(4) }),
    );
    const audio = { asset_id: "native", url: "/api/audio/native", duration_ms: 4000 };
    ui.show({
      ...base,
      phase: "FINAL_SCORE_REVIEW",
      finale: source.finale,
      audio: { current: audio, next: null },
      play: {
        play_id: "native-play",
        asset_id: audio.asset_id,
        start_at: now + 800,
        clip_offset: 0,
      },
    });
    await expect(page.locator(".audio-gate")).toBeVisible();
    expect(
      await page.evaluate(
        () => (window as unknown as { audioContextCreations: number }).audioContextCreations,
      ),
    ).toBe(0);
    await page
      .locator("header")
      .getByRole("button", { name: "Tester mon audio", exact: true })
      .click();
    await expect(page.locator(".audio-gate")).toHaveCount(0);
    await expect(page.locator(".finale-track .record")).toHaveClass(/record-playing/);
    expect(
      await page.evaluate(
        () => (window as unknown as { audioContextCreations: number }).audioContextCreations,
      ),
    ).toBe(1);
    await page.getByRole("button", { name: "Son", exact: true }).click();
    await page.getByLabel("Ambiance sonore du final").uncheck();
    await page.keyboard.press("Escape");
    ui.show({ ...base, phase: "FINAL_SCORE_REVIEW", finale: source.finale });
    await page.reload();
    await page.getByRole("button", { name: "Son", exact: true }).click();
    await expect(page.getByLabel("Ambiance sonore du final")).not.toBeChecked();
  } finally {
    await nativeBrowser.close();
  }
});

for (const viewport of [
  { width: 1280, height: 720 },
  { width: 1440, height: 900 },
  { width: 390, height: 740 },
]) {
  test(`score batches follow local viewport and confirmed zero awards (${viewport.width})`, async ({
    page,
  }, info) => {
    await page.setViewportSize(viewport);
    const base = hostView();
    const ui = await harness(page, base);
    const people = Array.from({ length: 24 }, (_, index) => ({
      ...players[1],
      id: `p_many${index}`,
      nickname: `Player ${index + 1}`,
      is_me: false,
    }));
    const answers: ReviewRow[] = people.map((person) => ({
      player_id: person.id,
      text: null,
      status: "NONE",
      elapsed_ms: null,
      order: null,
      near_tie: false,
      late_start_ms: 0,
      points_draft: 0,
      reviewed: false,
      score_before: 0,
      received_at_wall_ms: null,
      judgement: "manual",
      title_correct: null,
      artist_correct: null,
      album_correct: null,
      year_correct: null,
      featuring_correct: null,
      custom_correct: null,
      auto_evidence: [],
      auto_overridden: false,
      score_revision: 0,
    }));
    const seeded = globalReview({ ...base, players: people }, answers);
    if (!seeded.finale) throw new Error("Finale fixture");
    const review: HostView = {
      ...seeded,
      finale: {
        ...seeded.finale,
        standings: people.map((person) => ({ player_id: person.id, rank: 1, score: 0 })),
      },
      host: {
        ...seeded.host,
        final_review: people.map((person) => ({
          player_id: person.id,
          score_before: 0,
          draft_note: null,
          draft_delta: 0,
          score_after: 0,
          history: [],
          adjustments: [],
        })),
      },
    };
    ui.show(review);
    const pane = page.locator(".review-section .score-scroll");
    // The scoring list starts below the fold. It must already have useful height,
    // rather than being squeezed into the remaining space at its initial position.
    await expect.poll(() => pane.evaluate((el) => el.clientHeight)).toBeGreaterThan(240);
    await pane.scrollIntoViewIfNeeded();
    const initialHeight = await pane.evaluate((el) => el.clientHeight);
    await page.evaluate(() => window.dispatchEvent(new Event("resize")));
    await expect.poll(() => pane.evaluate((el) => el.clientHeight)).toBe(initialHeight);
    await expect.poll(() => pane.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
    const visible = await pane.evaluate((el) => {
      const box = el.getBoundingClientRect();
      return Array.from(el.querySelectorAll<HTMLElement>("[data-scroll-id]"))
        .filter((node) => {
          const row = node.getBoundingClientRect();
          return row.top >= box.top - 1 && row.bottom <= box.bottom + 1;
        })
        .map((node) => node.dataset.scrollId || "");
    });
    expect(visible.length).toBeGreaterThan(0);
    const last = visible.at(-1);
    if (!last) throw new Error("Visible scoring row");
    const lastIndex = people.findIndex((person) => person.id === last);
    const zero = pane
      .locator(`[data-scroll-id="${last}"]`)
      .getByRole("button", { name: "Confirmer 0 point", exact: true });
    await zero.click();
    const before = await pane.evaluate((el) => el.scrollTop);
    ui.show(review);
    expect(await pane.evaluate((el) => el.scrollTop)).toBe(before);
    ui.show({
      ...review,
      host: {
        ...review.host,
        review_rounds: review.host.review_rounds.map((round) => ({
          ...round,
          answers: round.answers.map((answer, index) =>
            index <= lastIndex ? { ...answer, reviewed: true, score_revision: 1 } : answer,
          ),
        })),
      },
    });
    await expect.poll(() => pane.evaluate((el) => el.scrollTop)).toBeGreaterThan(before);
    const rankPane = page.locator(".finale-scoreboard > .ranking-scroll-section .score-scroll");
    await rankPane.scrollIntoViewIfNeeded();
    const intersecting = await rankPane.evaluate((el) => {
      const box = el.getBoundingClientRect();
      return Array.from(el.querySelectorAll("[data-scroll-id]")).filter((node) => {
        const row = node.getBoundingClientRect();
        return row.bottom > box.top + 3 && row.top < box.bottom - 6;
      }).length;
    });
    expect(intersecting).toBeLessThanOrEqual(5);
    expect(await rankPane.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
    await layout(page);
    await page.screenshot({
      path: info.outputPath(`score-scroll-${viewport.width}.png`),
      fullPage: true,
    });
  });
}

for (const language of ["fr", "en"] as const) {
  test(`finale audio stays testable between replays and recovers suspended playback (${language})`, async ({
    page,
    browserName,
  }, info) => {
    if (browserName === "webkit") {
      await page.goto("/");
      test.skip(
        await page.evaluate(() => typeof window.AudioContext !== "function"),
        "This WebKit runtime has no AudioContext; validate audio on Safari hardware.",
      );
    }
    await page.setViewportSize({ width: 390, height: 740 });
    await page.addInitScript(() => {
      const Original = window.AudioContext;
      const probe = { contexts: [] as AudioContext[], offsets: [] as number[] };
      Object.assign(window, { audioRecoveryProbe: probe });
      window.AudioContext = class extends Original {
        constructor(options?: AudioContextOptions) {
          super(options);
          probe.contexts.push(this);
        }
        override createBufferSource() {
          const source = super.createBufferSource();
          const start = source.start.bind(source);
          source.start = (when = 0, offset = 0) => {
            probe.offsets.push(offset);
            start(when, offset);
          };
          return source;
        }
      };
    });
    const copy = language === "fr" ? fr : en;
    const base = playerView();
    const ui = await harness(page, base);
    if (language === "en") await page.getByRole("button", { name: "English", exact: true }).click();
    await page.getByRole("button", { name: copy["lobby.testAudio"], exact: true }).click();
    const finale = globalReview(hostView(), []).finale;
    const review: PlayerView = { ...base, phase: "FINAL_SCORE_REVIEW", finale };
    ui.show(review);
    await expect(
      page.locator("header.header").getByRole("button", {
        name: copy["lobby.testAudio"],
        exact: true,
      }),
    ).toBeVisible();
    await page.getByRole("button", { name: copy["audio.settings"], exact: true }).click();
    const dialog = page.getByRole("dialog", { name: copy["audio.settings"], exact: true });
    await dialog.getByRole("button", { name: copy["lobby.testAudio"], exact: true }).click();
    await page.keyboard.press("Escape");
    const suspend = async () => {
      await page.evaluate(async () => {
        const probe = (window as unknown as { audioRecoveryProbe: { contexts: AudioContext[] } })
          .audioRecoveryProbe;
        const context = probe.contexts[0];
        if (!context) throw new Error("Expected unlocked context");
        // Some mobile browsers miss the state event while backgrounded.
        context.onstatechange = null;
        await context.suspend();
        document.dispatchEvent(new Event("visibilitychange"));
      });
    };
    await suspend();
    const recovery = page.locator(".audio-gate");
    await expect(recovery).toBeVisible(); // No replay is active: recovery must remain available.
    await page
      .locator("header")
      .getByRole("button", { name: copy["audio.reactivate"], exact: true })
      .click();
    await expect(recovery).toHaveCount(0);
    await page.route("**/api/audio/recovery", (route) =>
      route.fulfill({ contentType: "audio/wav", body: silentWav(20) }),
    );
    const now = await page.evaluate(() => performance.now());
    const audio = { asset_id: "recovery", url: "/api/audio/recovery", duration_ms: 20_000 };
    ui.show({
      ...review,
      audio: { current: audio, next: null },
      play: {
        play_id: "recovery-play",
        asset_id: audio.asset_id,
        start_at: now + 300,
        clip_offset: 0,
      },
    });
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            (window as unknown as { audioRecoveryProbe: { offsets: number[] } }).audioRecoveryProbe
              .offsets.length,
        ),
      )
      .toBe(1);
    await expect(page.locator(".finale-track .record")).toHaveClass(/record-playing/);
    await suspend();
    await expect(recovery).toBeVisible();
    await page
      .locator("header")
      .getByRole("button", { name: copy["audio.reactivate"], exact: true })
      .click();
    await expect(recovery).toHaveCount(0);
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            (window as unknown as { audioRecoveryProbe: { offsets: number[] } }).audioRecoveryProbe
              .offsets.length,
        ),
      )
      .toBe(2);
    const recovered = await page.evaluate(() => {
      const probe = (
        window as unknown as {
          audioRecoveryProbe: { contexts: AudioContext[]; offsets: number[] };
        }
      ).audioRecoveryProbe;
      return { contexts: probe.contexts.length, offsets: probe.offsets };
    });
    expect(recovered.contexts).toBe(1);
    expect(recovered.offsets[1]).toBeGreaterThan(recovered.offsets[0] ?? 0);
    await layout(page);
    await page.screenshot({
      path: info.outputPath(`audio-recovery-${language}.png`),
      fullPage: true,
    });
  });
}

test("library pages adapt, edits stay under their track and midpoint previews stop on close", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const { view, library, track } = manualFixture();
  await harness(page, view, library);
  const tracks = Array.from({ length: 35 }, (_, index) => ({
    ...track,
    track_id: index.toString(16).padStart(24, "0"),
    title: `Example track ${index + 1}`,
  }));
  await page.route("**/api/host/library/search**", (route) => {
    const params = new URL(route.request().url()).searchParams;
    const offset = Number(params.get("offset"));
    const limit = Number(params.get("limit"));
    return route.fulfill({
      json: {
        total: tracks.length,
        tracks: tracks.slice(offset, offset + limit),
        tags: [],
        linked_to: [],
      },
    });
  });
  let previewRequests = 0;
  await page.route("**/api/host/library/*/*/preview", (route) => {
    previewRequests++;
    return route.fulfill({
      contentType: "audio/wav",
      body: silentWav(15),
      headers: { "Cache-Control": "no-store, private" },
    });
  });
  await page
    .getByRole("button", { name: "Sources et recherche de bibliothèque", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Sources et recherche de bibliothèque",
    exact: true,
  });
  await expect(dialog.locator(".library-tracks > li")).toHaveCount(20);
  expect(
    await dialog
      .locator(".library-tracks")
      .evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length),
  ).toBe(2);
  const card = dialog.locator(".library-tracks > li").first();
  await card
    .getByRole("button", { name: "Corriger les informations du morceau", exact: true })
    .click();
  await expect(card.getByRole("textbox", { name: "Titre", exact: true })).toBeVisible();
  await card.getByRole("textbox", { name: "Titre", exact: true }).fill("Unsaved title");
  await dialog.getByRole("button", { name: "Page suivante", exact: true }).click();
  const confirmation = page.getByRole("dialog", {
    name: "Corriger les informations du morceau",
    exact: true,
  });
  await expect(confirmation).toContainText("Abandonner les modifications non enregistrées");
  await confirmation.getByRole("button", { name: "Annuler", exact: true }).click();
  await expect(card.getByRole("textbox", { name: "Titre", exact: true })).toHaveValue(
    "Unsaved title",
  );
  await card
    .getByRole("button", { name: "Préécouter 15 s · milieu du morceau", exact: true })
    .click();
  await expect.poll(() => previewRequests).toBe(1);
  if (await page.evaluate(() => typeof AudioContext !== "undefined")) {
    await expect(
      card.getByRole("button", { name: "Arrêter la préécoute", exact: true }),
    ).toBeVisible();
    await card.getByRole("button", { name: "Arrêter la préécoute", exact: true }).click();
    await expect
      .poll(() => card.locator("audio").evaluate((el) => (el as HTMLAudioElement).paused))
      .toBe(true);
  } else {
    // Windows WebKit lacks media support. Exercise its error/retry UI and retain
    // the layout checks; actual preview playback remains covered by Chromium.
    await expect(card.getByRole("alert")).toHaveText(fr["library.previewError"]);
    info.annotations.push({
      type: "media-unavailable",
      description: "No Web Audio in this runtime; playback requires Safari hardware validation.",
    });
  }
  await page.setViewportSize({ width: 390, height: 740 });
  await expect(card.getByRole("textbox", { name: "Titre", exact: true })).toHaveValue(
    "Unsaved title",
  );
  await card.getByRole("button", { name: "Annuler", exact: true }).click();
  await confirmation.getByRole("button", { name: "Confirmer", exact: true }).click();
  await expect(dialog.locator(".library-tracks > li")).toHaveCount(10);
  await layout(page);
  await page.screenshot({ path: info.outputPath("library-mobile.png"), fullPage: true });
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
});

test("bulk classification adds labels to selected tracks and reports completion", async ({
  page,
}) => {
  const { view, library, track } = manualFixture();
  await harness(page, view, library);
  const tracks = [
    { ...track, tags: ["existing"], title: "One" },
    { ...track, track_id: "b".repeat(24), tags: ["different"], title: "Two" },
  ];
  await page.route("**/api/host/library/search**", (route) =>
    route.fulfill({ json: { total: 2, tracks, tags: ["existing", "different"], linked_to: [] } }),
  );
  const edits: { track_id: string; metadata: { tags: string[]; enabled: boolean } }[] = [];
  await page.route("**/api/host/metadata", (route) => {
    edits.push(route.request().postDataJSON());
    return route.fulfill({ json: { ok: true } });
  });
  await page
    .getByRole("button", { name: "Sources et recherche de bibliothèque", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Sources et recherche de bibliothèque",
    exact: true,
  });
  await dialog.getByRole("checkbox", { name: "Sélectionner One", exact: true }).check();
  await dialog.getByRole("checkbox", { name: "Sélectionner Two", exact: true }).check();
  await dialog.locator(".library-bulk > summary").click();
  const bulk = dialog.locator(".library-bulk");
  await bulk.getByRole("textbox", { name: "Tags", exact: true }).fill("rock, 2000s");
  await bulk.getByRole("combobox", { name: "Activation", exact: true }).selectOption("disabled");
  await bulk
    .getByRole("button", { name: "Appliquer aux morceaux sélectionnés", exact: true })
    .click();
  await expect.poll(() => edits.length).toBe(2);
  expect(edits[0]?.metadata).toEqual({ tags: ["existing", "rock", "2000s"], enabled: false });
  expect(edits[1]?.metadata).toEqual({ tags: ["different", "rock", "2000s"], enabled: false });
  await expect(
    dialog.getByRole("status").filter({ hasText: "2 / 2 morceaux mis à jour." }),
  ).toBeVisible();
});

test("last two finale rounds can be presented again after navigating backward", async ({
  page,
}) => {
  const base = hostView();
  const ui = await harness(page, base);
  const seeded = globalReview(base, []);
  if (!seeded.finale) throw new Error("Finale fixture");
  const firstRound = seeded.host.review_rounds[0];
  if (!firstRound) throw new Error("Review round fixture");
  const rounds = [1, 2, 3].map((number) => ({
    ...firstRound,
    round_id: `r_revisit${number}`,
    number,
  }));
  let live: HostView = {
    ...seeded,
    host: {
      ...seeded.host,
      commands: [...seeded.host.commands, "finale_reveal"],
      review_rounds: rounds,
    },
    finale: { ...seeded.finale, round: null, revealed_round_ids: [], rounds_total: 3 },
  };
  ui.show(live);
  const visited = new Set<string>();
  for (const number of [2, 3, 1, 2, 3]) {
    const id = `r_revisit${number}`;
    await page
      .getByRole("combobox", { name: "Corriger une autre manche en privé", exact: true })
      .selectOption(id);
    const button = page.getByRole("button", {
      name: `${visited.has(id) ? "Représenter" : "Présenter"} la manche ${number}`,
      exact: true,
    });
    await expect(button).toBeEnabled();
    await button.click();
    await expect
      .poll(() =>
        ui.sent.some((raw) => {
          const message = JSON.parse(raw);
          return message.cmd === "finale_reveal" && message.args.round_id === id;
        }),
      )
      .toBe(true);
    visited.add(id);
    if (!live.finale) throw new Error("Live fixture");
    live = {
      ...live,
      finale: {
        ...live.finale,
        round: {
          awards_pending: false,
          round_id: id,
          number,
          track: null,
          included: true,
          answers: [],
        },
        revealed_round_ids: [...visited],
      },
    };
    ui.show(live);
    await expect(
      page.getByText(`Les joueurs voient la manche ${number}`, { exact: true }),
    ).toBeVisible();
  }
  await expect(page.locator(".finale-progress")).toContainText("3 / 3 morceaux dévoilés");
  await expect(page.getByRole("button", { name: "Lancer le podium", exact: true })).toBeEnabled();
});

test("host distinguishes duplicate nickname claims by reference", async ({ page }) => {
  const base = hostView();
  await harness(page, base);
  await page.route("**/api/host/session/access", (route) =>
    route.fulfill({
      json: {
        code: "EXAMPLE2",
        invitation: "synthetic-invitation",
        requests: [
          { request_id: "a".repeat(32), nickname: "Alice", reference: "ABCD1234" },
          { request_id: "b".repeat(32), nickname: "Alice", reference: "EFAB5678" },
        ],
      },
    }),
  );
  await page.reload();
  await expect(page.getByText("Référence : ABCD1234", { exact: true })).toBeVisible();
  await expect(page.getByText("Référence : EFAB5678", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Demande au joueur sa référence avant d’autoriser la reprise."),
  ).toBeVisible();
});

for (const lang of ["fr", "en"] as const) {
  test(`identity transfer displays reference and retains approval after saving failure (${lang})`, async ({
    page,
  }) => {
    await page.route("**/api/session", (route) =>
      route.fulfill({ status: 401, json: { error: "unauthenticated" } }),
    );
    await page.route("**/api/session/access", (route) =>
      route.fulfill({
        status: 202,
        json: {
          status: "waiting",
          request_id: "a".repeat(32),
          token: "synthetic-token",
          reference: "ABCD1234",
        },
      }),
    );
    await page.route("**/api/session/access/poll", (route) =>
      route.fulfill({ status: 503, json: { error: "persistence_failed" } }),
    );
    await page.goto(`/?lang=${lang}#join=synthetic-invitation`);
    await page.getByLabel(lang === "fr" ? "Pseudo" : "Nickname", { exact: true }).fill("Alice");
    await page
      .getByRole("button", { name: lang === "fr" ? "Entrer" : "Join", exact: true })
      .click();
    await expect(page.getByRole("status")).toContainText("ABCD1234");
    await expect(page.getByRole("alert")).toContainText(
      lang === "fr" ? "La sauvegarde a échoué" : "Saving failed",
      { timeout: 10000 },
    );
    await expect(page.getByRole("status")).toContainText("ABCD1234");
    await expect(
      page.getByRole("button", { name: lang === "fr" ? "Entrer" : "Join", exact: true }),
    ).toBeDisabled();
  });
}

test("language switch translates existing feedback, preserves entry drafts and remembers this browser", async ({
  page,
  browser,
}) => {
  await page.route("**/api/session", (route) =>
    route.fulfill({ status: 401, json: { error: "unauthenticated" } }),
  );
  await page.route("**/api/session/join", (route) =>
    route.fulfill({ status: 401, json: { error: "bad_password" } }),
  );
  await page.goto("/?lang=fr");
  await page.getByLabel("Pseudo", { exact: true }).fill("Alice");
  await page
    .getByLabel("Mot de passe de la partie", { exact: true })
    .fill("example-wrong-password");
  await page.getByRole("button", { name: "Entrer", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText(fr["error.bad_password"]);
  await page.evaluate(() => {
    document.body.dataset.languageTest = "same-document";
  });
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(page.getByRole("heading", { name: en["join.headline"] })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveText(en["error.bad_password"]);
  await expect(page.getByLabel("Nickname", { exact: true })).toHaveValue("Alice");
  await expect(page.getByLabel("Game password", { exact: true })).toHaveValue(
    "example-wrong-password",
  );
  expect(await page.evaluate(() => document.body.dataset.languageTest)).toBe("same-document");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  expect(await page.evaluate(() => localStorage.getItem("openblindysir:language"))).toBe("en");
  expect(new URL(page.url()).searchParams.has("lang")).toBe(false);
  await page.reload();
  await expect(page.getByRole("heading", { name: en["join.headline"] })).toBeVisible();

  const independent = await browser.newContext();
  try {
    const other = await independent.newPage();
    await other.route("**/api/session", (route) =>
      route.fulfill({ status: 401, json: { error: "unauthenticated" } }),
    );
    await other.goto("/");
    await expect(other.getByRole("heading", { name: fr["join.headline"] })).toBeVisible();
    await expect(page.getByRole("button", { name: "English", exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  } finally {
    await independent.close();
  }
});

test("language switch preserves QR invitations and works without local storage", async ({
  page,
}) => {
  await page.addInitScript(() => {
    Storage.prototype.setItem = () => {
      throw new Error("storage unavailable");
    };
  });
  await page.route("**/api/session", (route) =>
    route.fulfill({ status: 401, json: { error: "unauthenticated" } }),
  );
  let submitted: unknown;
  await page.route("**/api/session/access", (route) => {
    submitted = route.request().postDataJSON();
    return route.fulfill({ status: 401, json: { error: "recovery_invalid" } });
  });
  await page.goto("/?lang=fr&from=invitation#join=synthetic-invitation");
  await page.getByLabel("Pseudo", { exact: true }).fill("Alice");
  const choice = page.locator("header").getByRole("button", { name: "English", exact: true });
  await choice.focus();
  await page.keyboard.press("Enter");
  await expect(choice).toBeFocused();
  await expect(page.getByLabel("Nickname", { exact: true })).toHaveValue("Alice");
  const url = new URL(page.url());
  expect(url.hash).toBe("#join=synthetic-invitation");
  expect(url.searchParams.get("from")).toBe("invitation");
  expect(url.searchParams.has("lang")).toBe(false);
  await expect(page.getByLabel("Game password", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Join", exact: true }).click();
  expect(submitted).toEqual({ nickname: "Alice", code: "", invitation: "synthetic-invitation" });
  await expect(page.getByRole("alert")).toHaveText(en["error.recovery_invalid"]);
});

test("language switch stays in the host access header and preserves its password draft", async ({
  page,
}) => {
  await page.route("**/api/session", (route) => route.fulfill({ json: { role: "player" } }));
  await page.goto("/host");
  await page.getByLabel("Mot de passe hôte", { exact: true }).fill("example-host-password");
  await page.locator("header").getByRole("button", { name: "English", exact: true }).click();
  await expect(page.getByRole("heading", { name: en["host.gateTitle"] })).toBeVisible();
  await expect(page.getByLabel(en["host.password"], { exact: true })).toHaveValue(
    "example-host-password",
  );
  await page.reload();
  await expect(page.getByRole("heading", { name: en["host.gateTitle"] })).toBeVisible();
});

test("language switch during playback preserves audio, the answer draft and the connection", async ({
  page,
}) => {
  const base = playerView();
  const ui = await harness(page, base);
  await page.evaluate(() => {
    document.body.dataset.languageTest = "same-game";
    const original = AudioContext.prototype.createBufferSource;
    AudioContext.prototype.createBufferSource = function () {
      const source = original.call(this);
      source.addEventListener("ended", () => {
        document.body.dataset.languageAudioEnded = "true";
      });
      return source;
    };
  });
  await page.getByRole("button", { name: "Tester mon audio", exact: true }).click();
  await page.route("**/api/audio/language", (route) =>
    route.fulfill({ contentType: "audio/wav", body: silentWav(30) }),
  );
  const now = await page.evaluate(() => performance.now());
  const audio = { asset_id: "language", url: "/api/audio/language", duration_ms: 30000 };
  ui.show({
    ...base,
    phase: "IN_GAME",
    game: { game_id: "g_language", round_number: 1, rounds_total: 8, clip_seconds: 30 },
    audio: { current: audio, next: null },
    play: {
      play_id: "play_language",
      asset_id: audio.asset_id,
      start_at: now + 700,
      clip_offset: 0,
    },
    round: {
      state: "OPEN",
      round_id: roundId,
      number: 1,
      official_start_at: now + 700,
      deadline: now + 90000,
      my_answer: { ...myAnswer, draft_text: "" },
      progress: null,
    },
  });
  await expect(page.locator(".open-round .record")).toHaveClass(/record-playing/);
  await page.getByLabel("Ta réponse", { exact: true }).fill("My guessed song");
  const connections = ui.sent.filter((raw) => JSON.parse(raw).t === "HELLO").length;
  await page.locator("header").getByRole("button", { name: "English", exact: true }).click();
  await expect(page.getByRole("heading", { name: en["round.openTitle"] })).toBeVisible();
  await expect(page.getByLabel("Your answer", { exact: true })).toHaveValue("My guessed song");
  await page.locator("header").getByRole("button", { name: "Français", exact: true }).click();
  await expect(page.getByLabel("Ta réponse", { exact: true })).toHaveValue("My guessed song");
  expect(await page.evaluate(() => document.body.dataset.languageTest)).toBe("same-game");
  expect(await page.evaluate(() => document.body.dataset.languageAudioEnded)).toBeUndefined();
  expect(ui.sent.filter((raw) => JSON.parse(raw).t === "HELLO").length).toBe(connections);
  await page.getByRole("button", { name: "VALIDER", exact: true }).click();
  await expect
    .poll(() =>
      ui.sent.some((raw) => {
        const message = JSON.parse(raw);
        return message.t === "ANSWER_SUBMIT" && message.text === "My guessed song";
      }),
    )
    .toBe(true);
});

for (const width of [320, 1366]) {
  for (const host of [false, true]) {
    test(`language switch remains accessible in every phase (${width}, ${host ? "host" : "player"})`, async ({
      page,
    }, info) => {
      await page.setViewportSize({ width, height: width === 320 ? 640 : 700 });
      const base = host ? (hostView() as Extract<HostView, { kind: "host_player" }>) : playerView();
      const ui = await harness(page, base);
      const review = globalReview(hostView(), []);
      const phases: AnyView[] = [
        base,
        {
          ...base,
          phase: "IN_GAME",
          game: { game_id: "g_language", round_number: 1, rounds_total: 8, clip_seconds: 25 },
          round: {
            state: "OPEN",
            round_id: roundId,
            number: 1,
            official_start_at: 1,
            deadline: 999999999,
            my_answer: myAnswer,
            progress: null,
          },
        },
        {
          ...base,
          phase: "FINAL_SCORE_REVIEW",
          finale: review.finale,
          ...(host ? { host: review.host } : {}),
        } as AnyView,
        {
          ...base,
          phase: "FINAL_RESULTS",
          final_results: {
            standings,
            podium: standings,
            rounds_played: 1,
            final_adjustments: [],
            recap: [],
            finished_at: 1780000000000,
            unreviewed_answers: 0,
            podium_started_at: null,
          },
        },
      ];
      for (const phase of phases) {
        ui.show(phase);
        await expect(page.locator(".app")).toHaveClass(
          new RegExp(`phase-${phase.phase.toLowerCase()}`),
        );
        const header = page.locator("header.header");
        await header.getByRole("button", { name: "English", exact: true }).click();
        await expect(header.getByRole("group", { name: "Language", exact: true })).toBeVisible();
        await expect(page.locator("html")).toHaveAttribute("lang", "en");
        await layout(page);
        await page.screenshot({ path: info.outputPath(`en-${phase.phase.toLowerCase()}.png`) });
        await header.getByRole("button", { name: "Français", exact: true }).click();
        await expect(header.getByRole("group", { name: "Langue", exact: true })).toBeVisible();
        await layout(page);
      }
    });
  }
}

for (const language of ["fr", "en"] as const) {
  test(`automatic scoring config keeps one input and selected criteria (${language})`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1093, height: 600 });
    const ui = await harness(page, hostView());
    if (language === "en")
      await page.locator("header").getByRole("button", { name: "English", exact: true }).click();
    const messages = language === "en" ? en : fr;
    await page.getByRole("button", { name: messages["flow.prepare"], exact: true }).click();
    const dialog = page.locator(".workspace-modal");
    await dialog.getByRole("tab", { name: messages["flow.rules"], exact: true }).click();
    await dialog
      .getByRole("combobox", { name: messages["ux.answerMode"], exact: true })
      .selectOption("fields");
    await dialog.getByRole("checkbox", { name: messages["review.album"], exact: true }).check();
    await dialog.getByRole("checkbox", { name: messages["review.year"], exact: true }).check();
    await dialog
      .getByRole("combobox", { name: messages["auto.mode"], exact: true })
      .selectOption("auto");
    await expect(dialog.getByLabel(messages["auto.threshold"], { exact: true })).toHaveValue("90");
    await dialog.getByLabel(messages["auto.threshold"], { exact: true }).fill("95");
    await dialog.getByRole("button", { name: messages["hostui.save"], exact: true }).click();
    const saved = ui.sent
      .map((raw) => JSON.parse(raw))
      .find((message) => message.cmd === "configure");
    expect(saved.args).toMatchObject({
      scoring_mode: "auto",
      acceptance_threshold: 95,
      answer_mode: "fields",
      answer_fields: ["title", "artist", "album", "year"],
    });
    await dialog
      .getByRole("combobox", { name: messages["ux.answerMode"], exact: true })
      .selectOption("custom");
    await expect(
      dialog.getByRole("combobox", { name: messages["auto.mode"], exact: true }),
    ).toBeDisabled();
    await expect(
      dialog.getByRole("combobox", { name: messages["auto.mode"], exact: true }),
    ).toHaveValue("manual");
    await layout(page);
  });

  test(`automatic evidence, explicit regrade and reveal wave controls (${language})`, async ({
    page,
  }, info) => {
    await page.setViewportSize(
      language === "en" ? { width: 390, height: 844 } : { width: 1093, height: 600 },
    );
    const ui = await harness(page, hostView());
    if (language === "en")
      await page.locator("header").getByRole("button", { name: "English", exact: true }).click();
    const messages = language === "en" ? en : fr;
    const answer: ReviewRow = {
      player_id: players[0].id,
      text: "Sapés comme jamias Maitre Gims Pilule bleue 2015",
      status: "LOCKED",
      points_draft: 4,
      reviewed: true,
      score_revision: 1,
      judgement: "criteria",
      title_correct: true,
      artist_correct: true,
      album_correct: true,
      year_correct: true,
      featuring_correct: null,
      custom_correct: null,
      order: 1,
      near_tie: false,
      elapsed_ms: 2000,
      late_start_ms: null,
      received_at_wall_ms: null,
      score_before: 0,
      auto_overridden: false,
      auto_evidence: [
        {
          criterion: "title",
          reference: "Sapés comme jamais",
          fragment: "Sapés comme jamias",
          similarity: 93.75,
          threshold: 90,
          status: "matched",
        },
      ],
    };
    const view = globalReview(hostView(), [answer], {
      title: "Sapés comme jamais",
      display_name: "Sapés comme jamais",
      folder: "Synth",
      artist: "Maître Gims",
      album: "Pilule bleue",
      year: 2015,
      featuring: "Niska",
      cleared_fields: [],
      aliases: {},
    });
    if (!view.finale?.round) throw new Error("Finale fixture");
    const active = {
      ...view,
      rules: {
        ...view.host.settings,
        answer_max_chars: 1000,
        scoring_mode: "auto",
        answer_mode: "fields",
        answer_fields: ["title", "artist", "album", "year"],
      },
      host: {
        ...view.host,
        commands: [...view.host.commands, "finale_reveal"],
        settings: {
          ...view.host.settings,
          scoring_mode: "auto",
          answer_mode: "fields",
          answer_fields: ["title", "artist", "album", "year"],
        },
      },
      finale: { ...view.finale, round: { ...view.finale.round, awards_pending: true } },
    } as HostView;
    ui.show(active);
    await expect(page.getByText(messages["auto.waves"], { exact: true })).toBeVisible();
    await page.getByRole("button", { name: messages["auto.fastForward"], exact: true }).click();
    expect(
      ui.sent
        .map((raw) => JSON.parse(raw))
        .some((message) => message.cmd === "finale_reveal" && message.args.fast_forward === true),
    ).toBe(true);
    await expect(page.locator(".expected-answer")).toContainText("Pilule bleue");
    await expect(page.locator(".expected-answer")).toContainText("2015");
    await expect(page.locator(".score-controls .criterion")).toHaveCount(4);
    const analysis = page.locator(".auto-assessment");
    await analysis.locator("summary").click();
    await expect(analysis).toContainText(
      language === "en" ? "93.8% / threshold 90%" : "93,8 % / seuil 90 %",
    );
    await page.locator(".review-heading > .track-options > summary").click();
    await page.getByRole("button", { name: messages["ux.editTrack"], exact: true }).click();
    const editor = page.locator(".review-section .metadata-editor");
    await editor.locator(".alias-editor summary").click();
    await editor
      .locator(".alias-editor")
      .getByLabel(messages["auto.aliasField"].replace("{field}", messages["review.artist"]), {
        exact: true,
      })
      .fill("Gims");
    await editor.getByRole("button", { name: messages["repair.saveRegrade"], exact: true }).click();
    expect(
      ui.sent
        .map((raw) => JSON.parse(raw))
        .some(
          (message) =>
            message.cmd === "track_metadata" &&
            message.args.regrade_auto === true &&
            message.args.aliases.artist[0] === "Gims",
        ),
    ).toBe(true);
    await layout(page);
    await page.screenshot({ path: info.outputPath("automatic-review.png"), fullPage: true });
  });
}

for (const language of ["fr", "en"] as const) {
  for (const failure of ["decode", "autoplay"] as const) {
    test(`midpoint preview recovers ${failure} failure (${language})`, async ({ page }) => {
      const { view, library, track } = manualFixture();
      const copy = language === "fr" ? fr : en;
      if (failure === "autoplay") {
        await page.addInitScript(() => {
          const original = HTMLMediaElement.prototype.play;
          let first = true;
          HTMLMediaElement.prototype.play = function () {
            if (first) {
              first = false;
              return Promise.reject(
                new DOMException("Synthetic blocked playback", "NotAllowedError"),
              );
            }
            return original.call(this);
          };
        });
      }
      await harness(page, view, library);
      if (language === "en")
        await page.getByRole("button", { name: "English", exact: true }).click();
      await page.route("**/api/host/library/search**", (route) =>
        route.fulfill({ json: { total: 1, tracks: [track], tags: [], linked_to: [] } }),
      );
      let requests = 0;
      await page.route("**/api/host/library/*/*/preview", (route) => {
        requests++;
        return route.fulfill({
          contentType: "audio/wav",
          body:
            failure === "decode" && requests === 1 ? Buffer.from("invalid-media") : silentWav(15),
        });
      });
      await page.getByRole("button", { name: copy["library.manage"], exact: true }).click();
      const card = page
        .getByRole("dialog", { name: copy["library.manage"], exact: true })
        .locator(".library-tracks > li")
        .first();
      await card.getByRole("button", { name: copy["library.preview"], exact: true }).click();
      const preview = card.locator(".private-preview");
      await expect(preview.getByRole("alert")).toHaveText(copy["library.previewError"]);
      expect(requests).toBe(1);
      await preview.getByRole("button", { name: copy["library.preview"], exact: true }).click();
      await expect(
        preview.getByRole("button", { name: copy["library.previewStop"], exact: true }),
      ).toBeVisible();
      await expect
        .poll(() => preview.locator("audio").evaluate((el) => !(el as HTMLAudioElement).paused))
        .toBe(true);
      expect(requests).toBe(failure === "decode" ? 2 : 1);
      await expect(preview.getByRole("alert")).toHaveCount(0);
      await preview.getByRole("button", { name: copy["library.previewStop"], exact: true }).click();
      await expect
        .poll(() => preview.locator("audio").evaluate((el) => (el as HTMLAudioElement).paused))
        .toBe(true);
    });
  }
}

for (const language of ["fr", "en"] as const) {
  test(`themed preview retries without losing filters and validates years locally (${language})`, async ({
    page,
  }) => {
    const { view, library, track } = manualFixture();
    await harness(page, view, library);
    const copy = language === "fr" ? fr : en;
    if (language === "en") await page.getByRole("button", { name: "English", exact: true }).click();
    let requests = 0;
    const longTag = "🎮".repeat(256);
    await page.route("**/api/host/library/selection", (route) => {
      requests++;
      if (requests === 1) return route.fulfill({ status: 503, json: { error: "unavailable" } });
      return route.fulfill({
        json: {
          matching: 4,
          available: 4,
          fresh: 3,
          unclassified: 0,
          genres: ["Rap"],
          languages: ["fr"],
          tags: [longTag],
          linked_to: [],
          years: [2012],
          examples: [{ ...track, title: "Wakfu" }],
        },
      });
    });
    await page.getByRole("button", { name: copy["flow.prepare"], exact: true }).click();
    const dialog = page.locator(".workspace-modal");
    const theme = dialog.getByRole("region", { name: copy["theme.title"], exact: true });
    await theme.getByRole("button", { name: copy["app.retry"], exact: true }).click();
    await expect(theme.locator(".theme-examples")).toContainText("Wakfu");
    await theme
      .getByRole("combobox", { name: copy["theme.tags"], exact: true })
      .selectOption(longTag);
    await expect.poll(() => requests).toBe(3);
    await theme.getByLabel(copy["theme.yearFrom"], { exact: true }).fill("20");
    await expect(theme.getByRole("alert")).toHaveText(copy["theme.invalidRange"]);
    await expect(
      dialog.getByRole("button", { name: copy["hostui.save"], exact: true }),
    ).toBeDisabled();
    await page.waitForTimeout(450);
    expect(requests).toBe(3);
    await theme.getByLabel(copy["theme.yearFrom"], { exact: true }).fill("2012");
    await expect(theme.getByRole("alert")).toHaveCount(0);
    await expect.poll(() => requests).toBe(4);
    await expect(
      dialog.getByRole("button", { name: copy["hostui.save"], exact: true }),
    ).toBeEnabled();
  });

  test(`themed nights combine criteria and configure the actual game (${language})`, async ({
    page,
  }, info) => {
    await page.setViewportSize(
      language === "fr" ? { width: 1093, height: 600 } : { width: 390, height: 844 },
    );
    const { view, library, track } = manualFixture();
    const ui = await harness(page, view, library);
    const copy = language === "fr" ? fr : en;
    if (language === "en") await page.getByRole("button", { name: "English", exact: true }).click();
    const filters: unknown[] = [];
    await page.route("**/api/host/library/selection", (route) => {
      filters.push(route.request().postDataJSON().selection_filter);
      return route.fulfill({
        json: {
          matching: 4,
          available: 4,
          fresh: 3,
          unclassified: 0,
          genres: ["Pop", "Rap"],
          languages: ["fr", "en"],
          tags: ["Génériques"],
          linked_to: ["Wakfu"],
          years: [2012],
          examples: [{ ...track, title: "Wakfu" }],
        },
      });
    });
    await page.getByRole("button", { name: copy["flow.prepare"], exact: true }).click();
    const dialog = page.locator(".workspace-modal");
    const theme = dialog.getByRole("region", { name: copy["theme.title"], exact: true });
    await expect(
      theme.locator(".theme-examples").getByText("Wakfu", { exact: true }),
    ).toBeVisible();
    await theme.getByRole("button", { name: "Rap", exact: true }).click();
    await theme
      .getByRole("combobox", { name: copy["theme.languages"], exact: true })
      .selectOption("fr");
    await theme.getByLabel(copy["theme.yearFrom"], { exact: true }).fill("2012");
    await theme.getByLabel(copy["theme.yearTo"], { exact: true }).fill("2012");
    await expect
      .poll(() => filters.at(-1))
      .toMatchObject({ genres: ["Rap"], languages: ["fr"], year_min: 2012, year_max: 2012 });
    await expect(
      theme.getByText(copy["theme.count"].replace("{available}", "4").replace("{fresh}", "3"), {
        exact: true,
      }),
    ).toBeVisible();
    await dialog.getByRole("button", { name: copy["hostui.save"], exact: true }).click();
    expect(
      ui.sent.map((raw) => JSON.parse(raw)).find((message) => message.cmd === "configure").args
        .selection_filter,
    ).toMatchObject({ genres: ["Rap"], languages: ["fr"], year_min: 2012, year_max: 2012 });
    await theme.getByRole("button", { name: copy["theme.cartoons"], exact: true }).click();
    await expect
      .poll(() => filters.at(-1))
      .toMatchObject({
        tags: ["Génériques"],
        genres: [],
        languages: [],
        year_min: null,
        year_max: null,
      });
    await layout(page);
    await page.screenshot({ path: info.outputPath(`themes-${language}.png`) });
  });

  test(`library themed filters transfer to game and invalid years stay local (${language})`, async ({
    page,
  }) => {
    const { view, library, track } = manualFixture();
    const ui = await harness(page, view, library);
    const copy = language === "fr" ? fr : en;
    if (language === "en") await page.getByRole("button", { name: "English", exact: true }).click();
    let requests = 0;
    await page.route("**/api/host/library/search**", (route) => {
      requests++;
      return route.fulfill({
        json: {
          total: 1,
          tracks: [track],
          tags: [],
          linked_to: [],
          genres: ["Rap"],
          languages: ["fr"],
          years: [2012],
        },
      });
    });
    await page.getByRole("button", { name: copy["library.manage"], exact: true }).click();
    const dialog = page.getByRole("dialog", { name: copy["library.manage"], exact: true });
    await expect(dialog.locator(".library-tracks > li")).toHaveCount(1);
    await dialog.locator(".library-extra-filters > summary").click();
    await dialog.getByRole("button", { name: "Rap", exact: true }).click();
    await dialog.getByRole("button", { name: copy["theme.french"], exact: true }).click();
    await dialog.getByRole("button", { name: "2012", exact: true }).click();
    const use = dialog.getByRole("button", { name: copy["theme.useLibrary"], exact: true });
    await expect(use).toBeEnabled();
    const before = requests;
    await dialog.getByLabel(copy["theme.yearFrom"], { exact: true }).fill("2013");
    await expect(dialog.getByRole("alert")).toContainText(copy["theme.invalidRange"]);
    expect(requests).toBe(before);
    await dialog.getByLabel(copy["theme.yearFrom"], { exact: true }).fill("2012");
    await expect(use).toBeEnabled();
    await use.click();
    expect(
      ui.sent.map((raw) => JSON.parse(raw)).find((message) => message.cmd === "configure").args
        .selection_filter,
    ).toMatchObject({ genres: ["Rap"], languages: ["fr"], year_min: 2012, year_max: 2012 });
    await expect(dialog).toHaveCount(0);
  });
}

for (const size of [
  { width: 1366, height: 768 },
  { width: 1093, height: 600 },
  { width: 390, height: 740 },
]) {
  test(`five missing criteria remain readable and oversized cards advance at ${size.width}`, async ({
    page,
  }, info) => {
    await page.setViewportSize(size);
    const ui = await harness(page, hostView());
    const answers: ReviewRow[] = players.map((person) => ({
      player_id: person.id,
      text:
        "Sapéscomme Ja m ais Maitre Gims 2015 ft niska pilule bleue " +
        "Une réponse très longue mais lisible. ".repeat(12),
      status: "LOCKED",
      points_draft: 0,
      reviewed: false,
      score_revision: 0,
      judgement: "criteria",
      title_correct: null,
      artist_correct: null,
      album_correct: null,
      year_correct: null,
      featuring_correct: null,
      custom_correct: null,
      order: null,
      near_tie: false,
      elapsed_ms: 2000,
      late_start_ms: null,
      received_at_wall_ms: null,
      score_before: 0,
      auto_overridden: false,
      auto_evidence: ["title", "artist", "album", "year", "featuring"].map((criterion) => ({
        criterion,
        reference: null,
        fragment: null,
        similarity: 0,
        threshold: 90,
        status: "missing_reference",
      })),
    }));
    const base = globalReview(hostView(), answers);
    const view = {
      ...base,
      rules: {
        ...base.host.settings,
        answer_mode: "fields",
        answer_fields: ["title", "artist", "album", "year", "featuring"],
        scoring_mode: "auto",
        answer_max_chars: 1000,
      },
    } as HostView;
    ui.show(view);
    const pane = page.locator(".review-section .score-scroll");
    const card = pane.locator(".answer-card").first();
    await expect(card).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    const widths = await card.evaluate((element) => ({
      card: element.clientWidth,
      name: element.querySelector(".answer-player")?.clientWidth ?? 0,
      answer: element.querySelector(".answer-text")?.clientWidth ?? 0,
    }));
    expect(widths.name).toBeGreaterThan(widths.card * 0.75);
    expect(widths.answer).toBeGreaterThan(widths.card * 0.75);
    await expect(card.locator(".criterion")).toHaveCount(5);
    await expect(card.locator(".review-status")).toContainText("0 / 5");
    // Opening explanations creates a genuinely oversized card, unlike the old absence-only fixture.
    await card.locator(".auto-assessment > summary").click();
    expect(await card.evaluate((el) => el.clientHeight)).toBeGreaterThan(
      await pane.evaluate((el) => el.clientHeight),
    );
    await pane.evaluate((el) => {
      el.scrollTop = 0;
      el.dispatchEvent(new Event("scroll"));
    });
    const before = await pane.evaluate((el) => el.scrollTop);
    ui.show({
      ...view,
      host: {
        ...view.host,
        review_rounds: view.host.review_rounds.map((round) => ({
          ...round,
          answers: round.answers.map((row, index) =>
            index === 0 ? { ...row, reviewed: true, score_revision: 1 } : row,
          ),
        })),
      },
    });
    await expect.poll(() => pane.evaluate((el) => el.scrollTop)).toBeGreaterThan(before + 100);
    await expect(
      page.locator("header").getByRole("button", { name: "Tester mon audio", exact: true }),
    ).toBeVisible();
    await layout(page);
    await page.screenshot({ path: info.outputPath("five-criteria-readable.png") });
  });
}

for (const language of ["fr", "en"] as const) {
  test(`draft automatic preflight blocks unchecked missing references (${language})`, async ({
    page,
  }) => {
    const { view, library } = manualFixture();
    const ui = await harness(page, view, library);
    const copy = language === "fr" ? fr : en;
    if (language === "en") await page.getByRole("button", { name: "English", exact: true }).click();
    const payloads: { scoring_criteria: string[] }[] = [];
    await page.route("**/api/host/library/selection", (route) => {
      const body = route.request().postDataJSON();
      payloads.push(body);
      return route.fulfill({
        json: {
          matching: 12,
          available: 12,
          fresh: 12,
          unclassified: 0,
          genres: [],
          languages: [],
          tags: [],
          linked_to: [],
          years: [],
          examples: [],
          reference_eligible: 12,
          reference_ready: body.scoring_criteria?.length ? 0 : 12,
          missing_by_criterion: Object.fromEntries(
            (body.scoring_criteria ?? []).map((key: string) => [key, 12]),
          ),
          reference_issues: [],
        },
      });
    });
    await page.getByRole("button", { name: copy["flow.prepare"], exact: true }).click();
    const dialog = page.getByRole("dialog", { name: copy["flow.prepare"], exact: true });
    await dialog.getByRole("tab", { name: copy["flow.rules"], exact: true }).click();
    await dialog
      .getByRole("combobox", { name: copy["auto.mode"], exact: true })
      .selectOption("auto");
    await expect(dialog.locator(".reference-preflight")).toContainText("0 / 12");
    const start = dialog.getByRole("button", { name: copy["ux.saveAndStart"], exact: true });
    await expect(start).toBeDisabled();
    await dialog.getByRole("checkbox", { name: copy["polish.acceptManual"], exact: true }).check();
    await expect(start).toBeEnabled();
    await dialog
      .getByRole("combobox", { name: copy["ux.answerMode"], exact: true })
      .selectOption("fields");
    await dialog.getByRole("checkbox", { name: copy["review.album"], exact: true }).check();
    await expect
      .poll(() => payloads.at(-1)?.scoring_criteria)
      .toEqual(["title", "artist", "album"]);
    await expect(start).toBeDisabled();
    expect(ui.sent.map((raw) => JSON.parse(raw)).some((msg) => msg.cmd === "configure")).toBe(
      false,
    );
  });
}

for (const language of ["fr", "en"] as const) {
  for (const incomplete of [false, true]) {
    test(`zero and incomplete results stay honest and offer another game (${language}, ${incomplete})`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: 1093, height: 600 });
      const base = hostView();
      const ui = await harness(page, base);
      const copy = language === "fr" ? fr : en;
      if (language === "en")
        await page.getByRole("button", { name: "English", exact: true }).click();
      const rows = standings.map((row) => ({
        ...row,
        score: incomplete && row.rank === 1 ? 5 : 0,
        rank: incomplete ? row.rank : 1,
      }));
      const now = await page.evaluate(() => performance.now());
      ui.show({
        ...base,
        phase: "FINAL_RESULTS",
        standings: rows,
        final_results: {
          standings: rows,
          podium: rows,
          rounds_played: 2,
          final_adjustments: [],
          recap: [],
          finished_at: 60,
          podium_started_at: now + 800,
          unreviewed_answers: incomplete ? 2 : 0,
        },
        host: { ...base.host, commands: ["new_game", "end_session"] },
      });
      await expect(
        page.getByRole("heading", {
          name: copy[incomplete ? "polish.incompleteTitle" : "experience.noAwardTitle"],
          exact: true,
        }),
      ).toBeVisible();
      await expect(page.locator(".celebration-sparks, .podium-first")).toHaveCount(0);
      await expect(page.locator(".podium-announcement")).toHaveCount(1);
      if (incomplete)
        await expect(page.locator(".podium-announcement")).toContainText(
          copy["polish.incompleteResults"].replace("{count}", "2"),
        );
      await expect(page.locator(".end-actions")).toBeVisible();
      const actions = await page.locator(".end-actions").boundingBox();
      const details = await page
        .getByRole("heading", { name: copy["results.title"], exact: true })
        .boundingBox();
      expect(actions).not.toBeNull();
      expect(details).not.toBeNull();
      expect((actions?.y ?? Infinity) + (actions?.height ?? 0)).toBeLessThan(details?.y ?? 0);
      for (const button of await page.locator(".end-actions > .btn").all()) {
        expect((await button.boundingBox())?.height).toBeLessThan(100);
      }
      await layout(page);
    });
  }
}

test("fresh host start unlocks audio under native gesture policy", async ({
  browserName,
}, info) => {
  test.skip(browserName !== "chromium", "Chromium native gesture policy");
  const nativeBrowser = await chromium.launch({
    ...(info.project.use.channel ? { channel: info.project.use.channel } : {}),
    args: ["--autoplay-policy=document-user-activation-required"],
  });
  const context = await nativeBrowser.newContext({
    baseURL: String(info.project.use.baseURL),
    locale: "fr-FR",
  });
  try {
    const page = await context.newPage();
    await page.addInitScript(() => {
      const Original = window.AudioContext;
      const contexts: AudioContext[] = [];
      Object.assign(window, { startAudioProbe: contexts });
      window.AudioContext = class extends Original {
        constructor(options?: AudioContextOptions) {
          super(options);
          contexts.push(this);
        }
      };
    });
    const { view, library } = manualFixture();
    const ui = await harness(page, view, library);
    await page.getByRole("button", { name: fr["flow.prepare"], exact: true }).click();
    const dialog = page.getByRole("dialog", { name: fr["flow.prepare"], exact: true });
    await dialog.getByRole("tab", { name: fr["flow.rhythm"], exact: true }).click();
    await dialog.getByLabel(fr["hostui.rounds"], { exact: true }).fill("1");
    await dialog.getByRole("button", { name: fr["ux.saveAndStart"], exact: true }).click();
    await expect
      .poll(() =>
        ui.sent
          .map((raw) => JSON.parse(raw))
          .some((msg) => msg.cmd === "configure" && msg.start_game),
      )
      .toBe(true);
    expect(
      await page.evaluate(() =>
        (window as unknown as { startAudioProbe: AudioContext[] }).startAudioProbe.map(
          (ctx) => ctx.state,
        ),
      ),
    ).toEqual(["running"]);
  } finally {
    await context.close();
    await nativeBrowser.close();
  }
});

test("finale activity changes language without repeating a score update", async ({ page }) => {
  const base = playerView();
  const ui = await harness(page, base);
  const source = globalReview(hostView(), []);
  if (!source.finale) throw new Error("Finale fixture");
  const initial = {
    ...base,
    phase: "FINAL_SCORE_REVIEW" as const,
    finale: { ...source.finale, round: null, revealed_round_ids: [] },
  };
  ui.show(initial);
  await expect(page.locator(".finale-activity")).toContainText(fr["experience.publicWaiting"]);
  ui.show({ ...initial, finale: source.finale });
  await expect(page.locator(".finale-activity")).toContainText(
    fr["experience.roundActivity"].replace("{number}", "1"),
  );
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(page.locator(".finale-activity")).toContainText(
    en["experience.roundActivity"].replace("{number}", "1"),
  );
  await expect(page.locator(".score-updated")).toHaveCount(0);
});

for (const language of ["fr", "en"] as const) {
  test(`library opens on tracks and clears every filter (${language})`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    const { library, track } = manualFixture();
    await harness(page, hostView(), library);
    const copy = language === "fr" ? fr : en;
    if (language === "en") await page.getByRole("button", { name: "English", exact: true }).click();
    const queries: URLSearchParams[] = [];
    await page.route("**/api/host/library/search**", (route) => {
      queries.push(new URL(route.request().url()).searchParams);
      return route.fulfill({ json: { total: 1, tracks: [track], tags: [], linked_to: [] } });
    });
    await page.getByRole("button", { name: copy["library.manage"], exact: true }).click();
    const dialog = page.getByRole("dialog", { name: copy["library.manage"], exact: true });
    await expect(dialog.locator(".library-tracks > li")).toBeInViewport({ ratio: 0.5 });
    await expect(dialog.locator(".library-extra-filters")).not.toHaveAttribute("open", "");
    await dialog.locator(".library-extra-filters > summary").click();
    await dialog
      .getByRole("combobox", { name: copy["library.activation"], exact: true })
      .selectOption("disabled");
    await dialog
      .getByRole("combobox", { name: copy["library.type"], exact: true })
      .selectOption(".mp4");
    await dialog
      .getByRole("combobox", { name: copy["library.quality"], exact: true })
      .selectOption("missing");
    await dialog
      .getByRole("checkbox", { name: copy["library.selectedSources"], exact: true })
      .check();
    await dialog.getByLabel(copy["library.search"], { exact: true }).fill("test");
    await expect.poll(() => queries.at(-1)?.get("q")).toBe("test");
    await dialog.getByRole("button", { name: copy["theme.clear"], exact: true }).click();
    await expect
      .poll(() => Object.fromEntries(queries.at(-1) ?? []))
      .toMatchObject({
        q: "",
        bridge: "",
        folder: "",
        ext: "",
        availability: "all",
        activation: "all",
        quality: "all",
        pool_only: "false",
        tag: "",
        linked_to: "",
        genre: "",
        language: "",
        offset: "0",
      });
    await expect(dialog.locator(".library-extra-filters > summary")).toContainText("0");
  });
}
