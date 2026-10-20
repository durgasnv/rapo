import { expect, test } from "@playwright/test";
import { draft } from "./fixtures/organizer-draft";

test("a successful automatic schedule refresh clears an earlier load error", async ({
  page,
  request,
}) => {
  const event = await draft(page, request);
  let unavailable = true;
  await page.route(`**/api/events/${event.id}/grouping-job`, (route) =>
    unavailable
      ? route.fulfill({
          status: 503,
          json: { detail: "Temporary schedule outage" },
        })
      : route.continue(),
  );
  await page.goto(`/organizer/events/${event.id}`);
  const panel = page.getByRole("region", {
    name: "Scheduled grouping",
    exact: true,
  });
  await expect(panel.getByRole("alert")).toContainText(
    "Temporary schedule outage",
  );
  unavailable = false;
  await page
    .getByRole("button", { name: "Publish event", exact: true })
    .click();
  await expect(
    panel.getByText("WAITING · 0 attempts", { exact: true }),
  ).toBeVisible();
  await expect(panel.getByRole("alert")).toHaveCount(0);
});
