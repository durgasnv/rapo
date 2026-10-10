"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { EventData, apiRequest, formatDate } from "../lib/api";

export function EventDetail({ id }: { id: string }) {
  const [event, setEvent] = useState<EventData | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    apiRequest<EventData>(`/events/${id}`)
      .then((data) => {
        if (active) setEvent(data);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load this event.",
          );
      });
    return () => {
      active = false;
    };
  }, [id]);
  return (
    <main className="page-shell">
      <Link className="underline" href="/events">
        All events
      </Link>
      {error ? (
        <p role="alert" className="panel mt-6">
          {error}
        </p>
      ) : !event ? (
        <p role="status" className="mt-6">
          Loading event…
        </p>
      ) : (
        <>
          <h1 className="mt-8">{event.title}</h1>
          <p className="intro">
            {formatDate(event.start_at, event.timezone)} · {event.timezone}
          </p>
          <section className="panel">
            <p className="whitespace-pre-wrap">{event.description}</p>
            <dl className="mt-6 grid gap-4 sm:grid-cols-2">
              <div>
                <dt>Location</dt>
                <dd>{event.location || "To be announced"}</dd>
              </div>
              <div>
                <dt>Event ends</dt>
                <dd>{formatDate(event.end_at, event.timezone)}</dd>
              </div>
              <div>
                <dt>Registration opens</dt>
                <dd>
                  {formatDate(event.registration_opens_at, event.timezone)}
                </dd>
              </div>
              <div>
                <dt>Registration closes</dt>
                <dd>
                  {formatDate(event.registration_closes_at, event.timezone)}
                </dd>
              </div>
              <div>
                <dt>Team size</dt>
                <dd>
                  {event.min_team_size}–{event.max_team_size}
                </dd>
              </div>
              <div>
                <dt>Capacity</dt>
                <dd>{event.capacity ?? "No fixed capacity"}</dd>
              </div>
            </dl>
            <p className="mt-6 text-stone-600">
              Participant registration will be available in the next release.
            </p>
          </section>
        </>
      )}
    </main>
  );
}
