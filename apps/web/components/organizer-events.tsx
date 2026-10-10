"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EventData, apiRequest, formatDate } from "../lib/api";
import { useAccount } from "./account-provider";

export function OrganizerEvents() {
  const { account, loading } = useAccount();
  const [events, setEvents] = useState<EventData[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (account?.user.role !== "organizer") return;
    let active = true;
    apiRequest<EventData[]>("/organizer/events")
      .then((data) => {
        if (active) setEvents(data);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load events.",
          );
      });
    return () => {
      active = false;
    };
  }, [account]);
  return (
    <main className="page-shell">
      <h1>Your community. Your events.</h1>
      {loading ? (
        <p className="intro" role="status">
          Loading your account…
        </p>
      ) : !account ? (
        <p className="intro">
          <Link href="/sign-in" className="underline">
            Sign in
          </Link>{" "}
          to manage events.
        </p>
      ) : account.user.role !== "organizer" ? (
        <p className="intro">
          Organizer access is required. Contact the person running your rapo.
          community.
        </p>
      ) : (
        <>
          <p className="intro">
            Create a draft, review the schedule, and publish when you’re ready.
          </p>
          <Link className="button mb-6" href="/organizer/events/new">
            Create event
          </Link>
          {error ? (
            <p role="alert" className="panel">
              {error}
            </p>
          ) : !events ? (
            <p role="status">Loading events…</p>
          ) : events.length === 0 ? (
            <p className="panel">You haven’t created an event yet.</p>
          ) : (
            <div className="grid gap-5 md:grid-cols-2">
              {events.map((event) => (
                <article key={event.id} className="panel">
                  <p className="text-sm font-semibold text-emerald-800">
                    {event.status}
                  </p>
                  <h2 className="mt-3">{event.title}</h2>
                  <p className="my-4">
                    {formatDate(event.start_at, event.timezone)} ·{" "}
                    {event.timezone}
                  </p>
                  <Link
                    className="underline"
                    href={`/organizer/events/${event.id}`}
                  >
                    Manage event
                  </Link>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}
