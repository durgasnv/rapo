import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

test("hosted organizer and participant flow uses the scheduled worker", async ({
  browser,
  page: organizer,
  playwright,
  baseURL,
}) => {
  expect((await organizer.request.get("/api/ready")).status()).toBe(200);
  await organizer.goto("/sign-in");
  await organizer
    .getByLabel("Email", { exact: true })
    .fill(process.env.RAPO_SMOKE_ORGANIZER_EMAIL!);
  await organizer
    .getByLabel("Password", { exact: true })
    .fill(process.env.RAPO_SMOKE_ORGANIZER_PASSWORD!);
  await organizer.getByRole("button", { name: "Sign in", exact: true }).click();
  await organizer.waitForURL("**/dashboard");
  const owner = await (await organizer.request.get("/api/me")).json();
  expect(owner.user.role).toBe("organizer");
  const cookie = (await organizer.context().cookies()).find(
    (item) => item.name === "rapo_session",
  );
  // Assert flags individually so a failure cannot print the cookie's raw value.
  expect(cookie?.secure).toBe(true);
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Lax");
  expect(cookie?.domain).toBe(new URL(baseURL!).hostname);

  const participantContext = await browser.newContext({ baseURL });
  const peer = await playwright.request.newContext({
    baseURL,
    extraHTTPHeaders: { Origin: baseURL! },
  });
  const participant = await participantContext.newPage();
  let eventId = "";
  try {
    const suffix = randomUUID();
    const password = `smoke-${randomUUID()}-password`;
    await participant.goto("/sign-up");
    await participant.getByLabel("Your name").fill("Release smoke participant");
    await participant
      .getByLabel("Email", { exact: true })
      .fill(`smoke-${suffix}@example.com`);
    await participant.getByLabel("Password", { exact: true }).fill(password);
    await participant
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await participant.waitForURL("**/dashboard");
    await participant.reload();
    await expect(
      participant.getByRole("heading", {
        name: "Hello, Release smoke participant.",
      }),
    ).toBeVisible();
    const member = await (await participant.request.get("/api/me")).json();
    expect(
      (
        await peer.post("/api/auth/register", {
          data: {
            name: "Release smoke peer",
            email: `peer-${suffix}@example.com`,
            password,
          },
        })
      ).status(),
    ).toBe(201);
    const peerAccount = await (await peer.get("/api/me")).json();
    const now = Date.now();
    const at = (seconds: number) =>
      new Date(now + seconds * 1000).toISOString();
    const data = {
      title: `[Release smoke] ${suffix}`,
      description: "Hosted verification event; cancelled after verification.",
      timezone: "UTC",
      start_at: at(86400),
      end_at: at(90000),
      registration_opens_at: at(-60),
      registration_closes_at: at(90),
      grouping_at: at(90),
      confirmation_deadline: at(3600),
      capacity: 2,
      min_team_size: 2,
      max_team_size: 2,
    };
    expect(
      (
        await participant.request.post("/api/events", {
          data,
          headers: { "X-CSRF-Token": member.csrf_token },
        })
      ).status(),
    ).toBe(403);
    const created = await organizer.request.post("/api/events", {
      data,
      headers: { "X-CSRF-Token": owner.csrf_token },
    });
    expect(created.status()).toBe(201);
    const event = await created.json();
    eventId = event.id;
    expect(
      (
        await organizer.request.post(`/api/events/${eventId}/publish`, {
          data: { version: event.version },
          headers: { "X-CSRF-Token": owner.csrf_token },
        })
      ).status(),
    ).toBe(200);
    expect(
      (
        await participant.request.get(
          `/api/events/${eventId}/grouping-runs/latest`,
        )
      ).status(),
    ).toBe(403);
    expect(
      (
        await participant.request.post(`/api/events/${eventId}/register`)
      ).status(),
    ).toBe(403);
    for (const [client, token] of [
      [participant.request, member.csrf_token],
      [peer, peerAccount.csrf_token],
    ] as const) {
      expect(
        (
          await client.post(`/api/events/${eventId}/register`, {
            headers: { "X-CSRF-Token": token },
          })
        ).status(),
      ).toBe(200);
    }
    let proposalId = "";
    await expect(async () => {
      const response = await organizer.request.get(
        `/api/events/${eventId}/grouping-runs/latest`,
      );
      expect(response.status()).toBe(200);
      const proposal = await response.json();
      expect(proposal).toBeTruthy();
      proposalId = proposal.id;
      expect(proposal.teams).toHaveLength(1);
    }).toPass({ timeout: 4_500_000, intervals: [10000, 30000] });
    const job = await (
      await organizer.request.get(`/api/events/${eventId}/grouping-job`)
    ).json();
    expect(job.status).toBe("SUCCEEDED");
    expect(job.attempts).toBe(1);
    expect(
      (
        await (
          await participant.request.get(`/api/events/${eventId}/teams`)
        ).json()
      ).teams,
    ).toHaveLength(0);
    expect(
      (
        await (
          await organizer.request.get(
            `/api/events/${eventId}/grouping-runs/latest`,
          )
        ).json()
      ).id,
    ).toBe(proposalId);
    await organizer.goto(`/organizer/events/${eventId}`);
    await organizer
      .getByRole("button", { name: "Finalize these teams", exact: true })
      .click();
    await expect(
      organizer.getByRole("region", { name: "Final team roster", exact: true }),
    ).toBeVisible();
    await participant.goto(`/events/${eventId}`);
    await participant
      .getByRole("button", { name: "Confirm my team", exact: true })
      .click();
    await expect(
      participant.getByRole("button", { name: "Confirmed", exact: true }),
    ).toBeVisible();
    const roster = await (
      await participant.request.get(`/api/events/${eventId}/teams`)
    ).json();
    expect(roster.own_status).toBe("CONFIRMED");
  } finally {
    if (eventId) {
      const current = await organizer.request.get(
        `/api/organizer/events/${eventId}`,
      );
      if (current.ok()) {
        const event = await current.json();
        const cancelled = await organizer.request.post(
          `/api/events/${eventId}/cancel`,
          {
            data: { version: event.version },
            headers: { "X-CSRF-Token": owner.csrf_token },
          },
        );
        expect(
          cancelled.status(),
          "Cancel the smoke event after verification",
        ).toBe(200);
      }
    }
    await participantContext.close();
    await peer.dispose();
  }
});
