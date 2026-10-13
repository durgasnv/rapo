import { expect, test } from "@playwright/test";

test("attention pagination, refresh, and recovery from a failed read", async ({
  page,
}) => {
  let fail = true;
  const at = new Date(Date.now() + 86400000).toISOString();
  const events = Array.from({ length: 21 }, (_, i) => ({
    event_id: `event-${i}`,
    title: `Review event ${i}`,
    start_at: at,
    timezone: "UTC",
    status: i === 0 ? "PUBLISHED" : "GROUPS_PROPOSED",
    reasons: [
      i === 0
        ? "Grouping failed. Review the job details."
        : "Preview awaiting review.",
    ],
  }));
  const unexpected: string[] = [];
  await page.route("http://127.0.0.1:8000/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/me")
      return route.fulfill({
        json: {
          user: {
            id: "organizer",
            name: "Organizer",
            email: "organizer@example.com",
            role: "organizer",
          },
          csrf_token: "test-csrf",
        },
      });
    if (url.pathname === "/organizer/events")
      return route.fulfill({
        json: [
          {
            id: "event-0",
            title: "Review event 0",
            status: "GROUPS_PROPOSED",
            start_at: at,
            timezone: "UTC",
          },
        ],
      });
    if (url.pathname === "/organizer/attention") {
      if (fail)
        return route.fulfill({
          status: 503,
          json: { detail: "Attention temporarily unavailable" },
        });
      const offset = Number(url.searchParams.get("offset"));
      return route.fulfill({
        json: {
          items: events.slice(offset, offset + 20),
          total: events.length,
          offset,
          limit: 20,
        },
      });
    }
    unexpected.push(url.pathname);
    return route.fulfill({ status: 404 });
  });
  await page.goto("/organizer");
  const panel = page.getByRole("region", {
    name: "Events needing attention",
    exact: true,
  });
  await expect(panel.getByRole("alert")).toHaveText(
    "Attention temporarily unavailable",
  );
  // The attention read failing does not block the existing event management list.
  await expect(
    page.getByRole("link", { name: "Manage event", exact: true }),
  ).toBeVisible();
  fail = false;
  await panel
    .getByRole("button", { name: "Refresh attention", exact: true })
    .click();
  await expect(
    panel.getByText("21 events need attention", { exact: true }),
  ).toBeVisible();
  await expect(panel.getByRole("link")).toHaveCount(20);
  await expect(
    panel.getByText("Grouping failed. Review the job details.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    panel.getByRole("link", { name: "Manage Review event 0", exact: true }),
  ).toHaveAttribute("href", "/organizer/events/event-0");
  await expect(
    panel.getByRole("button", { name: "Previous attention page", exact: true }),
  ).toBeDisabled();
  await expect(
    panel.getByRole("button", { name: "Previous attention page", exact: true }),
  ).toHaveCSS("cursor", "default");
  await expect(
    panel.getByRole("button", { name: "Previous attention page", exact: true }),
  ).toHaveCSS("opacity", "0.45");
  await panel
    .getByRole("button", { name: "Next attention page", exact: true })
    .click();
  await expect(panel.getByRole("link")).toHaveCount(1);
  await expect(
    panel.getByRole("heading", { name: "Review event 20", exact: true }),
  ).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "Next attention page", exact: true }),
  ).toBeDisabled();
  await panel
    .getByRole("button", { name: "Previous attention page", exact: true })
    .click();
  await expect(panel.getByRole("link")).toHaveCount(20);
  await panel
    .getByRole("button", { name: "Next attention page", exact: true })
    .click();
  await expect(panel.getByRole("link")).toHaveCount(1);
  events.length = 0;
  await panel
    .getByRole("button", { name: "Refresh attention", exact: true })
    .click();
  await expect(
    panel.getByText("No events need attention right now.", { exact: true }),
  ).toBeVisible();
  await expect(panel.getByRole("link")).toHaveCount(0);
  expect(unexpected).toEqual([]);
});
