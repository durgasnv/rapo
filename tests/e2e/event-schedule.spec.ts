import { expect, test } from "@playwright/test";
import { draft } from "./fixtures/organizer-draft";

test("editing a draft title preserves every untouched schedule timestamp", async ({
  page,
  request,
}) => {
  const event = await draft(page, request);
  await page.goto(`/organizer/events/${event.id}`);
  await page
    .getByLabel("Event title", { exact: true })
    .fill("Updated title only");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Changes saved." }),
  ).toBeVisible();
  const saved = await (
    await request.get(`http://127.0.0.1:8000/organizer/events/${event.id}`)
  ).json();
  for (const field of [
    "start_at",
    "end_at",
    "registration_opens_at",
    "registration_closes_at",
    "grouping_at",
    "confirmation_deadline",
  ])
    expect(saved[field], field).toBe(event[field]);
  // Preserving untouched values must not prevent intentional schedule edits.
  await page.locator('input[name="start_at"]').fill("2099-02-10T13:00:00.321");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect
    .poll(async () => {
      const changed = await (
        await request.get(`http://127.0.0.1:8000/organizer/events/${event.id}`)
      ).json();
      return new Date(changed.start_at).toISOString();
    })
    .toBe("2099-02-10T13:00:00.321Z");
});
