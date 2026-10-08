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
import type { LibraryTrack } from "../src/protocol";

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
  if (host) {
    // Ending a session deliberately retains host settings. Each standard game
    // must select its own rules after a preceding automatic-scoring scenario.
    await prepare(page, "Règles");
    const mode = page.getByRole("combobox", { name: "Réponse attendue", exact: true });
    const scoring = page.getByRole("combobox", { name: "Attribution des points", exact: true });
    const changed =
      (await mode.inputValue()) !== "both" || (await scoring.inputValue()) !== "manual";
    await mode.selectOption("both");
    await scoring.selectOption("manual");
    const save = page.getByRole("button", { name: "Enregistrer", exact: true });
    if (changed) {
      await expect(save).toBeEnabled();
      await save.click();
      await expect(page.locator(".setup").getByText("✓ Enregistré", { exact: true })).toBeVisible();
    }
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "Préparer la partie", exact: true })).toHaveCount(
      0,
    );
  }
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
      .or(page.locator(".closed-round").getByText(text, { exact: true }))
      .or(page.getByRole("heading", { name: "Le grand final", exact: true })),
  ).toBeVisible();
}

function reviewRow(host: Page, name: string): Locator {
  return host.locator(".answer-card, .absent-answer", { hasText: name });
}

async function score(host: Page, name: string, points: number): Promise<void> {
  const row = reviewRow(host, name);
  await row.locator(".manual-score > summary").click();
  if (points === 2 && (await row.getByRole("button", { name: "Tout bon", exact: true }).count()))
    await row.getByRole("button", { name: "Tout bon", exact: true }).click();
  else {
    const input = row.getByRole("textbox");
    await input.fill(String(points));
    await input.press("Enter");
  }
  await expect(row.locator(".review-status, .absence-award small")).toHaveText("✓ Vérifiée");
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
  await expect(alice.page.locator(".header .round-number")).toHaveText(`MANCHE ${n} / 2`, {
    timeout: 90_000,
  });
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
    await expect(alice.page.getByRole("heading", { name: "Les réponses sont closes" })).toBeVisible(
      { timeout: 60_000 },
    );
    await expect(alice.page.locator(".closed-round .own-answer")).toHaveText(`rep-A-${n}`);
  } else
    await expect(alice.page.getByText("Le grand final")).toBeVisible({
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
    await expect(h.getByRole("heading", { name: "Le grand final", exact: true })).toBeVisible();
    const replayRequests: string[] = [];
    h.on("request", (request) => {
      if (request.url().includes("/api/host/review/") && request.url().includes("/audio"))
        replayRequests.push(request.url());
    });
    const playerPlays = alice.frames.filter((raw) => JSON.parse(raw).t === "PLAY").length;
    const privatePlayer = h.getByRole("region", { name: "Réécoute privée" });
    await h.locator(".track-options > summary").click();
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
      await h.getByLabel("Choisir une manche à présenter").selectOption({ index: number - 1 });
      await h.getByRole("button", { name: `Présenter la manche ${number}`, exact: true }).click();
      await expect(alice.page.locator(".finale-track .eyebrow")).toContainText(`Manche ${number}`);
      if (number === 1) {
        await h.getByRole("button", { name: "Réécouter ensemble", exact: true }).click();
        await expect
          .poll(() => alice.frames.filter((raw) => JSON.parse(raw).t === "PLAY").length)
          .toBe(playerPlays + 1);
        await expect(
          h.getByRole("button", { name: "Arrêter la réécoute", exact: true }),
        ).toBeVisible();
        await expect(alice.page.locator(".finale-track .record")).toHaveClass(/record-playing/);
        await h.getByRole("button", { name: "Arrêter la réécoute", exact: true }).click();
        await expect(alice.page.locator(".finale-track .record")).not.toHaveClass(/record-playing/);
      } else {
        // No host command should be needed to restore the private player after natural expiry.
        await h.getByRole("button", { name: "Réécouter ensemble", exact: true }).click();
        await expect(privatePlayer).toHaveCount(0);
        await expect(privatePlayer).toBeVisible({ timeout: 20_000 });
        await expect(alice.page.locator(".finale-track .record")).not.toHaveClass(/record-playing/);
      }
      for (const [name, value] of Object.entries(points)) {
        if (value) await score(h, name, value);
        else {
          const zero = reviewRow(h, name).getByRole("button", {
            name: /^(Tout faux|Confirmer 0 point)$/,
            exact: true,
          });
          await zero.click();
          await expect(
            reviewRow(h, name).locator(".review-status, .absence-award small"),
          ).toHaveText("✓ Vérifiée");
        }
      }
    }

    // Final review: Bob +2 and host −1 update the shared provisional leaderboard.
    const review = h.locator(".final-review");
    await h.locator(".finale-adjustments > summary").click();
    const bobRow = review.locator(".final-table tr", { hasText: "Bob" });
    const hostRow = review.locator(".final-table tr", { hasText: "Hote" });
    await bobRow.getByRole("button", { name: "Ajouter un point à Bob", exact: true }).click();
    await expect(bobRow).toContainText("1 → +1 → 2");
    await bobRow.getByRole("button", { name: "Ajouter un point à Bob", exact: true }).click();
    await expect(bobRow).toContainText("1 → +2 → 3");
    await hostRow.getByRole("button", { name: "Retirer un point à Hote", exact: true }).click();
    await expect(hostRow).toContainText("3 → −1 → 2");
    await expect(alice.page.getByText("Le grand final")).toBeVisible();
    await expect(alice.page.locator(".standings")).toHaveCount(0);
    await expect(
      alice.page.locator(".live-standings").first().getByText("Bob", { exact: true }).locator(".."),
    ).toContainText("3");
    await capture(h, info, "host-final-review");
    await capture(alice.page, info, "player-final-waiting");
    await h.getByRole("button", { name: "Lancer le podium" }).click();
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
  await expect(bob.page.getByText("Le grand final")).toBeVisible();
  await expect(alice.page.locator("body")).not.toContainText("example-captured-draft");
  await score(h, "ExampleAlice", 2);
  await score(h, "ExampleBob", 1);
  await capture(h, info, "host-mc-review");
  await expect(bob.page.locator("body")).not.toContainText("example-mc-answer");
  await h.getByRole("button", { name: "Présenter la manche 1", exact: true }).click();
  await expect(bob.page.locator(".finale-answers")).toContainText("example-mc-answer");
  await h.getByRole("button", { name: "Lancer le podium" }).click();
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
        ws.send(JSON.stringify({ t: "HELLO", client_version: "0.3.0", protocol: 12 }));
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

test("real QR join, cookie resume, approved device transfer, private preview and immediate finish", async ({
  browser,
}) => {
  const host = await seat(browser, "QR Host", true);
  const h = host.page;
  const accessResponse = await h.request.get("/api/host/session/access");
  expect(accessResponse.ok()).toBe(true);
  const access = (await accessResponse.json()) as { invitation: string; code: string };
  const first = await browser.newContext();
  const replacement = await browser.newContext();
  try {
    const alice = await first.newPage();
    await alice.goto(`/#join=${encodeURIComponent(access.invitation)}`);
    await expect(alice.getByLabel("Mot de passe de la partie", { exact: true })).toHaveCount(0);
    await alice.getByLabel("Pseudo", { exact: true }).fill("QR Alice");
    await alice.getByRole("button", { name: "Entrer", exact: true }).click();
    await expect(
      alice.getByRole("heading", { name: "Tout le monde s’installe.", exact: true }),
    ).toBeVisible();
    const identity = (await (await alice.request.get("/api/session")).json()).player_id;
    await alice.reload();
    await expect(
      alice.getByRole("heading", { name: "Tout le monde s’installe.", exact: true }),
    ).toBeVisible();
    expect((await (await alice.request.get("/api/session")).json()).player_id).toBe(identity);
    const resumed = await replacement.newPage();
    await resumed.goto(`/#join=${encodeURIComponent(access.invitation)}`);
    await resumed.getByLabel("Pseudo", { exact: true }).fill("QR Alice");
    await resumed.getByRole("button", { name: "Entrer", exact: true }).click();
    await expect(resumed.getByRole("status")).toContainText("L’hôte doit confirmer");
    await h.getByRole("button", { name: "Autoriser la reprise de QR Alice", exact: true }).click();
    await expect(
      resumed.getByRole("heading", { name: "Tout le monde s’installe.", exact: true }),
    ).toBeVisible();
    expect((await (await resumed.request.get("/api/session")).json()).player_id).toBe(identity);
    expect((await alice.request.get("/api/session")).status()).toBe(401);
    await unlockAudio(resumed);
    await resumed.getByRole("button", { name: "Je l'entends ✓", exact: true }).click();
    await h
      .getByRole("button", { name: "Sources et recherche de bibliothèque", exact: true })
      .click();
    const library = h.getByRole("dialog", {
      name: "Sources et recherche de bibliothèque",
      exact: true,
    });
    const card = library.locator(".library-tracks > li").first();
    await expect(card).toBeVisible({ timeout: 90000 });
    await card
      .getByRole("button", { name: "Préécouter 15 s · milieu du morceau", exact: true })
      .click();
    await expect(
      card.getByRole("button", { name: "Arrêter la préécoute", exact: true }),
    ).toBeVisible();
    await expect
      .poll(() => card.locator("audio").evaluate((el) => !(el as HTMLAudioElement).paused))
      .toBe(true);
    await card.getByRole("button", { name: "Arrêter la préécoute", exact: true }).click();
    await expect
      .poll(() => card.locator("audio").evaluate((el) => (el as HTMLAudioElement).paused))
      .toBe(true);
    expect(host.frames.some((raw) => JSON.parse(raw).t === "PLAY")).toBe(false);
    await h.keyboard.press("Escape");
    await prepare(h, "Musique");
    await expect(
      h.locator(".setup").getByText("✓ Bibliothèque connectée", { exact: true }),
    ).toBeVisible({ timeout: 90000 });
    await h.locator(".tree input[type=checkbox]").first().check();
    await prepare(h, "Rythme");
    await h.getByLabel("Nombre de manches", { exact: true }).fill("3");
    await h.getByRole("button", { name: "Enregistrer et lancer", exact: true }).click();
    await expect(resumed.getByLabel("Ta réponse", { exact: true })).toBeEnabled({ timeout: 90000 });
    await answer(resumed, "Answer preserved on early finish");
    await h.getByRole("button", { name: "Paramètres", exact: true }).click();
    await h.getByRole("button", { name: "Arrêter la partie", exact: true }).click();
    await h
      .getByRole("button", { name: "Terminer avec les points déjà attribués", exact: true })
      .click();
    await expect(
      h.getByRole("button", { name: "Nouvelle partie avec les morceaux restants", exact: true }),
    ).toBeVisible();
    await expect(h.getByRole("button", { name: "Fin de session", exact: true })).toBeVisible();
    await expect(resumed.getByRole("heading", { name: "Résultats", exact: true })).toBeVisible();
    const final = host.frames
      .filter((raw) => JSON.parse(raw).t === "STATE")
      .map((raw) => JSON.parse(raw).view)
      .at(-1);
    expect(final.phase).toBe("FINAL_RESULTS");
    expect(final.final_results.podium_started_at).toBeNull();
    expect(JSON.stringify(final.final_results.recap)).toContain("Answer preserved on early finish");
  } finally {
    await first.close();
    await replacement.close();
    await host.page.context().close();
  }
});

test("real automatic scoring accepts the flexible multi-detail answer and reveals points in the finale", async ({
  browser,
}, info) => {
  const host = await seat(browser, "AutoHost", true);
  const alice = await seat(browser, "AutoAlice", false, { width: 390, height: 844 });
  const h = host.page;
  let originals: LibraryTrack[] = [];
  try {
    await prepare(h, "Musique");
    await expect(
      h.locator(".setup").getByText("✓ Bibliothèque connectée", { exact: true }),
    ).toBeVisible({ timeout: 90000 });
    const search = await h.request.get("/api/host/library/search?limit=20");
    expect(search.ok()).toBe(true);
    const library = (await search.json()) as { tracks: LibraryTrack[] };
    originals = library.tracks;
    expect(library.tracks.length).toBeGreaterThan(0);
    const origin = new URL(h.url()).origin;
    for (const track of library.tracks) {
      const edited = await h.request.put("/api/host/metadata", {
        headers: { Origin: origin },
        data: {
          bridge_id: track.bridge_id,
          track_id: track.track_id,
          metadata: {
            title: "Sapés comme jamais",
            artist: "Maître Gims",
            album: "Pilule bleue",
            year: 2015,
            featuring: "Niska",
          },
        },
      });
      expect(edited.ok()).toBe(true);
    }
    await h.locator(".tree input[type=checkbox]").first().check();
    await prepare(h, "Règles");
    await h.getByRole("combobox", { name: "Réponse attendue", exact: true }).selectOption("fields");
    await h.getByRole("checkbox", { name: "Album", exact: true }).check();
    await h.getByRole("checkbox", { name: "Année", exact: true }).check();
    await h
      .getByRole("combobox", { name: "Attribution des points", exact: true })
      .selectOption("auto");
    await prepare(h, "Rythme");
    await h.getByLabel("Nombre de manches").fill("1");
    await h.getByLabel("Durée des extraits (s)").fill("5");
    await h.getByLabel("Temps pour répondre après l’extrait (s)").fill("3");
    await h.getByRole("button", { name: "Enregistrer", exact: true }).click();
    await expect(h.getByRole("button", { name: "Lancer la partie", exact: true })).toBeEnabled();
    await h.getByRole("button", { name: "Lancer la partie", exact: true }).click();
    const input = alice.page.getByLabel("Ta réponse", { exact: true });
    await expect(input).toBeVisible({ timeout: 90000 });
    await expect(input).toHaveAttribute("maxlength", "1000");
    await expect(alice.page.locator(".answer-form input")).toHaveCount(1);
    const from = alice.frames.length;
    await answer(alice.page, "Sapéscomme Ja m ais Maitre Gims 2015 ft niska   pilule bleue");
    await expect(h.getByRole("heading", { name: "Le grand final", exact: true })).toBeVisible();
    const privateFrames = alice.frames.slice(from).map((raw) => JSON.parse(raw));
    expect(
      privateFrames
        .filter((message) => message.t === "ANSWER_ACK")
        .every((message) => !("points" in message)),
    ).toBe(true);
    expect(privateFrames.some((message) => JSON.stringify(message).includes("auto_evidence"))).toBe(
      false,
    );
    const before = privateFrames.filter((message) => message.t === "STATE").at(-1)?.view;
    expect(before.finale.standings.every((row: { score: number }) => row.score === 0)).toBe(true);
    await expect(reviewRow(h, "AutoAlice").locator(".review-status")).toHaveText("✓ Vérifiée");
    await h.getByRole("button", { name: "Présenter la manche 1", exact: true }).click();
    await expect(alice.page.getByText("Place aux points !", { exact: true })).toBeVisible();
    await expect(alice.page.locator(".my-finale-score > strong")).toContainText("4");
    await expect(alice.page.locator(".matched-criteria")).toContainText("Album");
    await capture(alice.page, info, "automatic-player-finale");
    await score(h, "AutoAlice", 6);
    await expect(alice.page.locator(".my-finale-score > strong")).toContainText("6");
    await h.getByRole("button", { name: "Lancer le podium", exact: true }).click();
    await h.getByRole("button", { name: "Confirmer", exact: true }).click();
    await expect(alice.page.getByRole("heading", { name: "Résultats", exact: true })).toBeVisible();
  } finally {
    // Metadata survives session resets too; restore the synthetic references.
    const origin = new URL(h.url()).origin;
    for (const track of originals) {
      const restored = await h.request.put("/api/host/metadata", {
        headers: { Origin: origin },
        data: {
          bridge_id: track.bridge_id,
          track_id: track.track_id,
          metadata: {
            title: track.title,
            artist: track.artist,
            featuring: track.featuring,
            album: track.album,
            year: track.year,
            tags: track.tags,
            linked_to: track.linked_to,
            aliases: track.aliases,
            enabled: track.enabled,
            cleared_fields: track.cleared_fields,
          },
        },
      });
      expect(restored.ok()).toBe(true);
    }
    await Promise.all([host.page.context().close(), alice.page.context().close()]);
  }
});
