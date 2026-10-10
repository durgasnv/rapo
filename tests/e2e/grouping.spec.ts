import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

test("organizer previews teams, retries a lost response, and sees stale registrations", async ({
  browser,
  playwright,
}) => {
  const api = await playwright.request.newContext({
    baseURL: "http://127.0.0.1:8000",
    extraHTTPHeaders: { Origin: "http://127.0.0.1:3000" },
  });
  const email = `grouping-owner-${randomUUID()}@example.com`;
  let context;
  try {
    const signup = await api.post("/auth/register", {
      data: {
        name: "Grouping organizer",
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
    const at = (days: number) => new Date(now + days * 86400000).toISOString();
    const created = await api.post("/events", {
      headers: { "X-CSRF-Token": account.csrf_token },
      data: {
        title: "Grouping browser workshop",
        description: "History-aware proposals",
        timezone: "UTC",
        start_at: at(10),
        end_at: at(11),
        registration_opens_at: at(-2),
        registration_closes_at: at(5),
        confirmation_deadline: at(9),
        min_team_size: 2,
        max_team_size: 2,
      },
    });
    expect(created.status()).toBe(201);
    const event = await created.json();
    expect(
      (
        await api.post(`/events/${event.id}/publish`, {
          headers: { "X-CSRF-Token": account.csrf_token },
          data: { version: event.version },
        })
      ).status(),
    ).toBe(200);
    context = await browser.newContext({
      storageState: await api.storageState(),
    });
    const page = await context.newPage();
    const hydrationErrors: string[] = [];
    page.on("console", (message) => {
      if (/hydration|hydrated|didn't match/i.test(message.text()))
        hydrationErrors.push(message.text());
    });
    await page.goto(`/organizer/events/${event.id}`);
    const panel = page.getByRole("region", {
      name: "Grouping preview",
      exact: true,
    });
    await panel
      .getByRole("button", { name: "Generate team preview", exact: true })
      .click();
    await expect(panel.getByRole("alert")).toContainText(
      "Wait until registration closes",
    );

    const seedScript = `
import json, os, sys
from datetime import timedelta
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from app.db import make_engine
from app.models import Event, User, Registration, GroupingRun, Team, TeamMember, utcnow
from app.schemas.events import EventInput
data = json.load(sys.stdin)
url = os.environ['RAPO_DATABASE_URL']
assert (make_url(url).database or '').endswith('_test')
with Session(make_engine(url)) as db:
    event = db.get(Event, UUID(data['event_id']))
    event.registration_closes_at = utcnow() - timedelta(days=1)
    users = [User(name=f'Grouping person {i}', email=f'{uuid4()}@example.com', password_hash='unused') for i in range(4)]
    db.add_all(users)
    db.flush()
    db.add_all([Registration(event_id=event.id, user_id=u.id, status='REGISTERED', queue_number=i+1) for i,u in enumerate(users)])
    body = EventInput.model_validate(event).model_dump()
    for key in ['start_at','end_at','registration_opens_at','registration_closes_at','grouping_at','confirmation_deadline']:
        body[key] -= timedelta(days=30)
    past = Event(**body, organizer_id=event.organizer_id, status='COMPLETED')
    db.add(past)
    db.flush()
    run = GroupingRun(event_id=past.id, request_id=uuid4(), created_by=event.organizer_id, status='FINALIZED', algorithm_version='fixture', seed=0, input_hash='0'*64, min_team_size=event.min_team_size, max_team_size=event.max_team_size, score=0, fairness=0, baseline_score=0, baseline_fairness=0, evaluations=0, history_snapshot=[])
    db.add(run)
    db.flush()
    for number, people in enumerate([users[:2], users[2:]], 1):
        team = Team(run_id=run.id, number=number, score=0, explanation='Historical fixture')
        db.add(team)
        db.flush()
        db.add_all([TeamMember(team_id=team.id, run_id=run.id, user_id=u.id) for u in people])
    db.commit()
`;
    execFileSync("uv", ["run", "python", "-c", seedScript], {
      input: JSON.stringify({ event_id: event.id }),
      env: { ...process.env, PYTHONPATH: "apps/api" },
    });
    // Commit the request but lose its response, simulating a network interruption.
    await page.route(
      "**/grouping-runs",
      async (route) => {
        await route.fetch();
        await route.abort();
      },
      { times: 1 },
    );
    await panel
      .getByRole("button", { name: "Generate team preview", exact: true })
      .click();
    await expect(panel.getByRole("alert")).toContainText("couldn’t reach");
    const committed = await (
      await api.get(`/events/${event.id}/grouping-runs/latest`)
    ).json();
    await panel
      .getByRole("button", { name: "Generate team preview", exact: true })
      .click();
    await expect(panel.getByRole("status")).toContainText("Repeat score: 0");
    const retried = await (
      await api.get(`/events/${event.id}/grouping-runs/latest`)
    ).json();
    expect(retried.id).toBe(committed.id);
    await expect(panel.getByRole("heading", { name: /^Team \d/ })).toHaveCount(
      2,
    );
    for (let i = 0; i < 4; i++)
      await expect(
        panel.getByText(`Grouping person ${i}`, { exact: true }),
      ).toHaveCount(1);
    await page.reload();
    await expect(panel.getByRole("status")).toContainText("Repeat score: 0");
    execFileSync(
      "uv",
      [
        "run",
        "python",
        "-c",
        `
import os, sys
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from app.db import make_engine
from app.models import Registration
from app.services.registrations import withdraw
url = os.environ['RAPO_DATABASE_URL']
assert (make_url(url).database or '').endswith('_test')
with Session(make_engine(url)) as db:
    event_id = UUID(sys.argv[1])
    registration = db.scalar(select(Registration).where(Registration.event_id == event_id).order_by(Registration.queue_number))
    withdraw(db, event_id, registration.user_id)
    db.commit()
`,
        event.id,
      ],
      { env: { ...process.env, PYTHONPATH: "apps/api" } },
    );
    await panel
      .getByRole("button", { name: "Refresh preview", exact: true })
      .click();
    await expect(panel.getByRole("alert")).toContainText("Stale preview");
    await panel
      .getByRole("button", { name: "Generate team preview", exact: true })
      .click();
    await expect(
      panel.getByRole("alert").filter({ hasText: "Cannot place all 3 people" }),
    ).toBeVisible();
    expect(hydrationErrors).toEqual([]);
  } finally {
    await context?.close();
    await api.dispose();
  }
});
