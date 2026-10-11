import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import type { APIRequestContext, BrowserContext } from "@playwright/test";

test("finalize, confirm, decline, replace, reassign, extend deadline and export", async ({
  browser,
  playwright,
}) => {
  const clients: APIRequestContext[] = [];
  const contexts: BrowserContext[] = [];
  const account = async (name: string) => {
    const client = await playwright.request.newContext({
      baseURL: "http://127.0.0.1:8000",
      extraHTTPHeaders: { Origin: "http://127.0.0.1:3000" },
    });
    clients.push(client);
    const email = `teams-${randomUUID()}@example.com`;
    const response = await client.post("/auth/register", {
      data: { name, email, password: "a-long-browser-test-passphrase" },
    });
    expect(response.status()).toBe(201);
    return { client, email, ...(await response.json()) };
  };
  try {
    const owner = await account("Team organizer");
    execFileSync("uv", ["run", "python", "-m", "app.cli", owner.email], {
      env: { ...process.env, PYTHONPATH: "apps/api" },
    });
    const now = Date.now();
    const at = (days: number) => new Date(now + days * 86400000).toISOString();
    const created = await owner.client.post("/events", {
      headers: { "X-CSRF-Token": owner.csrf_token },
      data: {
        title: "Lifecycle browser workshop",
        description: "Final assignments and replacements",
        timezone: "UTC",
        start_at: at(10),
        end_at: at(11),
        registration_opens_at: at(-2),
        registration_closes_at: at(5),
        confirmation_deadline: at(9),
        min_team_size: 2,
        max_team_size: 3,
        capacity: 4,
      },
    });
    expect(created.status()).toBe(201);
    const event = await created.json();
    expect(
      (
        await owner.client.post(`/events/${event.id}/publish`, {
          headers: { "X-CSRF-Token": owner.csrf_token },
          data: { version: event.version },
        })
      ).status(),
    ).toBe(200);
    const people = [];
    for (const name of [
      "Team Alice",
      "Team Bob",
      "Team Carol",
      "Team Dan",
      "Team Waiting",
    ]) {
      const person = await account(name);
      const response = await person.client.post(
        `/events/${event.id}/register`,
        { headers: { "X-CSRF-Token": person.csrf_token } },
      );
      expect(response.status()).toBe(200);
      people.push(person);
    }
    execFileSync(
      "uv",
      [
        "run",
        "python",
        "-c",
        `
import os, sys
from uuid import UUID
from datetime import timedelta
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from app.db import make_engine
from app.models import Event, utcnow
url = os.environ['RAPO_DATABASE_URL']
assert (make_url(url).database or '').endswith('_test')
with Session(make_engine(url)) as db:
    event = db.get(Event, UUID(sys.argv[1]))
    event.registration_closes_at = utcnow() - timedelta(days=1)
    db.commit()
`,
        event.id,
      ],
      { env: { ...process.env, PYTHONPATH: "apps/api" } },
    );
    const ownerContext = await browser.newContext({
      storageState: await owner.client.storageState(),
    });
    contexts.push(ownerContext);
    const organizer = await ownerContext.newPage();
    await organizer.goto(`/organizer/events/${event.id}`);
    const preview = organizer.getByRole("region", {
      name: "Grouping preview",
      exact: true,
    });
    await preview
      .getByRole("button", { name: "Generate team preview", exact: true })
      .click();
    await preview
      .getByRole("button", { name: "Finalize these teams", exact: true })
      .click();
    const roster = organizer.getByRole("region", {
      name: "Final team roster",
      exact: true,
    });
    await expect(
      roster.getByRole("heading", { name: /Team \d.*AWAITING CONFIRMATIONS/ }),
    ).toHaveCount(2);
    const aliceContext = await browser.newContext({
      storageState: await people[0].client.storageState(),
    });
    contexts.push(aliceContext);
    const alice = await aliceContext.newPage();
    await alice.goto("/dashboard");
    await alice
      .getByRole("link", { name: "View your team and confirm", exact: true })
      .click();
    await alice.waitForURL(`**/events/${event.id}`, { timeout: 60_000 });
    const own = alice.getByRole("region", { name: "Your team", exact: true });
    await expect(own.getByRole("heading", { name: /^Team \d/ })).toHaveCount(1);
    await own
      .getByRole("button", { name: "Confirm my team", exact: true })
      .click();
    await expect(
      own.getByText("Team Alice · confirmed", { exact: true }),
    ).toBeVisible();
    await own
      .getByRole("button", { name: "Decline assignment", exact: true })
      .click();
    await expect(
      own.getByText("Your assignment is declined.", { exact: true }),
    ).toBeVisible();
    await roster
      .getByRole("button", { name: "Refresh teams", exact: true })
      .click();
    const attention = roster.getByRole("region").filter({
      has: organizer.getByRole("heading", { name: /NEEDS ATTENTION/ }),
    });
    await expect(attention).toHaveCount(1);
    await expect(
      attention.getByText("Below minimum: 1 active; at least 2 required.", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      attention.getByText("Vacancy: 1 unfilled place (1 of 2 expected).", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      attention.getByRole("button", {
        name: "Approve current team size",
        exact: true,
      }),
    ).toBeDisabled();
    await expect(
      attention.getByText(/Cannot approve: at least 2 active members required/),
    ).toBeVisible();
    await attention
      .getByRole("button", { name: "Fill vacancy from waitlist", exact: true })
      .click();
    await expect(
      roster.getByText("Team Waiting · pending", { exact: true }),
    ).toBeVisible();
    await expect(roster.getByRole("status")).toContainText(
      "Vacancy filled from the waitlist.",
    );
    const waitingContext = await browser.newContext({
      storageState: await people[4].client.storageState(),
    });
    contexts.push(waitingContext);
    const waiting = await waitingContext.newPage();
    await waiting.goto(`/events/${event.id}`);
    const waitingTeam = waiting.getByRole("region", {
      name: "Your team",
      exact: true,
    });
    await waitingTeam
      .getByRole("button", { name: "Confirm my team", exact: true })
      .click();
    await expect(
      waitingTeam.getByText("Team Waiting · confirmed", { exact: true }),
    ).toBeVisible();
    await roster
      .getByRole("button", { name: "Refresh teams", exact: true })
      .click();
    const current = await (
      await owner.client.get(`/events/${event.id}/teams`)
    ).json();
    const source = current.teams.find(
      (t: { members: { user_id: string; status: string }[] }) =>
        t.members.some(
          (m) => m.user_id === people[4].user.id && m.status === "CONFIRMED",
        ),
    );
    const teammate = source.members.find(
      (m: { user_id: string; status: string }) =>
        m.user_id !== people[4].user.id && m.status === "PENDING",
    );
    const target = current.teams.find(
      (t: { id: string }) => t.id !== source.id,
    );
    await roster
      .getByRole("combobox", { name: "Participant to move", exact: true })
      .selectOption(teammate.user_id);
    await roster
      .getByRole("combobox", { name: "Target team", exact: true })
      .selectOption(target.id);
    await roster
      .getByRole("combobox", { name: "Swap with (optional)", exact: true })
      .selectOption(target.members[0].user_id);
    await roster
      .getByRole("button", { name: "Save reassignment", exact: true })
      .click();
    await expect(
      roster.getByText("Team Waiting · pending", { exact: true }),
    ).toBeVisible();
    await waitingTeam
      .getByRole("button", { name: "Refresh teams", exact: true })
      .click();
    await expect(
      waitingTeam.getByRole("button", { name: "Confirm my team", exact: true }),
    ).toBeEnabled();
    await roster
      .getByLabel("New confirmation deadline (UTC)", { exact: true })
      .fill(event.start_at.slice(0, 16));
    await roster
      .getByRole("button", {
        name: "Extend confirmation deadline",
        exact: true,
      })
      .click();
    await expect(async () => {
      const current = await (
        await owner.client.get(`/events/${event.id}/teams`)
      ).json();
      expect(new Date(current.confirmation_deadline).getTime()).toBeGreaterThan(
        new Date(at(9)).getTime(),
      );
    }).toPass();
    const downloadPromise = organizer.waitForEvent("download");
    await roster
      .getByRole("button", { name: "Export teams CSV", exact: true })
      .click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`rapo-${event.id}-teams.csv`);
    const content = await readFile((await download.path())!, "utf8");
    expect(content).toContain('"Team Waiting"');
    expect(content).toContain('"DECLINED"');
    expect(content).not.toContain(people[0].email);
    await waitingTeam
      .getByRole("button", { name: "Withdraw from team", exact: true })
      .click();
    await expect(
      waitingTeam.getByText("Your assignment is withdrawn.", { exact: true }),
    ).toBeVisible();
    await roster
      .getByRole("button", { name: "Refresh teams", exact: true })
      .click();
    const vacant = roster.getByRole("region").filter({
      has: organizer.getByRole("heading", { name: /NEEDS ATTENTION/ }),
    });
    await vacant
      .getByRole("button", { name: "Fill vacancy from waitlist", exact: true })
      .click();
    await expect(vacant.getByRole("alert")).toContainText(
      "No eligible waitlisted participant",
    );
    // A trusted test-only configuration permits continuation with one remaining member.
    execFileSync(
      "uv",
      [
        "run",
        "python",
        "-c",
        `
import os, sys
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from app.db import make_engine
from app.models import Event
url = os.environ['RAPO_DATABASE_URL']
assert (make_url(url).database or '').endswith('_test')
with Session(make_engine(url)) as db:
    event = db.get(Event, UUID(sys.argv[1]))
    event.min_team_size = 1
    db.commit()
`,
        event.id,
      ],
      { env: { ...process.env, PYTHONPATH: "apps/api" } },
    );
    await organizer.reload();
    const approvalCardName = await vacant.getAttribute("aria-label");
    const approvalCard = roster.getByRole("region", {
      name: approvalCardName!,
      exact: true,
    });
    await approvalCard
      .getByRole("button", { name: "Approve current team size", exact: true })
      .click();
    await expect(approvalCard.getByRole("status")).toHaveText(
      "Current size approved: 1 active member. Awaiting confirmation from 1 member.",
    );
    await expect(approvalCard.getByRole("heading")).toContainText(
      "AWAITING CONFIRMATIONS",
    );
    await expect(
      approvalCard.getByRole("button", {
        name: "Approve current team size",
        exact: true,
      }),
    ).toBeDisabled();
    await expect(
      approvalCard.getByText(
        "Current size already approved. Member confirmations are separate.",
        { exact: true },
      ),
    ).toBeVisible();
  } finally {
    for (const context of contexts) await context.close();
    for (const client of clients) await client.dispose();
  }
});
