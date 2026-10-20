import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import type { EventData } from "../../apps/web/lib/api";

// A controlled catalog keeps UI tests independent of other tests' published events.
// PostgreSQL integration tests verify the real API's filtering and sort ordering.
async function catalog(page: Page, outage?: { unavailable: boolean }) {
  const events: EventData[] = Array.from({ length: 15 }, (_, index) => ({
    id: randomUUID(),
    organizer_id: randomUUID(),
    title: `Community event ${String(index + 1).padStart(2, "0")}`,
    description: "Meet your next collaborators.",
    location: "Community hall",
    timezone: "UTC",
    start_at: `2099-02-${String(index + 1).padStart(2, "0")}T12:00:00Z`,
    end_at: `2099-02-${String(index + 1).padStart(2, "0")}T14:00:00Z`,
    registration_opens_at: "2099-01-01T12:00:00Z",
    registration_closes_at: "2099-01-20T12:00:00Z",
    grouping_at: "2099-01-25T12:00:00Z",
    confirmation_deadline: "2099-01-30T12:00:00Z",
    capacity: 40,
    min_team_size: 3,
    max_team_size: 5,
    status: "PUBLISHED",
    version: 1,
  }));
  const requests: URL[] = [];
  await page.route("**/api/events?*", async (route) => {
    const url = new URL(route.request().url());
    requests.push(url);
    if (outage?.unavailable) {
      await route.fulfill({
        status: 503,
        json: { detail: "Event discovery is temporarily unavailable." },
      });
      return;
    }
    const offset = Number(url.searchParams.get("offset"));
    const empty =
      url.searchParams.has("status") || url.searchParams.has("date_from");
    await route.fulfill({
      json: {
        items: empty ? [] : events.slice(offset, offset + 12),
        total: empty ? 0 : events.length,
        limit: 12,
        offset,
      },
    });
  });
  return requests;
}

test("sign-up opens an event dashboard with optional filters and sorting across pages", async ({
  page,
}) => {
  const requests = await catalog(page);
  await page.goto("/sign-up");
  await page.getByLabel("Your name").fill("Dashboard member");
  await page
    .getByLabel("Email", { exact: true })
    .fill(`dashboard-${randomUUID()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("a-long-browser-test-passphrase");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page).toHaveURL(/\/dashboard$/);
  const events = page.getByRole("region", {
    name: "Community events",
    exact: true,
  });
  await expect(events.locator("article")).toHaveCount(12);
  await expect(events.getByLabel("Starts on or after (UTC)")).not.toBeVisible();
  await expect(
    page.getByRole("link", { name: "Dashboard", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Your registrations", exact: true }),
  ).toBeVisible();
  await events.getByRole("button", { name: "Next", exact: true }).click();
  await expect(events.locator("article")).toHaveCount(3);
  await events
    .getByRole("combobox", { name: "Sort", exact: true })
    .selectOption("latest");
  await expect(events.locator("article")).toHaveCount(12);
  expect(requests.at(-1)?.searchParams.get("sort")).toBe("latest");
  expect(requests.at(-1)?.searchParams.get("offset")).toBe("0");
  await events
    .getByRole("combobox", { name: "Sort", exact: true })
    .selectOption("title");
  await expect
    .poll(() => requests.at(-1)?.searchParams.get("sort"))
    .toBe("title");
  await expect(events.locator("article")).toHaveCount(12);
  await page.screenshot({
    path: "/tmp/rapo-dashboard-desktop.png",
    fullPage: true,
  });
});

test("filters validate dates, show empty results, clear, and fit a mobile viewport", async ({
  page,
}) => {
  const requests = await catalog(page);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/events");
  await expect(page.locator("article")).toHaveCount(12);
  await page
    .getByRole("combobox", { name: "Sort", exact: true })
    .selectOption("latest");
  await expect
    .poll(() => requests.at(-1)?.searchParams.get("sort"))
    .toBe("latest");
  await expect(page.locator("article")).toHaveCount(12);
  const toggle = page.locator("summary");
  await toggle.focus();
  await page.keyboard.press("Enter");
  const form = page.getByRole("form", { name: "Filter events", exact: true });
  await expect(form).toBeVisible();
  const bounds = await form.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(375);
  await page.screenshot({ path: "/tmp/rapo-dashboard-mobile.png" });
  await form.getByLabel("Starts on or after (UTC)").fill("2100-02-01");
  await form.getByLabel("Starts on or before (UTC)").fill("2100-01-01");
  await form.getByRole("button", { name: "Apply filters" }).click();
  await expect(form.getByRole("alert")).toContainText(
    "Start date must not be after end date",
  );
  await expect(page.locator("article")).toHaveCount(12);
  await form.getByLabel("Starts on or before (UTC)").fill("2100-03-01");
  await form.getByRole("button", { name: "Apply filters" }).click();
  await expect(
    page.getByRole("heading", { name: "No events here yet." }),
  ).toBeVisible();
  expect(requests.at(-1)?.searchParams.get("date_from")).toBe("2100-02-01");
  expect(requests.at(-1)?.searchParams.get("date_to")).toBe("2100-03-01");
  await toggle.click();
  await form.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.locator("article")).toHaveCount(12);
  expect(requests.at(-1)?.searchParams.has("date_from")).toBe(false);
  await expect(
    page.getByRole("combobox", { name: "Sort", exact: true }),
  ).toHaveValue("latest");
  await toggle.click();
  await expect(form.getByLabel("Starts on or after (UTC)")).toHaveValue("");
  await form.getByLabel("Event status").selectOption("GROUPS_PROPOSED");
  await form.getByRole("button", { name: "Apply filters" }).click();
  await expect(
    page.getByRole("heading", { name: "No events here yet." }),
  ).toBeVisible();
  expect(requests.at(-1)?.searchParams.get("status")).toBe("GROUPS_PROPOSED");
});

test("event discovery can retry a failed request", async ({ page }) => {
  // Strict Mode may replay the initial effect; keep the outage active until
  // the UI observes it instead of consuming it on a single request.
  const outage = { unavailable: true };
  await catalog(page, outage);
  await page.goto("/events");
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Event discovery is temporarily unavailable",
  );
  outage.unavailable = false;
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.locator("article")).toHaveCount(12);
});
