// Full game through the real interface (spec §20.3): one host in Player Mode and two
// players in separate browser contexts, the demo Bridge, two rounds, up to FINAL_RESULTS.
import {
  type Browser,
  expect,
  type Locator,
  type Page,
  type TestInfo,
  test,
} from "@playwright/test";

const BLIND = "example-e2e-blind";
const HOST = "example-e2e-host";

// Reset the disposable local room through its existing protocol, even after a failed run.
// This keeps retries isolated (notably the existing nightly WebKit investigation).
async function resetRoom(page: Page): Promise<void> {
  const origin = new URL(String(test.info().project.use.baseURL)).origin;
  const joined = await page.request.post("/api/session/join", {
    headers: { Origin: origin },
    data: { password: BLIND, nickname: `ExampleReset${Date.now().toString(36)}` },
  });
  if (joined.status() === 409) expect(await joined.json()).toEqual({ error: "already_joined" });
  else expect(joined.ok()).toBe(true);
  const elevated = await page.request.post("/api/session/host", {
    headers: { Origin: origin },
    data: { host_password: HOST },
  });
  expect(elevated.ok()).toBe(true);
  await endTestSession(page);
}
test.beforeEach(async ({ page, browserName }) => {
  if (browserName === "webkit") {
    await page.goto("/");
    test.skip(
      await page.evaluate(() => typeof AudioContext === "undefined"),
      "This WebKit build has no Web Audio support; verify full games on Safari separately.",
    );
  }
  await resetRoom(page);
});
test.afterEach(async ({ page }) => {
  if (test.info().status !== "skipped") await resetRoom(page);
});

// Anything that would spoil a round before REVEALED (demo library names, catalogue keys).
const SPOILERS = [
  "relpath",
  "track_id",
  "elapsed_ms",
  '"folder"',
  "filename",
  "sine-",
  "melodie-",
  "clics-",
  "Sinus",
  "Mélodie",
  "Clics",
  "OpenBlindySir Demo",
];
const TIME = /\d+,\d s/; // an answer time as displayed (French typography)

type Seat = { page: Page; frames: string[]; sent: string[] };

async function seat(
  browser: Browser,
  nickname: string,
  host = false,
  viewport = { width: 1280, height: 960 },
): Promise<Seat> {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const frames: string[] = [];
  const sent: string[] = [];
  page.on("websocket", (ws) => {
    ws.on("framereceived", (frame) => frames.push(String(frame.payload)));
    ws.on("framesent", (frame) => sent.push(String(frame.payload)));
  });
  await page.goto("/");
  await page.getByLabel("Mot de passe de la partie").fill(BLIND);
  await page.getByLabel("Pseudo").fill(nickname);
  await page.getByRole("button", { name: "Entrer" }).click();
  // Navigation can cancel the join fetch before WebKit installs the session cookie.
  await expect(page.getByRole("button", { name: "Tester mon audio", exact: true })).toBeVisible();
  if (host) {
    await page.goto("/host");
    await page.getByLabel("Mot de passe hôte").fill(HOST);
    await page.getByRole("button", { name: "Devenir hôte" }).click();
  }
  await unlockAudio(page);
  await page.getByRole("button", { name: "Je l'entends ✓" }).click();
  await expect(page.getByText("✓ Son prêt")).toBeVisible();
  return { page, frames, sent };
}

async function unlockAudio(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Tester mon audio", exact: true }).click();
  await expect(page.locator(".audio-gate")).toHaveCount(0);
}

async function checkLayout(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
}

async function capture(page: Page, info: TestInfo, name: string): Promise<void> {
  await checkLayout(page);
  await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true });
}

async function answer(page: Page, text: string): Promise<void> {
  await page.getByLabel("Ta réponse").fill(text);
  await page.getByRole("button", { name: "VALIDER" }).click();
  await expect(
    page
      .getByText("✓ Réponse enregistrée")
      .or(page.getByText(`Ta réponse : ${text}`, { exact: true }))
      .or(page.locator(".review").getByText(text, { exact: true }))
      .or(page.getByRole("heading", { name: "REVUE DE FIN DE PARTIE", exact: true })),
  ).toBeVisible();
}

function reviewRow(host: Page, name: string): Locator {
  return host.locator("table.review tr", { hasText: name });
}

async function score(host: Page, name: string, points: number): Promise<void> {
  const row = reviewRow(host, name);
  if (points === 2) await row.getByRole("button", { name: "Tout bon", exact: true }).click();
  else {
    const input = row.getByRole("textbox");
    await input.fill(String(points));
    await input.press("Enter");
  }
  await expect(row.locator(".review-status")).toHaveText("✓ Vérifiée");
  await expect(row.getByRole("textbox")).toHaveValue(String(points));
  await expect(row.getByRole("textbox")).toBeEnabled();
}

async function prepare(page: Page, tab: string): Promise<void> {
  if (!(await page.getByRole("dialog", { name: "Préparer la partie", exact: true }).isVisible()))
    await page.getByRole("button", { name: "Préparer la partie", exact: true }).click();
  await page.getByRole("tab", { name: tab, exact: true }).click();
}

function framesSince(s: Seat, from: number): string {
  return s.frames.slice(from).join("\n");
}

async function playRound(host: Seat, alice: Seat, bob: Seat, n: number): Promise<void> {
  const start = { alice: alice.frames.length, bob: bob.frames.length };
  await expect(alice.page.getByText(`MANCHE ${n} / 2`)).toBeVisible({ timeout: 90_000 });
  await expect(alice.page.getByLabel("Ta réponse")).toBeVisible({ timeout: 90_000 });

  // VALIDER: confirmation without any time; the anonymous counter n/m for the others.
  await answer(alice.page, `rep-A-${n}`);
  // Catch-up audio can legitimately display seconds. Only answer timings are private.
  await expect(alice.page.locator(".answer-saved")).not.toContainText(TIME);
  await expect(alice.page.locator(".answer-time")).toHaveCount(0);
  const counter = bob.page.getByText("1/3 ont validé");
  await expect(counter).toBeVisible();
  await expect(counter).not.toContainText("Alice");

  if (n === 1) {
    await host.page.getByRole("button", { name: "Mettre en pause", exact: true }).click();
    await expect(bob.page.locator(".answer-deadline")).toContainText("Manche en pause");
    await expect(bob.page.getByLabel("Ta réponse", { exact: true })).toBeDisabled();
    await bob.page.waitForTimeout(700);
    await expect(bob.page.locator(".answer-deadline")).toContainText(
      "Son et temps de réponse suspendus",
    );
    await host.page.getByRole("button", { name: "Reprendre la manche", exact: true }).click();
    await expect(bob.page.getByLabel("Ta réponse", { exact: true })).toBeEnabled();
  }

  if (n === 2) {
    // Reconnection: Bob's draft survives a reload (same session cookie, same identity).
    await bob.page.getByLabel("Ta réponse").fill(`rep-B-${n}`);
    await bob.page.waitForTimeout(800); // the draft is sent after 500 ms of inactivity
    await bob.page.reload();
    await unlockAudio(bob.page);
    await expect(bob.page.getByLabel("Ta réponse")).toHaveValue(`rep-B-${n}`);
    await bob.page.getByRole("button", { name: "VALIDER" }).click();
    await expect(bob.page.getByText("✓ Réponse enregistrée")).toBeVisible();
  } else {
    await answer(bob.page, `rep-B-${n}`);
  }
  await answer(host.page, `rep-H-${n}`);

  // Closed rounds preserve each player's own answer; all scoring waits for global review.
  if (n === 1) {
    await expect(alice.page.getByText("Réponses conservées.")).toBeVisible({ timeout: 60_000 });
    await expect(alice.page.getByText(`Ta réponse : rep-A-${n}`)).toBeVisible();
  } else
    await expect(alice.page.getByText("L'hôte vérifie les scores…")).toBeVisible({
      timeout: 60_000,
    });
  for (const other of [`rep-B-${n}`, `rep-H-${n}`])
    await expect(alice.page.locator("body")).not.toContainText(other);
  await expect(alice.page.locator(".answer-time")).toHaveCount(0);

  // Nothing in the WebSocket traffic of a player spoils the round before REVEALED.
  for (const [s, from, others] of [
    [alice, start.alice, [`rep-B-${n}`, `rep-H-${n}`]],
    [bob, start.bob, [`rep-A-${n}`, `rep-H-${n}`]],
  ] as const) {
    const traffic = framesSince(s, from);
    for (const word of [...SPOILERS, ...others]) {
      expect(traffic, word).not.toContain(word);
    }
  }

  // Audio pipeline without any acoustic check: downloaded, decoded (READY), scheduled and
  // reported (PLAYBACK_REPORT) by each browser.
  for (const s of [alice, bob, host]) {
    const sent = s.sent.map((raw) => JSON.parse(raw) as { t: string; state?: string });
    expect(sent.some((m) => m.t === "AUDIO_STATUS" && m.state === "READY")).toBe(true);
    const reports = sent.filter((m) => m.t === "PLAYBACK_REPORT") as { late_ms?: number }[];
    expect(reports.length).toBeGreaterThanOrEqual(n);
    expect(reports.every((r) => (r.late_ms ?? 0) < 60_000)).toBe(true);
  }
}

for (const viewport of [
  { width: 1280, height: 960 },
  { width: 320, height: 780 },
]) {
  test(`a full game through the interface (${viewport.width}px)`, async ({ browser }, info) => {
    const host = await seat(browser, "Hote", true, viewport);
    const alice = await seat(browser, "Alice", false, viewport);
    const bob = await seat(browser, "Bob", false, viewport);
    await capture(alice.page, info, "player-lobby");
    await capture(host.page, info, "host-lobby");

    // Lobby: a second tab supersedes the first, which can take the session back.
    await expect(alice.page.getByText("Joueurs (3)")).toBeVisible();
    const tab = await bob.page.context().newPage();
    await tab.goto("/");
    await expect(bob.page.getByText("Ouvert ailleurs — reprendre ici")).toBeVisible();
    await tab.close();
    await bob.page.getByRole("button", { name: "Reprendre ici" }).click();
    await expect(bob.page.getByText("Joueurs (3)")).toBeVisible();

    // Setup through the host drawer: the demo library, 2 rounds of short clips.
    const h = host.page;
    await prepare(h, "Musique");
    await expect(
      h.locator(".setup").getByText("✓ Bibliothèque connectée", { exact: true }),
    ).toBeVisible({
      timeout: 90_000,
    });
    await h.locator(".tree input[type=checkbox]").first().check();
    await prepare(h, "Rythme");
    await h.getByLabel("Nombre de manches").fill("2");
    await h.getByLabel("Durée des extraits (s)").fill("8");
    const grace = h.getByLabel("Temps pour répondre après l’extrait (s)");
    await grace.fill((await grace.inputValue()) === "20" ? "21" : "20");
    await expect(h.getByRole("button", { name: "Enregistrer et lancer" })).toBeEnabled();
    await h.getByRole("button", { name: "Enregistrer", exact: true }).click();
    const startButton = h.getByRole("button", { name: "Lancer la partie" });
    await expect(startButton).toBeEnabled();
    await startButton.click();
    await expect(alice.page.locator(".countdown")).toBeVisible({ timeout: 90_000 });

    await playRound(host, alice, bob, 1);
    await capture(alice.page, info, "player-reveal");
    await expect(h.getByRole("dialog")).toHaveCount(0); // No mandatory host menu between rounds.
    await playRound(host, alice, bob, 2);
    await expect(
      h.getByRole("heading", { name: "REVUE DE FIN DE PARTIE", exact: true }),
    ).toBeVisible();
    const replayRequests: string[] = [];
    h.on("request", (request) => {
      if (request.url().includes("/api/host/review/") && request.url().includes("/audio"))
        replayRequests.push(request.url());
    });
    const playerPlays = alice.frames.filter((raw) => JSON.parse(raw).t === "PLAY").length;
    const privatePlayer = h.getByRole("region", { name: "Réécoute privée" });
    expect(replayRequests).toHaveLength(0);
    await privatePlayer.getByRole("button", { name: "Écouter", exact: true }).click();
    await expect(privatePlayer.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
    await privatePlayer.getByRole("button", { name: "Pause", exact: true }).click();
    await privatePlayer.getByRole("button", { name: "Écouter le morceau complet" }).click();
    await expect(privatePlayer.getByText("Morceau complet", { exact: true })).toBeVisible();
    await expect(privatePlayer.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
    await privatePlayer.getByRole("button", { name: "Revenir à l’extrait" }).click();
    await expect(privatePlayer.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
    await privatePlayer.getByRole("button", { name: "Pause", exact: true }).click();
    expect(replayRequests.some((url) => new URL(url).searchParams.get("mode") === "full")).toBe(
      true,
    );
    expect(alice.frames.filter((raw) => JSON.parse(raw).t === "PLAY")).toHaveLength(playerPlays);
    await expect(privatePlayer.getByRole("alert")).toHaveCount(0);
    for (const [number, points] of [
      [1, { Alice: 2, Bob: 1, Hote: 0 }],
      [2, { Alice: 1, Bob: 0, Hote: 3 }],
    ] as const) {
      await h
        .locator(".review-navigation")
        .getByRole("button", { name: new RegExp(`^${number}\\.`) })
        .click();
      for (const [name, value] of Object.entries(points)) {
        if (value) await score(h, name, value);
        else {
          const zero = reviewRow(h, name).getByRole("button", { name: "Tout faux", exact: true });
          await zero.click();
          await expect(reviewRow(h, name).locator(".review-status")).toHaveText("✓ Vérifiée");
        }
      }
    }

    // Final review: Bob +2, the host corrects themself −1; players never see the draft.
    const review = h.locator(".final-review");
    const bobRow = review.locator(".final-table tr", { hasText: "Bob" });
    const hostRow = review.locator(".final-table tr", { hasText: "Hote" });
    await bobRow.getByRole("button", { name: "Ajouter un point à Bob", exact: true }).click();
    await expect(bobRow).toContainText("1 → +1 → 2");
    await bobRow.getByRole("button", { name: "Ajouter un point à Bob", exact: true }).click();
    await expect(bobRow).toContainText("1 → +2 → 3");
    await hostRow.getByRole("button", { name: "Retirer un point à Hote", exact: true }).click();
    await expect(hostRow).toContainText("3 → −1 → 2");
    await expect(alice.page.getByText("L'hôte vérifie les scores…")).toBeVisible();
    await expect(alice.page.locator(".standings")).toHaveCount(0);
    await expect(alice.page.locator("body")).not.toContainText("+2");
    await capture(h, info, "host-final-review");
    await capture(alice.page, info, "player-final-waiting");
    await h.getByRole("button", { name: "VALIDER LES SCORES ET AFFICHER LES RÉSULTATS" }).click();
    await expect(h.getByRole("dialog")).toContainText("2 Corrections finales");
    await h.getByRole("button", { name: "Confirmer" }).click();

    // Results: podium, scores and the final adjustments, for everybody.
    for (const s of [alice, bob, host]) {
      const page = s.page;
      await expect(page.getByRole("heading", { name: "Résultats" })).toBeVisible();
      const podium = page.locator(".podium");
      await expect(podium.locator("li", { hasText: "Alice" })).toContainText("3 pts");
      await expect(podium.locator("li", { hasText: "Alice" }).locator(".podium-rank")).toHaveText(
        "1.",
      );
      await expect(podium.locator("li", { hasText: "Bob" })).toContainText("3 pts");
      await expect(podium.locator("li", { hasText: "Bob" }).locator(".podium-rank")).toHaveText(
        "1.",
      );
      await expect(podium.locator("li", { hasText: "Hote" })).toContainText("2 pts");
      await expect(podium.locator("li", { hasText: "Hote" }).locator(".podium-rank")).toHaveText(
        "3.",
      );
      await expect(page.getByText("2 manches jouées", { exact: true })).toBeVisible();
      await expect(page.getByText("ajustement final : Bob +2")).toBeVisible();
      await expect(page.getByText("ajustement final : Hote −1")).toBeVisible();
    }
    await capture(alice.page, info, "player-results");

    // End of session: everybody is sent back to the join screen (and the next run starts clean).
    await h.getByRole("button", { name: "Fin de session" }).click();
    await h.getByRole("button", { name: "Confirmer" }).click();
    for (const s of [alice, bob]) {
      await expect(s.page.getByRole("heading", { name: "Rejoindre la partie" })).toBeVisible();
    }
    // The old elevation must not survive a new session on /host.
    await h.getByLabel("Pseudo", { exact: true }).fill("Hote");
    await h.getByLabel("Mot de passe de la partie").fill(BLIND);
    await h.getByRole("button", { name: "Entrer", exact: true }).click();
    await expect(h.getByRole("heading", { name: "Accès hôte" })).toBeVisible();
    await h.getByLabel("Mot de passe hôte").fill(HOST);
    await h.getByRole("button", { name: "Devenir hôte" }).click();
    await h.getByRole("button", { name: "Tester mon audio", exact: true }).click();
    // Dispose this last session through the existing host command in the test harness.
    await endTestSession(h);
    for (const s of [host, alice, bob]) await s.page.context().close();
  });
}

test("an MC hosts a round with a captured draft and starts another game", async ({
  browser,
}, info) => {
  const viewport = { width: 390, height: 850 };
  const host = await seat(browser, "ExampleMC", true, viewport);
  const alice = await seat(browser, "ExampleAlice", false, viewport);
  const bob = await seat(browser, "ExampleBob", false, viewport);
  const h = host.page;
  await openModeOptions(h);
  await h.getByRole("button", { name: "Passer en mode animateur" }).click();
  await expect(h.getByText("Animateur", { exact: true })).toBeVisible();
  await prepare(h, "Musique");
  await expect(
    h.locator(".setup").getByText("✓ Bibliothèque connectée", { exact: true }),
  ).toBeVisible();
  await h.locator(".tree input[type=checkbox]").first().check();
  await prepare(h, "Rythme");
  await h.getByLabel("Nombre de manches").fill("1");
  await h.getByLabel("Durée des extraits (s)").fill("8");
  await h.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(h.getByRole("button", { name: "Lancer la partie" })).toBeEnabled();
  await h.getByRole("button", { name: "Lancer la partie" }).click();
  await expect(h.getByRole("heading", { name: "La manche est en cours." })).toBeVisible({
    timeout: 90_000,
  });
  await expect(h.getByLabel("Ta réponse", { exact: true })).toHaveCount(0);
  await expect(h.locator(".mc-panel")).toContainText("OpenBlindySir Demo");
  await expect(alice.page.locator(".answer-progress")).toHaveCount(0); // only two competitors
  await bob.page.getByLabel("Ta réponse", { exact: true }).fill("example-captured-draft");
  await bob.page.waitForTimeout(800);
  await answer(alice.page, "example-mc-answer");
  await expect(h.locator(".mc-progress")).toContainText("✓ Réponse validée");
  await expect(bob.page.getByText("Extrait terminé", { exact: true })).toBeVisible();
  await expect(bob.page.getByLabel("Ta réponse", { exact: true })).toBeEnabled();
  await capture(h, info, "host-mc-open");
  await h.getByRole("button", { name: "Paramètres", exact: true }).click();
  await h.getByRole("button", { name: "Fermer les réponses" }).click();
  await expect(reviewRow(h, "ExampleBob")).toContainText("Brouillon capturé · non validé");
  await expect(reviewRow(h, "ExampleBob")).toContainText("example-captured-draft");
  await expect(bob.page.getByText("L'hôte vérifie les scores…")).toBeVisible();
  await expect(alice.page.locator("body")).not.toContainText("example-captured-draft");
  await score(h, "ExampleAlice", 2);
  await score(h, "ExampleBob", 1);
  await capture(h, info, "host-mc-review");
  await expect(bob.page.locator("body")).not.toContainText("example-mc-answer");
  await h.getByRole("button", { name: "VALIDER LES SCORES ET AFFICHER LES RÉSULTATS" }).click();
  await h.getByRole("button", { name: "Confirmer", exact: true }).click();
  await expect(alice.page.getByRole("heading", { name: "Résultats", exact: true })).toBeVisible();
  await bob.page.locator(".recap summary").filter({ hasText: "ExampleBob" }).click();
  await expect(bob.page.locator(".recap details").filter({ hasText: "ExampleBob" })).toContainText(
    "example-captured-draft",
  );
  await h
    .getByRole("button", { name: "Nouvelle partie avec les morceaux restants", exact: true })
    .click();
  await expect(h.getByRole("heading", { name: "Tout le monde s’installe." })).toBeVisible();
  await expect(
    alice.page.getByRole("heading", { name: "Tout le monde s’installe." }),
  ).toBeVisible();
  await openModeOptions(h);
  await h.getByRole("button", { name: "Passer en mode joueur" }).click();
  await expect(h.getByText("Hôte joueur", { exact: true })).toBeVisible();
  await endTestSession(h);
  for (const s of [host, alice, bob]) await s.page.context().close();
});

async function openModeOptions(page: Page): Promise<void> {
  await prepare(page, "Avancé");
  if ((await page.locator(".mode-options").getAttribute("open")) === null) {
    await page.getByText("Changer de rôle", { exact: true }).click();
  }
}

async function endTestSession(page: Page): Promise<void> {
  // Stop the application's socket before opening the harness socket. Otherwise
  // they can supersede each other and a close can be mistaken for a room reset.
  await page.goto("/healthz");
  await page.evaluate(async () => {
    const ws = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/ws`,
    );
    await new Promise<void>((resolve, reject) => {
      ws.onopen = () =>
        ws.send(JSON.stringify({ t: "HELLO", client_version: "0.3.0", protocol: 6 }));
      ws.onmessage = (event) => {
        const msg = JSON.parse(String(event.data));
        if (msg.t === "ERROR") reject(new Error(`Room reset failed: ${msg.code}`));
        if (msg.t === "STATE")
          ws.send(
            JSON.stringify({
              t: "HOST",
              cmd: "end_session",
              expected_phase: msg.view.phase,
              args: {},
            }),
          );
      };
      ws.onclose = (event) => {
        if (event.code === 4004)
          resolve(); // SESSION_ENDED
        else reject(new Error(`Unexpected room reset close: ${event.code}`));
      };
    });
  });
  expect((await page.request.get("/api/session")).status()).toBe(401);
}
