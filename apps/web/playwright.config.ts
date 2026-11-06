import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";

// Two app instances: a healthy one, and one whose marketplace is unreachable (degraded-mode test).
// Both run fully offline (heuristic profile, stand-in GigSim) with throwaway databases.
const root = new URL("../..", import.meta.url).pathname;
const tmp = process.env.E2E_TMP ?? "/tmp/gigbid-e2e";
const reviewer = { REVIEWER_EMAIL: "e2e-reviewer@example.test", REVIEWER_PASSWORD: "e2e-only-password" };
const common = { GIGBID_PROFILE: "offline", GIGSIM_ERROR_RATE: "0", GIGBID_SCHEDULER: "0", ...reviewer };
const chromium = "/opt/pw-browsers/chromium";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 90_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: "http://127.0.0.1:8190",
    trace: "off",
    // CI installs its own browser; in environments with a pre-installed Chromium, use that one.
    launchOptions: existsSync(chromium) ? { executablePath: chromium } : {},
  },
  webServer: [
    {
      command: `rm -rf ${tmp}/ok && mkdir -p ${tmp}/ok && ${root}scripts/run_all.sh`,
      cwd: root,
      url: "http://127.0.0.1:8190/healthz",
      timeout: 120_000,
      reuseExistingServer: false,
      env: { ...common, PORT: "8190", GIGSIM_PORT: "8191", DATABASE_URL: `sqlite:///${tmp}/ok/gigbid.db`, GIGSIM_STATE: `${tmp}/ok/gigsim.json` },
    },
    {
      command: `rm -rf ${tmp}/down && mkdir -p ${tmp}/down && ${root}scripts/run_all.sh`,
      cwd: root,
      url: "http://127.0.0.1:8192/healthz",
      timeout: 120_000,
      reuseExistingServer: false,
      // GigSim is started on 8193 but the API is pointed at a closed port: the marketplace is "down".
      env: { ...common, PORT: "8192", GIGSIM_PORT: "8193", GIGSIM_URL: "http://127.0.0.1:8199", DATABASE_URL: `sqlite:///${tmp}/down/gigbid.db`, GIGSIM_STATE: `${tmp}/down/gigsim.json` },
    },
  ],
});
