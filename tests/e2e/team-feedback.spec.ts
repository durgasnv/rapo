import { expect, test } from "@playwright/test";
import type { EventData, FinalRoster } from "../../apps/web/lib/api";

for (const outcome of ["READY", "NEEDS_ATTENTION", "RETRY"] as const) {
  test(`approval feedback: ${outcome}`, async ({ page }) => {
    const eventId = "c605bc25-e88a-4c63-97a9-c86747ad174b";
    const teamId = "1528503e-4efb-452e-9140-40f2eed371fc";
    const ownerId = "a16492ec-cd18-41bb-8ea3-b54f37adfce9";
    const at = (days: number) =>
      new Date(Date.now() + days * 86400000).toISOString();
    const overdue = outcome === "NEEDS_ATTENTION";
    const event: EventData = {
      id: eventId,
      organizer_id: ownerId,
      title: "Approval feedback workshop",
      description: "Team approval",
      location: "",
      timezone: "UTC",
      start_at: at(10),
      end_at: at(11),
      registration_opens_at: at(-10),
      registration_closes_at: at(-5),
      grouping_at: at(-4),
      confirmation_deadline: at(overdue ? -1 : 9),
      capacity: null,
      min_team_size: 2,
      max_team_size: 4,
      status: "GROUPS_FINALIZED",
      version: 1,
    };
    const overdueReason =
      "Confirmation overdue: 3 still awaiting confirmation.";
    let roster: FinalRoster = {
      event_id: eventId,
      event_status: event.status,
      version: 1,
      confirmation_deadline: event.confirmation_deadline,
      confirmation_open: !overdue,
      withdrawal_open: true,
      own_status: null,
      teams: [
        {
          id: teamId,
          number: 1,
          version: 1,
          target_size: 4,
          status: "NEEDS_ATTENTION",
          reasons: ["Vacancy: 1 unfilled place (3 of 4 expected)."],
          members: ["Alice", "Bob", "Carol"].map((name, i) => ({
            user_id: `member-${i}`,
            name,
            status: overdue ? "PENDING" : "CONFIRMED",
            confirmed_at: overdue ? null : at(-2),
          })),
        },
      ],
    };
    const writes: Record<string, unknown>[] = [];
    const unexpected: string[] = [];
    await page.route("http://127.0.0.1:8000/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/me")
        return route.fulfill({
          json: {
            user: {
              id: ownerId,
              name: "Organizer",
              email: "organizer@example.com",
              role: "organizer",
            },
            csrf_token: "test-csrf",
          },
        });
      if (path === `/organizer/events/${eventId}`)
        return route.fulfill({ json: event });
      if (path === `/events/${eventId}/teams`)
        return route.fulfill({ json: roster });
      if (path === `/events/${eventId}/teams/${teamId}/continue`) {
        writes.push(route.request().postDataJSON());
        // Simulate a committed save whose response was lost. The retry must reuse its ID/version.
        roster = {
          ...roster,
          version: 2,
          teams: [
            {
              ...roster.teams[0],
              version: 2,
              target_size: 3,
              status: overdue ? "NEEDS_ATTENTION" : "READY",
              reasons: overdue ? [overdueReason] : [],
            },
          ],
        };
        if (outcome === "RETRY" && writes.length === 1)
          return route.abort("failed");
        return route.fulfill({ json: roster });
      }
      if (path.endsWith("/grouping-runs/latest"))
        return route.fulfill({ json: null });
      if (path.endsWith("/grouping-job"))
        return route.fulfill({
          json: {
            status: "SUCCEEDED",
            attempts: 1,
            message: "Preview created",
            next_attempt_at: null,
          },
        });
      if (path.endsWith("/registrations"))
        return route.fulfill({
          json: {
            items: [],
            total: 0,
            offset: 0,
            limit: 20,
            registered_count: 3,
            waitlisted_count: 0,
          },
        });
      // Notification navigation is unrelated to these roster scenarios.
      if (path === "/notifications")
        return route.fulfill({
          json: { items: [], unread_count: 0, total: 0, offset: 0, limit: 20 },
        });
      unexpected.push(path);
      return route.fulfill({
        status: 404,
        json: { detail: "Unexpected test request" },
      });
    });
    await page.goto(`/organizer/events/${eventId}`);
    const card = page.getByRole("region", {
      name: "Final team 1",
      exact: true,
    });
    const approve = card.getByRole("button", {
      name: "Approve current team size",
      exact: true,
    });
    await approve.click();
    if (outcome === "RETRY") {
      await expect(card.getByRole("alert")).toContainText(
        "We couldn’t reach rapo.",
      );
      await approve.click();
      expect(writes).toHaveLength(2);
      expect(writes[1]).toEqual(writes[0]);
      expect(writes[0].request_id).toEqual(expect.any(String));
    }
    await expect(card.getByRole("status")).toHaveText(
      overdue
        ? `Current size approved: 3 active members. Still needs attention: ${overdueReason}`
        : "Current size approved: 3 active members. Team is ready.",
    );
    await expect(card.getByRole("heading")).toContainText(
      overdue ? "NEEDS ATTENTION" : "READY",
    );
    await expect(approve).toBeDisabled();
    await expect(approve).toHaveCSS("cursor", "default");
    await expect(approve).toHaveCSS("opacity", "0.45");
    await expect(approve).toHaveCSS("text-decoration-line", "none");
    await expect(
      card.getByText(
        "Current size already approved. Member confirmations are separate.",
        { exact: true },
      ),
    ).toBeVisible();
    expect(writes).toHaveLength(outcome === "RETRY" ? 2 : 1);
    expect(unexpected).toEqual([]);
  });
}
