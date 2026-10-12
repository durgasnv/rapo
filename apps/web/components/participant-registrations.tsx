"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  MyRegistration,
  RegistrationPage,
  apiRequest,
  formatDate,
  registrationLabel,
} from "../lib/api";

export function ParticipantRegistrations() {
  const [data, setData] = useState<RegistrationPage<MyRegistration> | null>(
    null,
  );
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    apiRequest<RegistrationPage<MyRegistration>>(
      `/me/registrations?offset=${offset}&limit=20`,
    )
      .then((result) => {
        if (active) setData(result);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load your registrations.",
          );
      });
    return () => {
      active = false;
    };
  }, [offset, refresh]);
  function load(nextOffset = offset) {
    setData(null);
    setError("");
    setOffset(nextOffset);
    setRefresh((value) => value + 1);
  }
  return (
    <section className="panel mt-6" aria-label="Your registrations">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2>Your registrations</h2>
        <button
          className="underline"
          disabled={!data && !error}
          onClick={() => load()}
        >
          Refresh registrations
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-4 text-red-800">
          {error}
        </p>
      )}
      {!data && !error && (
        <p role="status" className="mt-4">
          Loading registrations…
        </p>
      )}
      {data && (
        <>
          {data.total === 0 ? (
            <p className="mt-4">You haven’t registered for any events yet.</p>
          ) : (
            <>
              <ul className="mt-4 divide-y divide-stone-200">
                {data.items.map((registration) => (
                  <li key={registration.id} className="py-4">
                    <h3 className="font-semibold">
                      {[
                        "PUBLISHED",
                        "GROUPS_PROPOSED",
                        "GROUPS_FINALIZED",
                        "COMPLETED",
                      ].includes(registration.event.status) ? (
                        <Link
                          className="underline"
                          href={`/events/${registration.event_id}`}
                        >
                          {registration.event.title}
                        </Link>
                      ) : (
                        registration.event.title
                      )}
                    </h3>
                    <p className="mt-2">
                      {registration.event.status === "CANCELLED"
                        ? "Event cancelled"
                        : registration.event.status === "COMPLETED"
                          ? "Event completed"
                          : registrationLabel(registration)}
                    </p>
                    {registration.event.status === "GROUPS_FINALIZED" &&
                      registration.status === "REGISTERED" && (
                        <Link
                          className="underline"
                          href={`/events/${registration.event_id}`}
                        >
                          View your team and confirm
                        </Link>
                      )}
                    <p className="mt-2 text-sm">
                      {formatDate(
                        registration.event.start_at,
                        registration.event.timezone,
                      )}{" "}
                      · {registration.event.timezone}
                    </p>
                  </li>
                ))}
              </ul>
              <div className="mt-4 flex flex-wrap items-center gap-4">
                <button
                  className="underline"
                  disabled={offset === 0}
                  onClick={() => load(Math.max(0, offset - 20))}
                >
                  Previous registrations
                </button>
                <span>{data.total} registrations</span>
                <button
                  className="underline"
                  disabled={offset + data.items.length >= data.total}
                  onClick={() => load(offset + 20)}
                >
                  Next registrations
                </button>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
