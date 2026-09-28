import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Unit tests for pure frontend logic (formatters, finding guides, stage
// mapping, contrast). Browser flows live in tests/e2e (Playwright).
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: {
    include: ["tests/unit/**/*.test.ts"],
    environment: "node",
    coverage: { provider: "v8", include: ["lib/**/*.ts"], reporter: ["text-summary", "json-summary"] },
  },
});
