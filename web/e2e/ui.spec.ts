// Deterministic UI states supplement the real-game tests; no server/game rule is mocked
// into production. These fixtures contain synthetic names and answers only.
import { expect, type Page, test, type WebSocketRoute } from "@playwright/test";
import type { AnyView, HostView, LibraryResponse, PlayerView, StandingRow } from "../src/protocol";

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
      protocol: 2,
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
        prefetch_depth: 1,
        allow_repeats: false,
        answer_mode: "both",
        title_points: 1,
        artist_points: 1,
        instructions: "",
        captured_policy: "manual",
        normalize_audio: true,
        avoid_silence: true,
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
      warnings: [],
      history: [],
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

test("local score editing waits for acknowledgement and confirms unchecked answers", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 850 });
  const base = hostView();
  const ui = await harness(page, base);
  const review = {
    ...base,
    phase: "IN_GAME" as const,
    round: {
      state: "REVIEW" as const,
      round_id: roundId,
      number: 1,
      official_start_at: 1,
      ending: false,
      recovery_interrupted: false,
      track: {
        title: "Titre privé exemple",
        artist: "Artiste exemple",
        display_name: "Exemple",
        folder: "Exemple",
      },
      answers: players.map((p) => ({
        player_id: p.id,
        text: "Exemple",
        status: "LOCKED" as const,
        elapsed_ms: 1000,
        order: 1,
        near_tie: false,
        late_start_ms: 0,
        points_draft: 0,
        reviewed: false,
        score_before: 4,
      })),
    },
    host: {
      ...base.host,
      start_blockers: [],
      commands: ["score_draft", "publish", "track_metadata"],
    },
  };
  ui.show(review);
  await expect(
    page.getByRole("heading", { name: "Titre privé exemple", exact: true }),
  ).toBeVisible();
  const input = page.getByLabel(`Points pour ${players[0].nickname}`, { exact: true });
  await input.fill("-");
  ui.show(review); // unrelated STATE must preserve incomplete local typing
  await expect(input).toHaveValue("-");
  expect(ui.sent.some((raw) => JSON.parse(raw).cmd === "score_draft")).toBe(false);
  await expect(page.getByRole("button", { name: "Publier", exact: true })).toBeDisabled();
  await input.fill("12");
  await input.press("Enter");
  await expect(input).toBeDisabled();
  await expect.poll(() => ui.sent.some((raw) => JSON.parse(raw).args?.points === 12)).toBe(true);
  ui.show({
    ...review,
    round: {
      ...review.round,
      answers: review.round.answers.map((row, i) =>
        i === 0 ? { ...row, points_draft: 12, reviewed: true } : row,
      ),
    },
  });
  await expect(input).toBeEnabled();
  await expect(page.locator(".review")).toContainText("Total publié 4 · +12 cette manche → 16");
  await page.getByRole("button", { name: "Publier", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("2 réponses restent à vérifier");
  await dialog.getByRole("button", { name: "Confirmer", exact: true }).click();
  await expect
    .poll(() =>
      ui.sent.some(
        (raw) =>
          JSON.parse(raw).cmd === "publish" && JSON.parse(raw).args.confirm_unreviewed === true,
      ),
    )
    .toBe(true);
  await layout(page);
  await page.screenshot({ path: info.outputPath("review-ack.png"), fullPage: true });
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
      await page.getByText("Son", { exact: true }).click();
      const soundBox = await page.locator(".sound-popover").boundingBox();
      expect(soundBox?.x).toBeGreaterThanOrEqual(0);
      expect((soundBox?.x ?? 0) + (soundBox?.width ?? 0)).toBeLessThanOrEqual(width);
      await layout(page);
      await page.getByText("Son", { exact: true }).click();
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
        round_id: roundId,
        number: 1,
        my_answer: { status: "CAPTURED", text: "Exemple de réponse", draft_text: null },
      },
    });
    await expect(page.getByRole("heading", { name: "L'hôte note les réponses…" })).toBeVisible();
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
        final_adjustments: [{ player_id: players[1].id, delta: -1 }],
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
      points_draft: 0,
      reviewed: false,
      score_before: 0,
    }));
    ui.show({
      ...base,
      phase: "IN_GAME",
      round: {
        state: "REVIEW",
        round_id: roundId,
        number: 1,
        official_start_at: 1,
        answers,
        ending: false,
        track: null,
        recovery_interrupted: false,
      },
      host: {
        ...base.host,
        start_blockers: [],
        commands: ["score_draft", "publish", "adjust", "end_game", "set_mode"],
      },
    });
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
          draft_delta: -1,
          score_after: 2,
          history: [],
          adjustments: [],
        })),
      },
    });
    await expect(
      page.getByRole("heading", { name: "VÉRIFICATION FINALE DES SCORES", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "VALIDER LES SCORES ET AFFICHER LES RÉSULTATS" })
      .click();
    const dialog = page.getByRole("dialog", { name: "On confirme ?" });
    await expect(dialog).toContainText("3 correction(s)");
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
        per_player: players.slice(1).map((p, i) => ({ player_id: p.id, validated: i === 0 })),
      },
      host: { ...mc.host, start_blockers: [], commands: ["close", "add_time", "skip", "end_game"] },
    } as HostView);
    await expect(page.getByRole("heading", { name: "La manche est en cours." })).toBeVisible();
    await expect(page.getByText("Morceau visible au MC")).toBeVisible();
    await expect(page.getByLabel("Ta réponse", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Publier", exact: true })).toHaveCount(0);
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
  await page.route("**/api/host/library", (route) =>
    fail
      ? route.fulfill({ status: 503, json: { error: "network" } })
      : route.fulfill({ json: { bridges: [] } }),
  );
  // A new catalogue causes the existing UI to reload the folder tree.
  await page.reload();
  await expect(page.locator(".setup").getByRole("alert")).toContainText("Serveur injoignable");
  fail = false;
  await page.locator(".setup").getByRole("button", { name: "Réessayer" }).click();
  await expect(page.getByText("Aucun Bridge connecté")).toBeVisible();
  await page.route("**/api/host/diagnostics", (route) =>
    route.fulfill({ status: 503, json: { error: "network" } }),
  );
  await page.getByText("Diagnostic", { exact: true }).click();
  const diagnostics = page.locator("details", {
    has: page.getByText("Diagnostic", { exact: true }),
  });
  await expect(diagnostics.getByRole("alert")).toHaveText("Serveur injoignable");
  await page.route("**/api/host/diagnostics", (route) =>
    route.fulfill({ json: { example: true } }),
  );
  await diagnostics.getByRole("button", { name: "Réessayer" }).click();
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
