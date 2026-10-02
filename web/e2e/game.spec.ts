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
  expect(joined.ok()).toBe(true);
  const elevated = await page.request.post("/api/session/host", {
    headers: { Origin: origin },
    data: { host_password: HOST },
  });
  expect(elevated.ok()).toBe(true);
  await page.goto("/host");
  await endTestSession(page);
}
test.beforeEach(async ({ page }) => resetRoom(page));
test.afterEach(async ({ page }) => resetRoom(page));

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
  await expect(page.getByText("✓ Réponse enregistrée")).toBeVisible();
}

function reviewRow(host: Page, name: string): Locator {
  return host.locator("table.review tr", { hasText: name });
}

async function score(host: Page, name: string, points: number): Promise<void> {
  const button = reviewRow(host, name).getByRole("button", { name: `+${points}`, exact: true });
  await button.click();
  await expect(button).toHaveAttribute("aria-pressed", "true");
}

function framesSince(s: Seat, from: number): string {
  return s.frames.slice(from).join("\n");
}

async function playRound(
  host: Seat,
  alice: Seat,
  bob: Seat,
  n: number,
  points: Record<string, number>,
): Promise<void> {
  const start = { alice: alice.frames.length, bob: bob.frames.length };
  await expect(alice.page.getByText(`ROUND ${n} / 2`)).toBeVisible({ timeout: 90_000 });
  await expect(alice.page.getByLabel("Ta réponse")).toBeVisible({ timeout: 90_000 });

  // VALIDER: confirmation without any time; the anonymous counter n/m for the others.
  await answer(alice.page, `rep-A-${n}`);
  await expect(alice.page.locator("main")).not.toContainText(TIME);
  const counter = bob.page.getByText("1/3 ont validé");
  await expect(counter).toBeVisible();
  await expect(counter).not.toContainText("Alice");

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

  // REVIEW: the player sees only their own answer; the host sees every row and scores.
  await expect(alice.page.getByText("L'hôte note les réponses…")).toBeVisible({ timeout: 60_000 });
  await expect(alice.page.getByText(`Ta réponse : rep-A-${n}`)).toBeVisible();
  for (const other of [`rep-B-${n}`, `rep-H-${n}`]) {
    await expect(alice.page.locator("body")).not.toContainText(other);
  }
  await expect(alice.page.locator("main")).not.toContainText(TIME);
  for (const name of ["Alice", "Bob", "Hote"]) {
    await expect(reviewRow(host.page, name)).toContainText(TIME);
  }
  for (const [name, pts] of Object.entries(points)) {
    await score(host.page, name, pts);
  }

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

  await host.page.getByRole("button", { name: "Publier" }).click();
  // Reveal: everybody sees the track, every answer, the times and the points.
  for (const s of [alice, bob]) {
    await expect(s.page.getByText("C'était…")).toBeVisible();
    for (const text of [`rep-A-${n}`, `rep-B-${n}`, `rep-H-${n}`]) {
      await expect(s.page.locator("table")).toContainText(text);
    }
    await expect(s.page.locator("table")).toContainText(TIME);
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
    await expect(h.locator(".setup").getByText("✓ Bibliothèque connectée")).toBeVisible({
      timeout: 90_000,
    });
    await h.locator(".tree input[type=checkbox]").first().check();
    await h.getByLabel("Nombre de rounds").fill("2");
    await h.getByLabel("Durée des extraits (s)").fill("8");
    await h.getByText("Réglages avancés", { exact: true }).click();
    const grace = h.getByLabel("Délai de grâce (s)");
    await grace.fill((await grace.inputValue()) === "20" ? "21" : "20");
    await expect(h.getByRole("button", { name: "Lancer la partie" })).toBeDisabled();
    await h.getByRole("button", { name: "Enregistrer" }).click();
    const startButton = h.getByRole("button", { name: "Lancer la partie" });
    await expect(startButton).toBeEnabled();
    await startButton.click();
    await expect(alice.page.locator(".countdown")).toBeVisible({ timeout: 90_000 });

    await playRound(host, alice, bob, 1, { Alice: 2, Bob: 1 });
    await capture(alice.page, info, "player-reveal");
    await h.getByRole("button", { name: "Suivant" }).click();
    await playRound(host, alice, bob, 2, { Alice: 1, Hote: 3 });
    await h.getByRole("button", { name: "Vérification finale" }).click();

    // Final review: Bob +2, the host corrects themself −1; players never see the draft.
    const review = h.locator(".final-review");
    const bobRow = review.locator("tr", { hasText: "Bob" });
    const hostRow = review.locator("tr", { hasText: "Hote" });
    await bobRow.getByRole("button", { name: "Ajouter un point à Bob", exact: true }).click();
    await expect(bobRow).toContainText("1 → +1 → 2");
    await bobRow.getByRole("button", { name: "Ajouter un point à Bob", exact: true }).click();
    await expect(bobRow).toContainText("1 → +2 → 3");
    await hostRow.getByRole("button", { name: "Retirer un point à Hote", exact: true }).click();
    await expect(hostRow).toContainText("3 → −1 → 2");
    await expect(alice.page.getByText("L'hôte vérifie les scores…")).toBeVisible();
    await expect(alice.page.locator(".standing-list li", { hasText: "Bob" })).toContainText(
      "1 pts",
    );
    await expect(alice.page.locator("body")).not.toContainText("+2");
    await capture(h, info, "host-final-review");
    await capture(alice.page, info, "player-final-waiting");
    await h.getByRole("button", { name: "VALIDER LES SCORES ET AFFICHER LES RÉSULTATS" }).click();
    await expect(h.getByText("2 corrections")).toBeVisible();
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
      await expect(page.getByText("2 rounds joués")).toBeVisible();
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
  await expect(h.getByText("Animateur (MC)", { exact: true })).toBeVisible();
  await expect(h.locator(".setup").getByText("✓ Bibliothèque connectée")).toBeVisible();
  await h.locator(".tree input[type=checkbox]").first().check();
  await h.getByLabel("Nombre de rounds").fill("1");
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
  await h.getByRole("button", { name: "Fermer les réponses" }).click();
  await expect(reviewRow(h, "ExampleBob")).toContainText("(non validée)");
  await expect(reviewRow(h, "ExampleBob")).toContainText("example-captured-draft");
  await expect(bob.page.getByText("(non validée)")).toBeVisible();
  await expect(alice.page.locator("body")).not.toContainText("example-captured-draft");
  await score(h, "ExampleAlice", 2);
  await score(h, "ExampleBob", 1);
  await capture(h, info, "host-mc-review");
  await h.getByRole("button", { name: "Publier", exact: true }).click();
  await expect(bob.page.locator("table")).toContainText("example-captured-draft");
  await h.getByRole("button", { name: "Vérification finale", exact: true }).click();
  await h.getByRole("button", { name: "VALIDER LES SCORES ET AFFICHER LES RÉSULTATS" }).click();
  await h.getByRole("button", { name: "Confirmer", exact: true }).click();
  await expect(alice.page.getByRole("heading", { name: "Résultats", exact: true })).toBeVisible();
  await h.getByRole("button", { name: "Nouvelle partie", exact: true }).click();
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
  if ((await page.locator(".mode-options").getAttribute("open")) === null) {
    await page.getByText("Changer de rôle", { exact: true }).click();
  }
}

async function endTestSession(page: Page): Promise<void> {
  await page.evaluate(async () => {
    const ws = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/ws`,
    );
    await new Promise<void>((resolve) => {
      ws.onopen = () =>
        ws.send(JSON.stringify({ t: "HELLO", client_version: "0.1.0", protocol: 1 }));
      ws.onmessage = (event) => {
        const msg = JSON.parse(String(event.data));
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
      ws.onclose = () => resolve();
    });
  });
}
