import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import type { APIRequestContext, BrowserContext } from "@playwright/test";

test("scheduled preview requires approval and private notifications persist read state", async ({
  browser,
  playwright,
}) => {
  test.setTimeout(180_000);
  const clients: APIRequestContext[] = [];
  const contexts: BrowserContext[] = [];
  const account = async (name: string) => {
    const client = await playwright.request.newContext({
      baseURL: "http://127.0.0.1:8000",
      extraHTTPHeaders: { Origin: "http://127.0.0.1:3000" },
    });
    clients.push(client);
    const email = `automation-${randomUUID()}@example.com`;
    const response = await client.post("/auth/register", {
      data: { name, email, password: "a-long-browser-test-passphrase" },
    });
    expect(response.status()).toBe(201);
    return { client, email, ...(await response.json()) };
  };
  try {
    const owner = await account("Automation organizer");
    execFileSync("uv", ["run", "python", "-m", "app.cli", owner.email], {
      env: { ...process.env, PYTHONPATH: "apps/api" },
    });
    const now = Date.now();
    const at = (days: number) => new Date(now + days * 86400000).toISOString();
    const response = await owner.client.post("/events", {
      headers: { "X-CSRF-Token": owner.csrf_token },
      data: {
        title: "Scheduled browser workshop",
        description: "Approval and private notifications",
        timezone: "UTC",
        start_at: at(10),
        end_at: at(11),
        registration_opens_at: at(-2),
        registration_closes_at: at(5),
        confirmation_deadline: at(9),
        capacity: 2,
        min_team_size: 2,
        max_team_size: 3,
      },
    });
    expect(response.status()).toBe(201);
    const event = await response.json();
    expect(
      (
        await owner.client.post(`/events/${event.id}/publish`, {
          headers: { "X-CSRF-Token": owner.csrf_token },
          data: { version: event.version },
        })
      ).status(),
    ).toBe(200);
    const participant = await account("Automation participant");
    const peer = await account("Automation peer");
    for (const person of [participant, peer])
      expect(
        (
          await person.client.post(`/events/${event.id}/register`, {
            headers: { "X-CSRF-Token": person.csrf_token },
          })
        ).status(),
      ).toBe(200);
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
from app.jobs.grouping import run_once
url=os.environ['RAPO_DATABASE_URL']
assert (make_url(url).database or '').endswith('_test')
engine=make_engine(url)
with Session(engine) as db:
    event=db.get(Event,UUID(sys.argv[1]))
    event.registration_closes_at=utcnow()-timedelta(hours=2)
    event.grouping_at=utcnow()-timedelta(hours=1)
    db.commit()
assert run_once(engine).get('SUCCEEDED',0)>=1
assert run_once(engine)=={}
engine.dispose()
`,
        event.id,
      ],
      { env: { ...process.env, PYTHONPATH: "apps/api" } },
    );
    const ownerContext = await browser.newContext({
      storageState: await owner.client.storageState(),
    });
    const personContext = await browser.newContext({
      storageState: await participant.client.storageState(),
    });
    contexts.push(ownerContext, personContext);
    const organizer = await ownerContext.newPage();
    await organizer.goto(`/organizer/events/${event.id}`);
    await expect(
      organizer.getByRole("region", {
        name: "Scheduled grouping",
        exact: true,
      }),
    ).toContainText("SUCCEEDED");
    const preview = organizer.getByRole("region", {
      name: "Grouping preview",
      exact: true,
    });
    await expect(
      preview.getByRole("button", {
        name: "Finalize these teams",
        exact: true,
      }),
    ).toBeVisible();
    expect(
      (await participant.client.get(`/events/${event.id}/teams`)).status(),
    ).toBe(200);
    expect(
      (await (await participant.client.get(`/events/${event.id}/teams`)).json())
        .teams,
    ).toHaveLength(0);
    await preview
      .getByRole("button", { name: "Finalize these teams", exact: true })
      .click();
    await expect(
      organizer.getByRole("region", { name: "Final team roster", exact: true }),
    ).toBeVisible();
    const page = await personContext.newPage();
    await page.goto("/dashboard");
    const inbox = page.getByRole("region", {
      name: "Your notifications",
      exact: true,
    });
    await expect(inbox).toContainText("Your team is assigned.");
    await expect(inbox).toContainText("1 unread notifications");
    await inbox
      .getByRole("button", { name: "Mark as read", exact: true })
      .click();
    await expect(inbox).toContainText("0 unread notifications");
    await inbox
      .getByRole("checkbox", { name: "Unread only", exact: true })
      .check();
    await expect(inbox).toContainText("No notifications on this page.");
    await page.reload();
    await expect(inbox).toContainText("Your team is assigned.");
    await expect(
      inbox.getByRole("button", { name: "Mark as read", exact: true }),
    ).toHaveCount(0);
    await inbox.getByRole("link", { name: "View update", exact: true }).click();
    const ownTeam = page.getByRole("region", {
      name: "Your team",
      exact: true,
    });
    await ownTeam
      .getByRole("button", { name: "Withdraw from team", exact: true })
      .click();
    await expect(ownTeam).toContainText("Your assignment is withdrawn.");
    await organizer.goto("/dashboard");
    const ownerInbox = organizer.getByRole("region", {
      name: "Your notifications",
      exact: true,
    });
    await expect(ownerInbox).toContainText(
      "Your scheduled team preview is ready",
    );
    await expect(ownerInbox).toContainText("A participant withdrew.");
    const current = await (
      await owner.client.get(`/organizer/events/${event.id}`)
    ).json();
    expect(
      (
        await owner.client.post(`/events/${event.id}/cancel`, {
          headers: { "X-CSRF-Token": owner.csrf_token },
          data: { version: current.version },
        })
      ).status(),
    ).toBe(200);
    const peerNotices = await (
      await peer.client.get("/me/notifications")
    ).json();
    expect(
      peerNotices.items.some(
        (n: { kind: string }) => n.kind === "TEAM_CHANGED",
      ),
    ).toBe(true);
    expect(
      peerNotices.items.some(
        (n: { kind: string }) => n.kind === "EVENT_CANCELLED",
      ),
    ).toBe(true);
  } finally {
    await Promise.allSettled(contexts.map((context) => context.close()));
    await Promise.allSettled(clients.map((client) => client.dispose()));
  }
});
