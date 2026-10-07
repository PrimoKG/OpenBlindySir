import { defineConfig, devices } from "@playwright/test";

// End-to-end tests (spec §20.3): real server serving web/dist, demo Bridge, real browsers.
// No acoustic check: headless browsers decode and schedule the clip into a muted output.
// Read without @types/node: the web package targets the browser only.
const env =
  (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const port = Number(env.E2E_PORT ?? 8765);

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: env.CI ? 1 : 0,
  reporter: env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${port}`,
    trace: "retain-on-failure",
    locale: "fr-FR",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: { args: ["--autoplay-policy=no-user-gesture-required"] },
      },
    },
    // CI and nightly regression coverage; Safari on iPhone still needs physical testing.
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
  webServer: {
    command: env.E2E_PYTHON
      ? `"${env.E2E_PYTHON}" ../tools/e2e_stack.py`
      : "uv run python ../tools/e2e_stack.py",
    url: `http://localhost:${port}/healthz`,
    reuseExistingServer: !env.CI,
    timeout: 120_000,
    env: { E2E_PORT: String(port) },
  },
});
