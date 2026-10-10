"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EventPage, apiRequest, formatDate } from "../lib/api";

export function EventList() {
  const [page, setPage] = useState<EventPage | null>(null);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState({ from: "", to: "" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    const query = new URLSearchParams({ limit: "12", offset: String(offset) });
    if (filters.from) query.set("date_from", filters.from);
    if (filters.to) query.set("date_to", filters.to);
    apiRequest<EventPage>(`/events?${query}`)
      .then((data) => {
        if (active) {
          setPage(data);
          setError("");
        }
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
  }, [offset, filters, attempt]);

  return (
    <>
      <form
        className="panel mb-6 flex flex-wrap items-end gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          const form = new FormData(event.currentTarget);
          setPage(null);
          setError("");
          setOffset(0);
          setFilters({
            from: String(form.get("from") || ""),
            to: String(form.get("to") || ""),
          });
        }}
      >
        <label>
          Starts on or after (UTC)
          <input name="from" type="date" />
        </label>
        <label>
          Starts on or before (UTC)
          <input name="to" type="date" />
        </label>
        <button className="button">Filter events</button>
      </form>
      {error ? (
        <div role="alert" className="panel">
          <p>{error}</p>
          <button
            className="button mt-4"
            onClick={() => {
              setError("");
              setAttempt((n) => n + 1);
            }}
          >
            Try again
          </button>
        </div>
      ) : !page ? (
        <p role="status">Loading events…</p>
      ) : (
        <>
          {page.items.length === 0 ? (
            <section className="panel">
              <h2>No events here yet.</h2>
              <p className="mt-3">
                Try different dates or check back when your community publishes
                an event.
              </p>
            </section>
          ) : (
            <div className="grid gap-5 md:grid-cols-2">
              {page.items.map((event) => (
                <article key={event.id} className="panel">
                  <p className="text-sm font-semibold text-emerald-800">
                    {formatDate(event.start_at, event.timezone)} ·{" "}
                    {event.timezone}
                  </p>
                  <h2 className="mt-3">
                    <Link href={`/events/${event.id}`}>{event.title}</Link>
                  </h2>
                  <p className="my-4 line-clamp-3 text-stone-600">
                    {event.description}
                  </p>
                  <p className="text-sm">
                    Teams of {event.min_team_size}–{event.max_team_size} ·{" "}
                    {event.capacity === null
                      ? "No fixed capacity"
                      : `Capacity ${event.capacity}`}
                  </p>
                  <Link
                    className="mt-5 inline-block font-semibold underline"
                    href={`/events/${event.id}`}
                  >
                    View event
                  </Link>
                </article>
              ))}
            </div>
          )}
          <nav
            aria-label="Event pages"
            className="mt-6 flex items-center gap-5"
          >
            <button
              className="button"
              disabled={offset === 0}
              onClick={() => {
                setPage(null);
                setOffset(Math.max(0, offset - 12));
              }}
            >
              Previous
            </button>
            <span>
              {page.total} event{page.total === 1 ? "" : "s"}
            </span>
            <button
              className="button"
              disabled={offset + 12 >= page.total}
              onClick={() => {
                setPage(null);
                setOffset(offset + 12);
              }}
            >
              Next
            </button>
          </nav>
        </>
      )}
    </>
  );
}
