import { expect, test } from "@playwright/test";

test("browser connects to the live API", async ({ page }) => {
  await page.goto("/");
  await page.locator("summary").click();
  await expect(page.getByRole("status")).toContainText("Connected to rapo.");
  await expect(page.getByRole("status")).toContainText('{ "status": "ok" }');
});

test("failed health request can be retried", async ({ page }) => {
  await page.route("**/health", (route) => route.abort());
  await page.goto("/");
  await page.locator("summary").click();
  await expect(page.getByRole("status")).toContainText("We couldn’t connect");
  await page.unroute("**/health");
  await page.getByRole("button", { name: "Check again" }).click();
  await expect(page.getByRole("status")).toContainText("Connected to rapo.");
});
