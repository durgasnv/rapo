"use client";

import { useEffect, useState } from "react";
import {
  RosterPage,
  apiRequest,
  formatDate,
  registrationLabel,
} from "../lib/api";

export function OrganizerRoster({ eventId }: { eventId: string }) {
  const [data, setData] = useState<RosterPage | null>(null);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    apiRequest<RosterPage>(
      `/events/${eventId}/registrations?offset=${offset}&limit=20`,
    )
      .then((result) => {
        if (active) setData(result);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load the roster.",
          );
      });
    return () => {
      active = false;
    };
  }, [eventId, offset, refresh]);
  function load(nextOffset = offset) {
    setData(null);
    setError("");
    setOffset(nextOffset);
    setRefresh((value) => value + 1);
  }
  return (
    <section className="panel mt-6" aria-label="Registration roster">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2>Registration roster</h2>
        <button
          className="underline"
          disabled={!data && !error}
          onClick={() => load()}
        >
          Refresh roster
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-4 text-red-800">
          {error}
        </p>
      )}
      {!data && !error && (
        <p role="status" className="mt-4">
          Loading roster…
        </p>
      )}
      {data && (
        <>
          <p className="mt-4">
            {data.registered_count} registered · {data.waitlisted_count}{" "}
            waitlisted
          </p>
          {data.total === 0 ? (
            <p className="mt-4">No registrations yet.</p>
          ) : (
            <>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">
                    Participant registrations in queue order, grouped by status
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col" className="p-3">
                        Participant
                      </th>
                      <th scope="col" className="p-3">
                        Status
                      </th>
                      <th scope="col" className="p-3">
                        Joined (UTC)
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((registration) => (
                      <tr
                        key={registration.id}
                        className="border-t border-stone-200"
                      >
                        <td className="p-3">{registration.name}</td>
                        <td className="p-3">
                          {registrationLabel(registration)}
                        </td>
                        <td className="p-3">
                          {formatDate(registration.registered_at, "UTC")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-4">
                <button
                  className="underline"
                  disabled={offset === 0}
                  onClick={() => load(Math.max(0, offset - 20))}
                >
                  Previous participants
                </button>
                <span>{data.total} registrations</span>
                <button
                  className="underline"
                  disabled={offset + data.items.length >= data.total}
                  onClick={() => load(offset + 20)}
                >
                  Next participants
                </button>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
