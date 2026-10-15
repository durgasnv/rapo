import { defineConfig } from "@playwright/test";

const origin = process.env.RAPO_HOSTED_URL;
if (process.env.RAPO_HOSTED_TESTS !== "1" || !origin) {
  throw new Error(
    "Set RAPO_HOSTED_TESTS=1 and RAPO_HOSTED_URL to run live smoke tests.",
  );
}
const url = new URL(origin);
if (url.protocol !== "https:" || url.origin !== origin) {
  throw new Error(
    "RAPO_HOSTED_URL must be an HTTPS origin without credentials or a path.",
  );
}
if (
  !process.env.RAPO_SMOKE_ORGANIZER_EMAIL ||
  !process.env.RAPO_SMOKE_ORGANIZER_PASSWORD
) {
  throw new Error(
    "Set the dedicated smoke organizer credentials in the local environment.",
  );
}

export default defineConfig({
  testDir: "./tests/hosted",
  workers: 1,
  retries: 0,
  timeout: 4_800_000,
  use: {
    baseURL: origin,
    // Real accounts and cookies must not be recorded in test artifacts.
    trace: "off",
    screenshot: "off",
    video: "off",
  },
});
