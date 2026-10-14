"use client";

import { useEffect, useState } from "react";
import { apiRequest, formatDate } from "../lib/api";

type AuditPage = {
  items: {
    id: string;
    action: string;
    description: string;
    actor_name: string;
    created_at: string;
  }[];
  total: number;
  offset: number;
  limit: number;
};

export function EventAudit({
  eventId,
  timezone,
}: {
  eventId: string;
  timezone: string;
}) {
  const [data, setData] = useState<AuditPage | null>(null);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    apiRequest<AuditPage>(
      `/organizer/events/${eventId}/audit?offset=${offset}&limit=20`,
    )
      .then((result) => {
        if (active) setData(result);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load event activity.",
          );
      });
    return () => {
      active = false;
    };
  }, [eventId, offset, refresh]);

  function load(nextOffset = 0) {
    setData(null);
    setError("");
    setOffset(nextOffset);
    setRefresh((value) => value + 1);
  }
  return (
    <section className="event-activity panel mt-6" aria-label="Event activity">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2>Event activity</h2>
        <button
          className="underline"
          disabled={!data && !error}
          onClick={() => load()}
        >
          Refresh activity
        </button>
      </div>
      <p className="mt-3 text-sm">
        Recorded actions, newest first · {timezone}. Member and organizer names
        reflect current profiles.
      </p>
      {error && (
        <p role="alert" className="mt-4 text-red-800">
          {error}
        </p>
      )}
      {!data && !error && (
        <p role="status" className="mt-4">
          Loading event activity…
        </p>
      )}
      {data && (
        <>
          <p className="mt-4">
            {data.total} recorded {data.total === 1 ? "action" : "actions"}
          </p>
          {data.total === 0 ? (
            <p className="mt-3">No activity recorded yet.</p>
          ) : (
            <>
              {data.items.length === 0 && (
                <p className="mt-3">
                  No activity on this page. Refresh activity to return to the
                  newest actions.
                </p>
              )}
              <ol className="mt-4 divide-y divide-stone-200">
                {data.items.map((entry) => (
                  <li key={entry.id} className="py-4">
                    <h3 className="font-semibold">{entry.description}</h3>
                    <p className="mt-2">By {entry.actor_name}</p>
                    <time
                      className="mt-2 block text-sm"
                      dateTime={entry.created_at}
                    >
                      {formatDate(entry.created_at, timezone)}
                    </time>
                  </li>
                ))}
              </ol>
              <div className="mt-4 flex flex-wrap gap-4">
                <button
                  className="underline"
                  disabled={offset === 0}
                  onClick={() => load(Math.max(0, offset - 20))}
                >
                  Newer activity
                </button>
                <button
                  className="underline"
                  disabled={offset + data.items.length >= data.total}
                  onClick={() => load(offset + 20)}
                >
                  Older activity
                </button>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
