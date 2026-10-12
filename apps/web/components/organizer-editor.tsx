"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { EventData, apiRequest, formatDate } from "../lib/api";
import { useAccount } from "./account-provider";
import { EventForm } from "./event-form";
import { TeamRoster } from "./team-roster";
import { GroupingSchedule } from "./grouping-schedule";
import { GroupingPreview } from "./grouping-preview";
import { OrganizerRoster } from "./organizer-roster";

export function OrganizerEditor({ id }: { id?: string }) {
  const { account, loading } = useAccount();
  const [event, setEvent] = useState<EventData | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const router = useRouter();
  useEffect(() => {
    if (!id || account?.user.role !== "organizer") return;
    let active = true;
    apiRequest<EventData>(`/organizer/events/${id}`)
      .then((data) => {
        if (active) setEvent(data);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load event.",
          );
      });
    return () => {
      active = false;
    };
  }, [id, account]);
  async function transition(action: "publish" | "cancel" | "complete") {
    if (!event || !account) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await apiRequest<EventData>(
        `/events/${event.id}/${action}`,
        { method: "POST", body: JSON.stringify({ version: event.version }) },
        account.csrf_token,
      );
      setEvent(result);
      setNotice(
        action === "publish"
          ? "Your event is published."
          : action === "complete"
            ? "Event completed. Its final roster will inform future team grouping."
            : "Your event is cancelled.",
      );
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "Could not update event.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="page-shell">
      <Link className="underline" href="/organizer">
        Your events
      </Link>
      <h1 className="mt-8">{id ? "Manage event" : "Create an event"}</h1>
      {loading ? (
        <p role="status" className="intro">
          Loading your account…
        </p>
      ) : account?.user.role !== "organizer" ? (
        <p className="intro">
          Sign in with an authorized organizer account to continue.
        </p>
      ) : (
        <>
          {error && (
            <p role="alert" className="panel mt-6 text-red-800">
              {error}
            </p>
          )}
          {notice && (
            <p role="status" className="panel mt-6">
              {notice}
            </p>
          )}
          {id && !event ? (
            !error && (
              <p role="status" className="intro">
                Loading event…
              </p>
            )
          ) : (
            <>
              {event && (
                <section className="panel my-6">
                  <h2>{event.title}</h2>
                  <p className="mt-3 font-semibold">{event.status}</p>
                  <p className="mt-3">
                    Grouping: {formatDate(event.grouping_at, event.timezone)} ·{" "}
                    {event.timezone}
                  </p>
                  <p>
                    Confirmation deadline:{" "}
                    {formatDate(event.confirmation_deadline, event.timezone)} ·{" "}
                    {event.timezone}
                  </p>
                  <p className="my-3">
                    Review the schedule before publishing. Published events are
                    read-only in this release.
                  </p>
                  <div className="flex flex-wrap gap-4">
                    {event.status === "DRAFT" && (
                      <button
                        className="button"
                        disabled={busy}
                        onClick={() => void transition("publish")}
                      >
                        Publish event
                      </button>
                    )}
                    {[
                      "DRAFT",
                      "PUBLISHED",
                      "GROUPS_PROPOSED",
                      "GROUPS_FINALIZED",
                    ].includes(event.status) && (
                      <button
                        className="button"
                        disabled={busy}
                        onClick={() => void transition("cancel")}
                      >
                        Cancel event
                      </button>
                    )}
                    {["GROUPS_FINALIZED", "IN_PROGRESS"].includes(
                      event.status,
                    ) && (
                      <button
                        className="button"
                        disabled={busy}
                        onClick={() => void transition("complete")}
                      >
                        Mark event completed
                      </button>
                    )}
                    {[
                      "PUBLISHED",
                      "GROUPS_PROPOSED",
                      "GROUPS_FINALIZED",
                      "COMPLETED",
                    ].includes(event.status) && (
                      <Link className="button" href={`/events/${event.id}`}>
                        View public event
                      </Link>
                    )}
                  </div>
                  {["GROUPS_FINALIZED", "IN_PROGRESS"].includes(
                    event.status,
                  ) && (
                    <p className="mt-3 text-sm">
                      Complete after {formatDate(event.end_at, event.timezone)}{" "}
                      · {event.timezone}. This includes pending and confirmed
                      final members in future collaboration history, excluding
                      declined and withdrawn members. Completion does not verify
                      attendance.
                    </p>
                  )}
                  {event.status === "COMPLETED" && (
                    <p className="mt-3">
                      Completed event. The final roster is read-only and
                      contributes to future grouping history.
                    </p>
                  )}
                </section>
              )}
              {(!event || event.status === "DRAFT") && (
                <div className="mt-6">
                  <EventForm
                    key={event?.version ?? "new"}
                    initial={event ?? undefined}
                    csrfToken={account.csrf_token}
                    onSaved={(saved) => {
                      if (!id) router.push(`/organizer/events/${saved.id}`);
                      else {
                        setEvent(saved);
                        setNotice("Changes saved.");
                      }
                    }}
                  />
                </div>
              )}
              {event && <GroupingSchedule event={event} />}
              {event && (
                <GroupingPreview
                  key={`${event.id}:${account.user.id}`}
                  event={event}
                  csrfToken={account.csrf_token}
                  onGenerated={async () => {
                    setEvent(
                      await apiRequest<EventData>(
                        `/organizer/events/${event.id}`,
                      ),
                    );
                  }}
                />
              )}
              {event &&
                [
                  "GROUPS_FINALIZED",
                  "IN_PROGRESS",
                  "COMPLETED",
                  "CANCELLED",
                ].includes(event.status) && (
                  <TeamRoster
                    key={`${event.id}:${event.status}`}
                    event={event}
                    onChanged={async () => {
                      setEvent(
                        await apiRequest<EventData>(
                          `/organizer/events/${event.id}`,
                        ),
                      );
                    }}
                  />
                )}
              {event && (
                <OrganizerRoster
                  key={`${event.id}:${event.version}`}
                  eventId={event.id}
                />
              )}
            </>
          )}
        </>
      )}
    </main>
  );
}
