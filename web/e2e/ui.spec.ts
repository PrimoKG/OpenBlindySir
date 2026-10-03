// Deterministic UI states supplement the real-game tests; no server/game rule is mocked
// into production. These fixtures contain synthetic names and answers only.

import { Buffer } from "node:buffer";
import { expect, type Page, type Route, test, type WebSocketRoute } from "@playwright/test";
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

function playerView(): PlayerView {
  return {
    kind: "player",
    session: {
      epoch: "example-epoch",
      protocol: 6,
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
  await page.getByRole("combobox", { name: "Langue", exact: true }).selectOption("en");
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
      start_blockers: [],
      review_rounds: [
        {
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
    version: 2,
    game_id: "g_history1",
    finished_at: 1780000000000,
    started_at: 1779990000000,
    settings: view.host.settings,
    sources: [{ bridge_id: "12345678-1234-1234-1234-123456789abc", name: "Ancienne source" }],
    players: [...players],
    teams: [],
    results: {
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
        version: 2,
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
            version: 2,
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
          protocol: 6,
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
          protocol: 6,
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
        protocol: 6,
        protocol_min: 6,
        protocol_max: 6,
        snapshot_format: 4,
        history_format: 2,
      },
    }),
  );
  h.error("protocol_mismatch");
  h.disconnect(1008);
  await expect(page.getByRole("heading", { name: "Version incompatible" })).toBeVisible();
  await expect(page.getByRole("status")).toContainText("6 à 6");
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
      custom_correct: null,
      score_revision: 0,
      points_draft: 0,
      reviewed: false,
      score_before: 4,
      received_at_wall_ms: null,
    })),
    {
      title: "Titre privé exemple",
      artist: "Artiste exemple",
      display_name: "Exemple",
      folder: "Exemple",
      featuring: null,
      album: null,
      year: null,
    },
  );
  ui.show(review);
  await expect(
    page.getByRole("heading", { name: "Titre privé exemple", exact: true }),
  ).toBeVisible();
  const input = page.getByLabel(`Points pour ${players[0].nickname}`, { exact: true });
  await input.fill("-");
  ui.show(review); // unrelated STATE must preserve incomplete local typing
  await expect(input).toHaveValue("-");
  expect(ui.sent.some((raw) => JSON.parse(raw).cmd === "score_draft")).toBe(false);
  await expect(
    page.getByRole("button", { name: "VALIDER LES SCORES ET AFFICHER LES RÉSULTATS", exact: true }),
  ).toBeDisabled();
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
                custom_correct: null,
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
  await page
    .getByRole("button", { name: "VALIDER LES SCORES ET AFFICHER LES RÉSULTATS", exact: true })
    .click();
  const dialog = page.getByRole("dialog").last();
  await expect(dialog).toContainText("2 réponses restent à vérifier");
  await dialog.getByRole("button", { name: "Confirmer", exact: true }).click();
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
  const increase = panel.getByRole("button", {
    name: `Ajouter un point à ${players[0].nickname}`,
  });
  const input = panel.getByLabel(`Correction pour ${players[0].nickname}`, { exact: true });
  const validate = panel.getByRole("button", {
    name: "VALIDER LES SCORES ET AFFICHER LES RÉSULTATS",
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
        custom_correct: null,
        score_revision: 0,
        points_draft: 0,
        reviewed: false,
        score_before: 0,
        received_at_wall_ms: null,
      },
    ]),
  );
  await page.locator("table.review").getByRole("button", { name: "Tout bon", exact: true }).click();
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
    display_name: "Source",
    folder: "Test",
    featuring: null,
    album: null,
    year: null,
  });
  ui.show(review);
  await page.getByRole("button", { name: "Corriger les informations du morceau" }).click();
  const editor = page.locator(".metadata-editor");
  await editor.getByLabel("Titre", { exact: true }).fill("");
  await editor.getByRole("button", { name: "Enregistrer", exact: true }).click();
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
  await expect(editor.getByLabel("Titre", { exact: true })).toHaveValue("Titre importé");
  await expect(editor.getByRole("button", { name: "Enregistrer", exact: true })).toBeEnabled();
  await expect(editor.getByRole("status")).toContainText("Enregistré");
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
  await expect(page.getByRole("combobox", { name: "Bridge", exact: true })).toBeFocused();
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
    await expect(
      page.getByText("Tu peux modifier ta réponse. Valider la rend définitive."),
    ).toBeVisible();
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
    await expect(page.getByRole("heading", { name: "Réponses conservées." })).toBeVisible();
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
    ui.show({ ...base, phase: "FINAL_SCORE_REVIEW", standings });
    await expect(page.getByRole("heading", { name: "L'hôte vérifie les scores…" })).toBeVisible();
    await layout(page);
    ui.show({
      ...base,
      phase: "FINAL_RESULTS",
      standings,
      final_results: {
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
      custom_correct: null,
      score_revision: 0,
      points_draft: 0,
      reviewed: false,
      score_before: 0,
      received_at_wall_ms: null,
    }));
    ui.show(globalReview(base, answers));
    await expect(page.getByRole("heading", { name: "À toi de noter." })).toBeVisible();
    await expect(page.locator(".review")).toContainText("⚠ audio +2,3 s");
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
                custom_correct: null,
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
      host: {
        ...base.host,
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
    await expect(
      page.getByRole("heading", { name: "REVUE DE FIN DE PARTIE", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "VALIDER LES SCORES ET AFFICHER LES RÉSULTATS" })
      .click();
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
        name: "VALIDER LES SCORES ET AFFICHER LES RÉSULTATS",
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

test("recovery has one primary action and submits code plus game password", async ({ page }) => {
  await page.route("**/api/session", (route) =>
    route.fulfill({ status: 401, json: { error: "unauthenticated" } }),
  );
  let submitted: { code: string; password: string } | undefined;
  await page.route("**/api/session/recover", (route) => {
    submitted = route.request().postDataJSON();
    return route.fulfill({ status: 401, json: { error: "recovery_invalid" } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Retrouver ma place", exact: true }).click();
  await expect(page.getByRole("button", { name: "Entrer", exact: true })).toHaveCount(1);
  await expect(page.getByLabel("Pseudo", { exact: true })).toHaveCount(0);
  await page.getByLabel("Code de récupération", { exact: true }).fill("ab2xyz");
  await page.getByLabel("Mot de passe de la partie", { exact: true }).fill("example-recovery");
  await page.getByRole("button", { name: "Entrer", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Mot de passe ou code de récupération incorrect.",
  );
  expect(submitted).toEqual({ code: "AB2XYZ", password: "example-recovery" });
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
    custom_correct: null,
    score_revision: 0,
  };
  const review = globalReview(
    {
      ...base,
      rules: {
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
  await title.getByRole("button", { name: "Vrai", exact: true }).click();
  await expect(artist.getByRole("button", { name: "Faux", exact: true })).toBeDisabled();
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
  await expect(artist.getByRole("button", { name: "Faux", exact: true })).toBeEnabled();
  await expect(page.locator(".review-status")).toHaveText("À vérifier");
  await artist.getByRole("button", { name: "Faux", exact: true }).click();
  echo({ points_draft: 2, judgement: "criteria", title_correct: true, score_revision: 1 });
  await expect(artist.getByRole("button", { name: "Faux", exact: true })).toBeDisabled();
  echo({
    points_draft: 2,
    judgement: "criteria",
    title_correct: true,
    artist_correct: false,
    reviewed: true,
    score_revision: 2,
  });
  await expect(artist.getByRole("button", { name: "Faux", exact: true })).toHaveAttribute(
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
  const row = page.locator(".final-table tr", { hasText: players[0].nickname });
  const publish = page.getByRole("button", {
    name: "VALIDER LES SCORES ET AFFICHER LES RÉSULTATS",
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
  await expect.poll(() => requests.at(-1)?.get("offset")).toBe("25");
  await page.keyboard.press("Escape");
  await expect(opener).toBeFocused();
  await opener.click();
  await expect(dialog.getByRole("combobox", { name: "Trier par", exact: true })).toHaveValue(
    "artist",
  );
  await expect(dialog).toContainText("Page 2 sur 4");
  await expect.poll(() => requests.at(-1)?.get("limit")).toBe("25");
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
