"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { EventPage, apiRequest, formatDate } from "../lib/api";

export function EventList() {
  const [page, setPage] = useState<EventPage | null>(null);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState({ from: "", to: "", status: "" });
  const [sort, setSort] = useState("soonest");
  const [filterError, setFilterError] = useState("");
  const filterMenu = useRef<HTMLDetailsElement>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    const query = new URLSearchParams({
      limit: "12",
      offset: String(offset),
      sort,
    });
    if (filters.from) query.set("date_from", filters.from);
    if (filters.to) query.set("date_to", filters.to);
    if (filters.status) query.set("status", filters.status);
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
  }, [offset, filters, sort, attempt]);

  const filterCount = Object.values(filters).filter(Boolean).length;

  return (
    <>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <p className="text-sm text-stone-600" aria-live="polite">
          {page
            ? `${page.total} event${page.total === 1 ? "" : "s"}`
            : "Community events"}
        </p>
        <div className="flex flex-wrap items-center gap-4">
          <details ref={filterMenu} className="relative">
            <summary className="cursor-pointer rounded-full border border-stone-300 px-5 py-2 text-sm font-semibold">
              Filter{filterCount > 0 ? ` (${filterCount})` : ""}
            </summary>
            <form
              aria-label="Filter events"
              className="panel absolute left-0 z-10 mt-2 grid w-[min(20rem,calc(100vw-3rem))] gap-4 shadow-lg"
              onSubmit={(event) => {
                event.preventDefault();
                const form = new FormData(event.currentTarget);
                const next = {
                  from: String(form.get("from") || ""),
                  to: String(form.get("to") || ""),
                  status: String(form.get("status") || ""),
                };
                if (next.from && next.to && next.from > next.to) {
                  setFilterError("Start date must not be after end date.");
                  return;
                }
                setFilterError("");
                setPage(null);
                setError("");
                setOffset(0);
                setFilters(next);
                if (filterMenu.current) filterMenu.current.open = false;
              }}
              onReset={() => {
                setFilterError("");
                setError("");
                setPage(null);
                setOffset(0);
                setFilters({ from: "", to: "", status: "" });
                if (filterMenu.current) filterMenu.current.open = false;
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
              <label>
                Event status
                <select name="status" defaultValue="">
                  <option value="">All available events</option>
                  <option value="PUBLISHED">Published</option>
                  <option value="GROUPS_PROPOSED">Groups proposed</option>
                  <option value="GROUPS_FINALIZED">Groups finalized</option>
                </select>
              </label>
              {filterError && (
                <p role="alert" className="text-red-800">
                  {filterError}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-4">
                <button className="button">Apply filters</button>
                <button type="reset" className="underline">
                  Clear filters
                </button>
              </div>
            </form>
          </details>
          <label className="flex items-center gap-2 text-sm">
            Sort
            <select
              value={sort}
              onChange={(event) => {
                setPage(null);
                setError("");
                setOffset(0);
                setSort(event.target.value);
              }}
            >
              <option value="soonest">Soonest first</option>
              <option value="latest">Latest first</option>
              <option value="title">Event name A–Z</option>
            </select>
          </label>
        </div>
      </div>
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
