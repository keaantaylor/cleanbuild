import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { defineConfig } from "@playwright/test";

// End-to-end: the real API (embedded worker, throwaway SQLite or the
// Postgres given in E2E_DATABASE_URL) behind the production build of the
// frontend, wired exactly as on Vercel: the browser calls /api/v1 on the
// frontend origin and next.config.ts rewrites it to the API.
// Run `npm run build` first with NEXT_PUBLIC_API_URL=/api/v1 and
// TRUEBIND_API_ORIGIN=http://127.0.0.1:<E2E_API_PORT> (scripts/verify.py does this).
const API_PORT = Number(process.env.E2E_API_PORT ?? 8765);
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 3100);
const PYTHON = process.env.TRUEBIND_PYTHON ?? "python";
const dataDir = mkdtempSync(path.join(tmpdir(), "truebind-e2e-"));
const backendDir = path.resolve(__dirname, "../backend");

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 240_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {},
    trace: "retain-on-failure",
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
        DATABASE_URL: process.env.E2E_DATABASE_URL ?? `sqlite:///${path.join(dataDir, "e2e.db")}`,
        TRUEBIND_DATA_DIR: path.join(dataDir, "data"),
        TRUEBIND_STORAGE_DIR: path.join(dataDir, "objects"),
        // P2 channels, test-only values: no public DNS in the test environment.
        INBOUND_EMAIL_DOMAIN: "in.e2e.example",
        INBOUND_WEBHOOK_SECRET: "e2e-inbound-secret", // gitleaks:allow -- dummy value for the local e2e server
        WEBHOOK_ALLOW_PRIVATE_TARGETS: "1",
      },
    },
    {
      command: `npx next start --port ${WEB_PORT}`,
      url: `http://localhost:${WEB_PORT}/login`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: { TRUEBIND_API_ORIGIN: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
