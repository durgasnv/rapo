"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiRequest, formatDate } from "../lib/api";

type AttentionPage = {
  items: {
    event_id: string;
    title: string;
    start_at: string;
    timezone: string;
    status: string;
    reasons: string[];
  }[];
  total: number;
  offset: number;
  limit: number;
};

export function OrganizerAttention() {
  const [data, setData] = useState<AttentionPage | null>(null);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    apiRequest<AttentionPage>(`/organizer/attention?offset=${offset}&limit=20`)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load attention overview.",
          );
      });
    return () => {
      active = false;
    };
  }, [offset, refresh]);

  function load(nextOffset = 0) {
    setData(null);
    setError("");
    setOffset(nextOffset);
    setRefresh((value) => value + 1);
  }
  return (
    <section
      className="organizer-attention panel mb-6"
      aria-label="Events needing attention"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2>Events needing attention</h2>
        <button
          className="underline"
          disabled={!data && !error}
          onClick={() => load()}
        >
          Refresh attention
        </button>
      </div>
      <p className="mt-3 text-sm">
        Review proposals, grouping job problems, vacancies, and overdue
        confirmations. Open an event to see its current details and available
        actions.
      </p>
      {error && (
        <p role="alert" className="mt-4 text-red-800">
          {error}
        </p>
      )}
      {!data && !error && (
        <p role="status" className="mt-4">
          Loading attention overview…
        </p>
      )}
      {data && (
        <>
          <p className="mt-4 font-semibold">
            {data.total} {data.total === 1 ? "event needs" : "events need"}{" "}
            attention
          </p>
          {data.total === 0 ? (
            <p className="mt-3">No events need attention right now.</p>
          ) : (
            <>
              {data.items.length === 0 && (
                <p className="mt-3">
                  No events on this page. Refresh attention to return to the
                  first page.
                </p>
              )}
              <ul className="mt-4 divide-y divide-stone-200">
                {data.items.map((event) => (
                  <li key={event.event_id} className="py-4">
                    <h3 className="font-semibold">{event.title}</h3>
                    <p className="mt-2 text-sm">
                      {formatDate(event.start_at, event.timezone)} ·{" "}
                      {event.timezone} · {event.status.replaceAll("_", " ")}
                    </p>
                    <ul className="mt-2 list-inside list-disc">
                      {event.reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                    <Link
                      className="mt-3 inline-block underline"
                      href={`/organizer/events/${event.event_id}`}
                      aria-label={`Manage ${event.title}`}
                    >
                      Manage event
                    </Link>
                  </li>
                ))}
              </ul>
              <div className="mt-4 flex flex-wrap gap-4">
                <button
                  className="underline"
                  disabled={offset === 0}
                  onClick={() => load(Math.max(0, offset - 20))}
                >
                  Previous attention page
                </button>
                <button
                  className="underline"
                  disabled={offset + data.items.length >= data.total}
                  onClick={() => load(offset + 20)}
                >
                  Next attention page
                </button>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
