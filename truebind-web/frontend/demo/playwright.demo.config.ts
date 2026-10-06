import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { defineConfig } from "@playwright/test";

// Product demo recording. Runs the real API (throwaway SQLite, embedded worker)
// behind the production build of the frontend, exactly like the e2e suite, so
// what is filmed is the real application with synthetic data only.
// Build first:  NEXT_PUBLIC_API_URL=/api/v1 TRUEBIND_API_ORIGIN=http://127.0.0.1:8766 npm run build
const API_PORT = Number(process.env.DEMO_API_PORT ?? 8766);
const WEB_PORT = Number(process.env.DEMO_WEB_PORT ?? 3200);
const PYTHON = process.env.TRUEBIND_PYTHON ?? "python";
const dataDir = mkdtempSync(path.join(tmpdir(), "truebind-demo-"));
const backendDir = path.resolve(__dirname, "../../backend");

export default defineConfig({
  testDir: ".",
  testMatch: "record-demo.spec.ts",
  timeout: 600_000,
  expect: { timeout: 60_000 },
  workers: 1,
  reporter: [["list"]],
  outputDir: "output/playwright",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    colorScheme: "light",
    locale: "en-GB",
    timezoneId: "Europe/Dublin",
    video: { mode: "on", size: { width: 1920, height: 1080 } },
    launchOptions: {
      ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {}),
      args: ["--hide-scrollbars", "--disable-extensions", "--force-color-profile=srgb", "--font-render-hinting=none"],
    },
  },
  webServer: [
    {
      command: `"${PYTHON}" -m alembic upgrade head && "${PYTHON}" -m uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: backendDir,
      url: `http://127.0.0.1:${API_PORT}/health/ready`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        TRUEBIND_ENV: "test",
        TRUEBIND_NO_DOTENV: "1",
        TRUEBIND_EMBEDDED_WORKER: "1",
        ALLOW_SIGNUP: "1",
        SIGNUP_LIMIT_PER_HOUR: "50",
        ANTHROPIC_API_KEY: "", // mapping by alias rules only: deterministic, nothing sent anywhere
        DATABASE_URL: `sqlite:///${path.join(dataDir, "demo.db")}`,
        TRUEBIND_DATA_DIR: path.join(dataDir, "data"),
        TRUEBIND_STORAGE_DIR: path.join(dataDir, "objects"),
        // pyshim/sitecustomize.py: a neutral worker name, so no host name reaches the audit trail on camera.
        PYTHONPATH: [path.resolve(__dirname, "pyshim"), process.env.PYTHONPATH ?? ""].filter(Boolean).join(path.delimiter),
      },
    },
    {
      command: `npx next start --port ${WEB_PORT}`,
      cwd: path.resolve(__dirname, ".."),
      url: `http://localhost:${WEB_PORT}/login`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: { TRUEBIND_API_ORIGIN: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
