"use client";

import { useEffect, useState } from "react";
import { apiRequest, EventData, formatDate } from "../lib/api";

type Job = {
  status: string;
  attempts: number;
  message: string;
  next_attempt_at: string | null;
};

export function GroupingSchedule({ event }: { event: EventData }) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    apiRequest<Job>(`/events/${event.id}/grouping-job`)
      .then((result) => {
        if (active) setJob(result);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load scheduled grouping status.",
          );
      });
    return () => {
      active = false;
    };
  }, [event.id, event.version, refresh]);
  return (
    <section className="panel mt-6" aria-label="Scheduled grouping">
      <h2>Scheduled grouping</h2>
      <p className="mt-3">
        Scheduled for {formatDate(event.grouping_at, event.timezone)} ·{" "}
        {event.timezone}
      </p>
      {error && (
        <p role="alert" className="mt-3 text-red-800">
          {error}
        </p>
      )}
      {!job && !error && <p role="status">Loading schedule…</p>}
      {job && (
        <>
          <p className="mt-3 font-semibold">
            {job.status.replaceAll("_", " ")} · {job.attempts} attempts
          </p>
          <p className="mt-2">{job.message}</p>
          {job.next_attempt_at &&
            ["FAILED", "BLOCKED"].includes(job.status) && (
              <p className="mt-2">
                Next retry after{" "}
                {formatDate(job.next_attempt_at, event.timezone)} ·{" "}
                {event.timezone}
              </p>
            )}
        </>
      )}
      <button
        className="mt-4 underline"
        onClick={() => {
          setError("");
          setRefresh((v) => v + 1);
        }}
      >
        Refresh schedule
      </button>
      <p className="mt-3 text-sm">
        Refresh the grouping preview to see a newly generated proposal.
        Finalization requires your approval.
      </p>
    </section>
  );
}
