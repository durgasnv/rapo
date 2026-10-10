import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { APIRequest, Browser, Page, expect, test } from "@playwright/test";

async function seedEvent(request: APIRequest, capacity: number | null) {
  const owner = await request.newContext({
    baseURL: "http://127.0.0.1:8000",
    extraHTTPHeaders: { Origin: "http://127.0.0.1:3000" },
  });
  const email = `registration-owner-${randomUUID()}@example.com`;
  try {
    const signup = await owner.post("/auth/register", {
      data: {
        name: "Registration organizer",
        email,
        password: "a-long-browser-test-passphrase",
      },
    });
    expect(signup.status()).toBe(201);
    const account = await signup.json();
    execFileSync("uv", ["run", "python", "-m", "app.cli", email], {
      env: { ...process.env, PYTHONPATH: "apps/api" },
    });
    const now = Date.now();
    const at = (days: number) =>
      new Date(now + days * 86_400_000).toISOString();
    const created = await owner.post("/events", {
      headers: { "X-CSRF-Token": account.csrf_token },
      data: {
        title: `Registration workshop ${randomUUID()}`,
        description: "Meet new collaborators.",
        timezone: "UTC",
        start_at: at(10),
        end_at: at(11),
        registration_opens_at: new Date(now - 60_000).toISOString(),
        registration_closes_at: at(5),
        confirmation_deadline: at(9),
        capacity,
        min_team_size: 1,
        max_team_size: 2,
      },
    });
    expect(created.status()).toBe(201);
    const event = await created.json();
    expect(
      (
        await owner.post(`/events/${event.id}/publish`, {
          headers: { "X-CSRF-Token": account.csrf_token },
          data: { version: event.version },
        })
      ).status(),
    ).toBe(200);
    return { event, owner, csrf: account.csrf_token as string };
  } catch (error) {
    await owner.dispose();
    throw error;
  }
}

async function signup(page: Page, name: string) {
  await page.goto("/sign-up");
  await page.getByLabel("Your name").fill(name);
  await page
    .getByLabel("Email", { exact: true })
    .fill(`registration-${randomUUID()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("a-long-browser-test-passphrase");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: `Hello, ${name}.` }),
  ).toBeVisible();
}

async function participant(browser: Browser, name: string) {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3000",
  });
  const page = await context.newPage();
  await signup(page, name);
  return { context, page };
}

test("capacity, waitlist, withdrawal and FIFO promotion are visible end to end", async ({
  browser,
  playwright,
}) => {
  const { event, owner } = await seedEvent(playwright.request, 1);
  const people = [];
  try {
    for (const name of [
      "First participant",
      "Second participant",
      "Third participant",
    ])
      people.push(await participant(browser, name));
    const [first, second, third] = people.map((person) => person.page);
    await first.goto(`/events/${event.id}`);
    const firstPanel = first.getByRole("region", {
      name: "Your registration",
      exact: true,
    });
    await firstPanel
      .getByRole("button", { name: "Register for event", exact: true })
      .click();
    await expect(
      firstPanel.getByText("Registered", { exact: true }),
    ).toBeVisible();
    await first.reload();
    await expect(
      firstPanel.getByText("Registered", { exact: true }),
    ).toBeVisible();
    await second.goto(`/events/${event.id}`);
    const secondPanel = second.getByRole("region", {
      name: "Your registration",
      exact: true,
    });
    await secondPanel
      .getByRole("button", { name: "Join waitlist", exact: true })
      .click();
    await expect(
      secondPanel.getByText("Waitlisted · position 1", { exact: true }),
    ).toBeVisible();
    await third.goto(`/events/${event.id}`);
    const thirdPanel = third.getByRole("region", {
      name: "Your registration",
      exact: true,
    });
    await thirdPanel
      .getByRole("button", { name: "Join waitlist", exact: true })
      .click();
    await expect(
      thirdPanel.getByText("Waitlisted · position 2", { exact: true }),
    ).toBeVisible();
    await firstPanel
      .getByRole("button", { name: "Withdraw registration", exact: true })
      .click();
    await expect(
      firstPanel.getByText("Withdrawn", { exact: true }),
    ).toBeVisible();
    await secondPanel
      .getByRole("button", { name: "Refresh registration", exact: true })
      .click();
    await expect(
      secondPanel.getByText("Registered", { exact: true }),
    ).toBeVisible();
    await thirdPanel
      .getByRole("button", { name: "Refresh registration", exact: true })
      .click();
    await expect(
      thirdPanel.getByText("Waitlisted · position 1", { exact: true }),
    ).toBeVisible();
    await third.goto("/dashboard");
    await expect(
      third
        .getByRole("region", { name: "Your registrations", exact: true })
        .getByText("Waitlisted · position 1", { exact: true }),
    ).toBeVisible();
    const roster = await owner.get(`/events/${event.id}/registrations`);
    expect(roster.status()).toBe(200);
    expect(
      (await roster.json()).items.map(
        (row: { name: string; status: string }) => [row.name, row.status],
      ),
    ).toEqual([
      ["Second participant", "REGISTERED"],
      ["Third participant", "WAITLISTED"],
      ["First participant", "CANCELLED"],
    ]);
    const ownerContext = await browser.newContext({
      baseURL: "http://127.0.0.1:3000",
      storageState: await owner.storageState(),
    });
    try {
      const organizer = await ownerContext.newPage();
      await organizer.goto(`/organizer/events/${event.id}`);
      const table = organizer.getByRole("table");
      await expect(
        table.getByRole("row", { name: /Second participant.*Registered/ }),
      ).toBeVisible();
      await expect(
        table.getByRole("row", {
          name: /Third participant.*Waitlisted · position 1/,
        }),
      ).toBeVisible();
      await expect(
        table.getByRole("row", { name: /First participant.*Withdrawn/ }),
      ).toBeVisible();
    } finally {
      await ownerContext.close();
    }
  } finally {
    for (const person of people) await person.context.close();
    await owner.dispose();
  }
});

test("uncapped events accept participants and event cancellation remains visible", async ({
  browser,
  playwright,
}) => {
  const { event, owner, csrf } = await seedEvent(playwright.request, null);
  const people = [];
  try {
    for (const name of ["Uncapped first", "Uncapped second"]) {
      const person = await participant(browser, name);
      people.push(person);
      await person.page.goto(`/events/${event.id}`);
      const panel = person.page.getByRole("region", {
        name: "Your registration",
        exact: true,
      });
      await panel
        .getByRole("button", { name: "Register for event", exact: true })
        .click();
      await expect(
        panel.getByText("Registered", { exact: true }),
      ).toBeVisible();
      await expect(panel.getByText(/No fixed capacity/)).toBeVisible();
    }
    const current = await (
      await owner.get(`/organizer/events/${event.id}`)
    ).json();
    expect(
      (
        await owner.post(`/events/${event.id}/cancel`, {
          headers: { "X-CSRF-Token": csrf },
          data: { version: current.version },
        })
      ).status(),
    ).toBe(200);
    await people[0].page.goto("/dashboard");
    const registrations = people[0].page.getByRole("region", {
      name: "Your registrations",
      exact: true,
    });
    await expect(
      registrations.getByText("Event cancelled", { exact: true }),
    ).toBeVisible();
    await expect(
      registrations.getByRole("link", { name: event.title, exact: true }),
    ).toHaveCount(0);
  } finally {
    for (const person of people) await person.context.close();
    await owner.dispose();
  }
});
