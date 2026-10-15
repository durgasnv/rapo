import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

const databaseUrl = process.env.RAPO_DATABASE_URL;
if (!databaseUrl || !new URL(databaseUrl).pathname.endsWith("_test")) {
  throw new Error(
    "Browser tests require RAPO_DATABASE_URL pointing to a dedicated database ending in _test.",
  );
}

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  timeout: 120_000,
  retries: process.env.CI ? 2 : 0,
  use: { baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  webServer: [
    {
      command:
        "uv run uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000",
      env: {
        // All reset emails stay in the loopback test mailbox, even if real mail vars are inherited.
        RAPO_AUTH_RATE_LIMIT: "1000",
        RAPO_SMTP_HOST: "127.0.0.1",
        RAPO_SMTP_PORT: "8026",
        RAPO_SMTP_SECURITY: "starttls",
        RAPO_SMTP_USERNAME: "test-sender",
        RAPO_SMTP_PASSWORD: "synthetic-mail-password",
        RAPO_SMTP_SENDER: "sender@example.com",
        RAPO_RESET_FRONTEND_URL: "http://127.0.0.1:3000",
        SSL_CERT_FILE: join(tmpdir(), "rapo-playwright-smtp-cert.pem"),
      },
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: false,
      timeout: 180_000,
      env: {
        NEXT_PUBLIC_API_URL: "http://127.0.0.1:8000",
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});
