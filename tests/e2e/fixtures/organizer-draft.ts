import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, type APIRequestContext, type Page } from "@playwright/test";

export async function draft(page: Page, api: APIRequestContext) {
  const email = `debug-owner-${randomUUID()}@example.com`;
  const signup = await api.post("http://127.0.0.1:8000/auth/register", {
    headers: { Origin: "http://127.0.0.1:3000" },
    data: {
      name: "Debug organizer",
      email,
      password: "a-long-browser-test-passphrase",
    },
  });
  expect(signup.status()).toBe(201);
  const account = await signup.json();
  execFileSync("uv", ["run", "python", "-m", "app.cli", email], {
    env: { ...process.env, PYTHONPATH: "apps/api" },
  });
  const response = await api.post("http://127.0.0.1:8000/events", {
    headers: {
      Origin: "http://127.0.0.1:3000",
      "X-CSRF-Token": account.csrf_token,
    },
    data: {
      title: "Schedule precision regression",
      description: "Preserve exact schedule times when editing event details.",
      timezone: "UTC",
      start_at: "2099-02-10T12:00:31.123456Z",
      end_at: "2099-02-10T14:00:00.000456Z",
      registration_opens_at: "2099-01-01T12:00:33.345678Z",
      registration_closes_at: "2099-02-01T12:00:34.456789Z",
      grouping_at: "2099-02-07T12:00:35.567891Z",
      confirmation_deadline: "2099-02-09T12:00:36.678912Z",
      min_team_size: 2,
      max_team_size: 3,
    },
  });
  expect(response.status()).toBe(201);
  await page.context().addCookies((await api.storageState()).cookies);
  return response.json();
}
