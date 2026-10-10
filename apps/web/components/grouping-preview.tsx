"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, EventData, apiRequest } from "../lib/api";

type Preview = {
  id: string;
  seed: number;
  score: number;
  fairness: number;
  baseline_score: number;
  stale: boolean;
  stale_reason: string | null;
  teams: {
    number: number;
    score: number;
    explanation: string;
    members: { user_id: string; name: string }[];
  }[];
};

export function GroupingPreview({
  event,
  csrfToken,
  onGenerated,
}: {
  event: EventData;
  csrfToken: string;
  onGenerated: () => Promise<void>;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [seed, setSeed] = useState("0");
  const request = useRef<{ request_id: string; seed: number } | null>(null);
  useEffect(() => {
    let active = true;
    apiRequest<Preview | null>(`/events/${event.id}/grouping-runs/latest`)
      .then((result) => {
        if (active) setPreview(result);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load preview.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [event.id]);
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      setPreview(
        await apiRequest<Preview | null>(
          `/events/${event.id}/grouping-runs/latest`,
        ),
      );
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Could not refresh preview.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function generate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const value = Number(seed);
    if (!Number.isInteger(value) || value < 0 || value > 2147483647) {
      setError("Use a whole-number seed from 0 to 2147483647.");
      return;
    }
    setBusy(true);
    setError("");
    // Keep the same ID after a network failure: the server may already have committed.
    if (!request.current || request.current.seed !== value)
      request.current = { request_id: crypto.randomUUID(), seed: value };
    try {
      setPreview(
        await apiRequest<Preview>(
          `/events/${event.id}/grouping-runs`,
          {
            method: "POST",
            body: JSON.stringify(request.current),
          },
          csrfToken,
        ),
      );
      request.current = null;
      await onGenerated();
    } catch (failure) {
      if (failure instanceof ApiError) request.current = null;
      setError(
        failure instanceof Error
          ? failure.message
          : "Could not generate teams.",
      );
    } finally {
      setBusy(false);
    }
  }
  const active = ["PUBLISHED", "GROUPS_PROPOSED"].includes(event.status);
  return (
    <section className="panel mt-6" aria-label="Grouping preview">
      <h2>Grouping preview</h2>
      <p className="mt-3">
        After registration closes, propose balanced teams for up to 100
        registered participants. Waitlisted and withdrawn people are excluded.
      </p>
      {active && (
        <form
          onSubmit={(e) => void generate(e)}
          className="mt-4 flex flex-wrap items-end gap-4"
        >
          <label>
            Grouping seed
            <input
              className="mt-2 block"
              type="number"
              min="0"
              max="2147483647"
              step="1"
              required
              value={seed}
              disabled={busy || loading}
              onChange={(e) => setSeed(e.target.value)}
            />
          </label>
          <button className="button" disabled={busy || loading} type="submit">
            {busy ? "Working…" : "Generate team preview"}
          </button>
        </form>
      )}
      <button
        className="underline mt-4"
        disabled={busy || loading}
        onClick={() => void refresh()}
      >
        Refresh preview
      </button>
      {error && (
        <p role="alert" className="mt-4 text-red-800">
          {error}
        </p>
      )}
      {loading ? (
        <p role="status" className="mt-4">
          Loading preview…
        </p>
      ) : preview ? (
        <>
          {preview.stale && (
            <p role="alert" className="mt-4 text-red-800">
              Stale preview: {preview.stale_reason}
            </p>
          )}
          <p role="status" className="mt-4">
            Repeat score: {preview.score} · Random baseline:{" "}
            {preview.baseline_score} · Fairness penalty: {preview.fairness} ·
            Seed: {preview.seed}
          </p>
          <p className="mt-3 text-sm">
            Lower scores are better. Fairness breaks equal repeat scores. The
            search keeps the best valid result found; it does not guarantee the
            global optimum. These teams are proposals awaiting organizer review.
          </p>
          <ol className="mt-4 grid gap-4 sm:grid-cols-2">
            {preview.teams.map((team) => (
              <li
                key={team.number}
                className="rounded-lg border border-stone-200 p-4"
              >
                <h3 className="font-semibold">
                  Team {team.number} · {team.members.length} people
                </h3>
                <ul className="mt-2 list-inside list-disc">
                  {team.members.map((member) => (
                    <li key={member.user_id}>{member.name}</li>
                  ))}
                </ul>
                <p className="mt-3 text-sm">{team.explanation}</p>
              </li>
            ))}
          </ol>
        </>
      ) : (
        <p className="mt-4">No grouping preview yet.</p>
      )}
    </section>
  );
}
