"use client";

import { FormEvent, useState } from "react";
import { EventData, apiRequest } from "../lib/api";

const dates = [
  ["start_at", "Event starts"],
  ["end_at", "Event ends"],
  ["registration_opens_at", "Registration opens"],
  ["registration_closes_at", "Registration closes"],
  ["grouping_at", "Grouping (leave blank for automatic schedule)"],
  ["confirmation_deadline", "Confirmation deadline"],
] as const;

export function EventForm({
  initial,
  csrfToken,
  onSaved,
}: {
  initial?: EventData;
  csrfToken: string;
  onSaved: (event: EventData) => void;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body: Record<string, unknown> = {
      title: form.get("title"),
      description: form.get("description"),
      location: form.get("location"),
      timezone: form.get("timezone"),
      min_team_size: Number(form.get("min_team_size")),
      max_team_size: Number(form.get("max_team_size")),
      capacity: form.get("capacity") ? Number(form.get("capacity")) : null,
      ...(initial ? { version: initial.version } : {}),
    };
    for (const [key] of dates) {
      const value = String(form.get(key) || "");
      const timestamp = value ? new Date(`${value}Z`) : null;
      // JavaScript dates have millisecond precision; retain the API's original
      // timestamp (including microseconds) when this input has not changed.
      body[key] =
        timestamp &&
        initial &&
        timestamp.getTime() === new Date(initial[key]).getTime()
          ? initial[key]
          : (timestamp?.toISOString() ?? null);
    }
    setError("");
    setBusy(true);
    try {
      const saved = await apiRequest<EventData>(
        initial ? `/events/${initial.id}` : "/events",
        { method: initial ? "PATCH" : "POST", body: JSON.stringify(body) },
        csrfToken,
      );
      onSaved(saved);
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "Could not save event.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="panel form-stack" onSubmit={(event) => void submit(event)}>
      <label>
        Event title
        <input
          name="title"
          required
          maxLength={200}
          defaultValue={initial?.title}
        />
      </label>
      <label>
        Description
        <textarea
          name="description"
          required
          maxLength={10_000}
          defaultValue={initial?.description}
        />
      </label>
      <label>
        Location or meeting link
        <input
          name="location"
          maxLength={500}
          defaultValue={initial?.location}
        />
      </label>
      <label>
        Display timezone (IANA name)
        <input
          name="timezone"
          required
          placeholder="Asia/Kolkata"
          defaultValue={initial?.timezone ?? "UTC"}
        />
      </label>
      <p className="text-sm text-stone-600">
        Enter all schedule times below in UTC. Event pages display them in your
        chosen timezone.
      </p>
      <div className="grid gap-5 sm:grid-cols-2">
        {dates.map(([key, title]) => (
          <label key={key}>
            {title} (UTC)
            <input
              type="datetime-local"
              step="any"
              name={key}
              required={key !== "grouping_at"}
              defaultValue={
                initial ? new Date(initial[key]).toISOString().slice(0, -1) : ""
              }
            />
          </label>
        ))}
      </div>
      <div className="grid gap-5 sm:grid-cols-3">
        <label>
          Minimum team size
          <input
            name="min_team_size"
            type="number"
            min={1}
            max={1000}
            required
            defaultValue={initial?.min_team_size ?? 3}
          />
        </label>
        <label>
          Maximum team size
          <input
            name="max_team_size"
            type="number"
            min={1}
            max={1000}
            required
            defaultValue={initial?.max_team_size ?? 5}
          />
        </label>
        <label>
          Capacity (blank for unlimited)
          <input
            name="capacity"
            type="number"
            min={1}
            defaultValue={initial?.capacity ?? ""}
          />
        </label>
      </div>
      {error && (
        <p role="alert" className="text-red-800">
          {error}
        </p>
      )}
      <button className="button" disabled={busy}>
        {busy ? "Saving…" : initial ? "Save changes" : "Save draft"}
      </button>
    </form>
  );
}
