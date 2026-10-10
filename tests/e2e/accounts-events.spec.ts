import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

const password = "a-long-browser-test-passphrase";

test("account survives reload and can sign out and sign in", async ({
  page,
}) => {
  const email = `participant-${randomUUID()}@example.com`;
  await page.goto("/sign-up");
  await page.getByLabel("Your name").fill("Community member");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Hello, Community member." }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Hello, Community member." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your account", exact: true }),
  ).toBeVisible();
  await page.goto("/sign-in");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Hello, Community member." }),
  ).toBeVisible();
  await page.goto("/organizer");
  await expect(
    page.getByText("Organizer access is required.", { exact: false }),
  ).toBeVisible();
});

test("organizer creates, edits, publishes and cancels a discoverable event", async ({
  page,
  playwright,
}) => {
  const email = `organizer-${randomUUID()}@example.com`;
  const title = `Workshop ${randomUUID()}`;
  await page.goto("/sign-up");
  await page.getByLabel("Your name").fill("Organizer");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Hello, Organizer." }),
  ).toBeVisible();
  execFileSync("uv", ["run", "python", "-m", "app.cli", email], {
    env: { ...process.env, PYTHONPATH: "apps/api" },
  });
  await page.reload();
  await page.getByRole("link", { name: "Manage events", exact: true }).click();
  await page.getByRole("link", { name: "Create event", exact: true }).click();
  await page.getByLabel("Event title", { exact: true }).fill(title);
  await page
    .getByLabel("Description", { exact: true })
    .fill("Build fresh connections together.");
  await page
    .getByLabel("Display timezone", { exact: false })
    .fill("Asia/Kolkata");
  const at = (days: number, hours = 0) =>
    new Date(Date.now() + (days * 24 + hours) * 3_600_000)
      .toISOString()
      .slice(0, 16);
  for (const [name, value] of Object.entries({
    start_at: at(10),
    end_at: at(10, 2),
    registration_opens_at: at(0),
    registration_closes_at: at(5),
    confirmation_deadline: at(9),
  }))
    await page.locator(`input[name="${name}"]`).fill(value);
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByText("DRAFT", { exact: true })).toBeVisible();
  const eventId = page.url().split("/").at(-1)!;
  const anonymous = await playwright.request.newContext({
    baseURL: "http://127.0.0.1:8000",
  });
  expect((await anonymous.get(`/events/${eventId}`)).status()).toBe(404);
  await page
    .getByLabel("Event title", { exact: true })
    .fill(`${title} updated`);
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Changes saved." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Publish event", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Your event is published." }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "View public event", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: `${title} updated`, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Asia/Kolkata", { exact: false }).first(),
  ).toBeVisible();
  expect((await anonymous.get(`/events/${eventId}`)).status()).toBe(200);
  await page.goto("/events");
  const pages = page.getByRole("navigation", { name: "Event pages" });
  const publishedHeading = page.getByRole("heading", {
    name: `${title} updated`,
    exact: true,
  });
  await expect(pages).toBeVisible();
  // Repeated runs retain events; discovery must work beyond the first results page.
  while (
    !(await publishedHeading.isVisible()) &&
    (await pages.getByRole("button", { name: "Next", exact: true }).isEnabled())
  ) {
    await pages.getByRole("button", { name: "Next", exact: true }).click();
    await expect(pages).toBeVisible();
  }
  await expect(publishedHeading).toBeVisible();
  await page.goto(`/organizer/events/${eventId}`);
  await page.getByRole("button", { name: "Cancel event", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Your event is cancelled." }),
  ).toBeVisible();
  expect((await anonymous.get(`/events/${eventId}`)).status()).toBe(404);
  await anonymous.dispose();
});
