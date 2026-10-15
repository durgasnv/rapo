import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

test("email reset through TLS SMTP revokes sessions and rejects link reuse", async ({
  page,
  playwright,
}) => {
  test.setTimeout(120_000);
  const smtp = spawn(
    "python3",
    [
      "tests/e2e/fixtures/smtp_capture.py",
      "--cert",
      join(tmpdir(), "rapo-playwright-smtp-cert.pem"),
      "--key",
      join(tmpdir(), "rapo-playwright-smtp-key.pem"),
    ],
    { stdio: "ignore" },
  );
  const api = await playwright.request.newContext({
    baseURL: "http://127.0.0.1:8000",
    extraHTTPHeaders: { Origin: "http://127.0.0.1:3000" },
  });
  const email = `reset-${randomUUID()}@example.com`;
  const password = "a-long-browser-reset-password";
  try {
    await expect(async () => {
      expect((await api.get("http://127.0.0.1:8025/health")).ok()).toBe(true);
    }).toPass({ timeout: 20_000 });
    const registered = await api.post("/auth/register", {
      data: {
        name: "Reset participant",
        email,
        password: "an-old-browser-passphrase",
      },
    });
    expect(registered.status()).toBe(201);
    await page.goto("/sign-in");
    await page
      .getByRole("link", { name: "Forgot password?", exact: true })
      .click();
    await page.waitForURL("**/forgot-password", { timeout: 60_000 });
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page
      .getByRole("button", { name: "Send reset link", exact: true })
      .click();
    await expect(page.getByRole("main").getByRole("status")).toContainText(
      "If an account exists",
    );
    let link = "";
    await expect(async () => {
      const messages = await (
        await api.get("http://127.0.0.1:8025/messages")
      ).json();
      const reset = messages.find(
        (m: { to: string; subject: string }) =>
          m.to === email && m.subject === "Reset your rapo password",
      );
      expect(reset).toBeTruthy();
      link = reset.body
        .split(/\r?\n/)
        .find((line: string) => line.startsWith("http"));
      expect(new URL(link).origin).toBe("http://127.0.0.1:3000");
    }).toPass({ timeout: 20_000 });
    await page.goto(link);
    await expect(
      page.getByLabel("New password", { exact: true }),
    ).toBeVisible();
    expect(new URL(page.url()).hash).toBe("");
    await page.getByLabel("New password", { exact: true }).fill(password);
    await page
      .getByLabel("Confirm new password", { exact: true })
      .fill("a-different-reset-password");
    await page
      .getByRole("button", { name: "Reset password", exact: true })
      .click();
    await expect(page.getByRole("main").getByRole("alert")).toHaveText(
      "Passwords must match.",
    );
    await page
      .getByLabel("Confirm new password", { exact: true })
      .fill(password);
    await page
      .getByRole("button", { name: "Reset password", exact: true })
      .click();
    await expect(page.getByRole("main").getByRole("status")).toHaveText(
      "Your password has been reset. Sign in with your new password.",
    );
    expect((await api.get("/me")).status()).toBe(401);
    await expect(async () => {
      const messages = await (
        await api.get("http://127.0.0.1:8025/messages")
      ).json();
      expect(
        messages.some(
          (m: { to: string; subject: string }) =>
            m.to === email && m.subject === "Your rapo password was reset",
        ),
      ).toBe(true);
    }).toPass();
    await page.goto(link);
    await page.getByLabel("New password", { exact: true }).fill(password);
    await page
      .getByLabel("Confirm new password", { exact: true })
      .fill(password);
    await page
      .getByRole("button", { name: "Reset password", exact: true })
      .click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText(
      "invalid or has expired",
    );
    await page.goto("/sign-in");
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.waitForURL("**/dashboard", { timeout: 60_000 });
    await expect(
      page.getByRole("heading", {
        name: "Hello, Reset participant.",
        exact: true,
      }),
    ).toBeVisible();
  } finally {
    await api.dispose();
    smtp.kill("SIGTERM");
    await new Promise<void>((resolve) => {
      if (smtp.exitCode !== null) resolve();
      else smtp.once("exit", () => resolve());
    });
  }
});

test("reset pages reject missing or malformed links without exposing a password form", async ({
  page,
}) => {
  for (const suffix of ["", "#token=invalid"]) {
    await page.goto(`/reset-password${suffix}`);
    await expect(page.getByRole("main").getByRole("alert")).toContainText(
      "missing or invalid",
    );
    await expect(page.getByLabel("New password", { exact: true })).toHaveCount(
      0,
    );
    await expect(page.locator('meta[name="referrer"]')).toHaveAttribute(
      "content",
      "no-referrer",
    );
  }
});
