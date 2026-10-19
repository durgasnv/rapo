import { expect, test } from "@playwright/test";
import type { EventData } from "../../apps/web/lib/api";

test("event activity read recovery, pagination, and refresh after an event transition", async ({
  page,
}) => {
  const id = "2661382e-0649-41de-996b-2282029c49b7";
  const at = (days: number) =>
    new Date(Date.now() + days * 86400000).toISOString();
  let event: EventData = {
    id,
    organizer_id: "owner",
    title: "Audit browser workshop",
    description: "Activity history",
    location: "Main hall",
    timezone: "UTC",
    start_at: at(10),
    end_at: at(11),
    registration_opens_at: at(-2),
    registration_closes_at: at(5),
    grouping_at: at(7),
    confirmation_deadline: at(9),
    capacity: null,
    min_team_size: 2,
    max_team_size: 4,
    status: "DRAFT",
    version: 21,
  };
  const entries = Array.from({ length: 21 }, (_, i) => ({
    id: `entry-${i}`,
    action: i === 20 ? "event.created" : "event.updated",
    description: i === 20 ? "Event created" : "Event updated",
    actor_name: "Organizer",
    created_at: new Date(Date.now() - i * 1000).toISOString(),
  }));
  let fail = true;
  const unexpected: string[] = [];
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    url.pathname = url.pathname.slice("/api".length);
    if (url.pathname === "/me")
      return route.fulfill({
        json: {
          user: {
            id: "owner",
            name: "Organizer",
            email: "owner@example.com",
            role: "organizer",
          },
          csrf_token: "test-csrf",
        },
      });
    if (url.pathname === `/organizer/events/${id}`)
      return route.fulfill({ json: event });
    if (url.pathname === `/organizer/events/${id}/audit`) {
      if (fail)
        return route.fulfill({
          status: 503,
          json: { detail: "Activity temporarily unavailable" },
        });
      const offset = Number(url.searchParams.get("offset"));
      return route.fulfill({
        json: {
          items: entries.slice(offset, offset + 20),
          total: entries.length,
          offset,
          limit: 20,
        },
      });
    }
    if (url.pathname === `/events/${id}/publish`) {
      expect(route.request().method()).toBe("POST");
      expect(route.request().postDataJSON()).toEqual({ version: 21 });
      event = { ...event, version: 22, status: "PUBLISHED" };
      entries.unshift({
        id: "published-entry",
        action: "event.published",
        description: "Event published",
        actor_name: "Organizer",
        created_at: new Date().toISOString(),
      });
      return route.fulfill({ json: event });
    }
    if (url.pathname.endsWith("/grouping-runs/latest"))
      return route.fulfill({ json: null });
    if (url.pathname.endsWith("/grouping-job"))
      return route.fulfill({
        json: {
          status: "INACTIVE",
          attempts: 0,
          message: "No grouping job",
          next_attempt_at: null,
        },
      });
    if (url.pathname.endsWith("/registrations"))
      return route.fulfill({
        json: {
          items: [],
          total: 0,
          offset: 0,
          limit: 20,
          registered_count: 0,
          waitlisted_count: 0,
        },
      });
    unexpected.push(url.pathname);
    return route.fulfill({ status: 404 });
  });
  await page.goto(`/organizer/events/${id}`);
  const panel = page.getByRole("region", {
    name: "Event activity",
    exact: true,
  });
  await expect(panel.getByRole("alert")).toHaveText(
    "Activity temporarily unavailable",
  );
  await expect(
    page.getByRole("button", { name: "Publish event", exact: true }),
  ).toBeEnabled();
  fail = false;
  await panel
    .getByRole("button", { name: "Refresh activity", exact: true })
    .click();
  await expect(
    panel.getByText("21 recorded actions", { exact: true }),
  ).toBeVisible();
  await expect(panel.getByRole("listitem")).toHaveCount(20);
  await expect(panel.getByText("By Organizer", { exact: true })).toHaveCount(
    20,
  );
  await expect(panel.locator("time").first()).toHaveAttribute(
    "datetime",
    entries[0].created_at,
  );
  await expect(
    panel.getByRole("button", { name: "Newer activity", exact: true }),
  ).toBeDisabled();
  await expect(
    panel.getByRole("button", { name: "Newer activity", exact: true }),
  ).toHaveCSS("cursor", "default");
  await panel
    .getByRole("button", { name: "Older activity", exact: true })
    .click();
  await expect(
    panel.getByRole("heading", { name: "Event created", exact: true }),
  ).toBeVisible();
  await expect(panel.getByRole("listitem")).toHaveCount(1);
  await expect(
    panel.getByRole("button", { name: "Older activity", exact: true }),
  ).toBeDisabled();
  // The version change should reset pagination and load the new action automatically.
  await page
    .getByRole("button", { name: "Publish event", exact: true })
    .click();
  await expect(
    panel.getByRole("heading", { name: "Event published", exact: true }),
  ).toBeVisible();
  await expect(
    panel.getByText("22 recorded actions", { exact: true }),
  ).toBeVisible();
  await expect(panel.getByRole("listitem")).toHaveCount(20);
  await expect(
    panel.getByRole("button", { name: "Newer activity", exact: true }),
  ).toBeDisabled();
  entries.length = 0;
  await panel
    .getByRole("button", { name: "Refresh activity", exact: true })
    .click();
  await expect(
    panel.getByText("No activity recorded yet.", { exact: true }),
  ).toBeVisible();
  expect(unexpected).toEqual([]);
});
