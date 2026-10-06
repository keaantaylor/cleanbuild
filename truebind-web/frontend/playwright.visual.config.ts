import { defineConfig } from "@playwright/test";

// Visual review: screenshots at 1440 and 390 into docs/design/review/<session>/.
// Runs against an app that is already up (dev.ps1, or `npm run dev` + the API on :8000).
//   npx playwright test -c playwright.visual.config.ts tests/visual/session-0.spec.ts
export default defineConfig({
  testDir: "tests/visual",
  timeout: 90_000,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.VISUAL_BASE_URL ?? "http://localhost:3000",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {},
  },
});
