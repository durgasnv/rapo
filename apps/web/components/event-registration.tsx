"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  AccountSession,
  EventData,
  RegistrationState,
  apiRequest,
  registrationLabel,
} from "../lib/api";
import { useAccount } from "./account-provider";

export function EventRegistration({ event }: { event: EventData }) {
  const { account, loading } = useAccount();
  if (loading)
    return (
      <p className="mt-6" role="status">
        Checking your account…
      </p>
    );
  if (!account)
    return (
      <p className="mt-6">
        <Link className="underline" href="/sign-in">
          Sign in
        </Link>{" "}
        to register or join the waitlist.
      </p>
    );
  return (
    <RegistrationControls
      key={`${event.id}:${account.user.id}`}
      event={event}
      account={account}
    />
  );
}

function RegistrationControls({
  event,
  account,
}: {
  event: EventData;
  account: AccountSession;
}) {
  const [data, setData] = useState<RegistrationState | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    apiRequest<RegistrationState>(`/events/${event.id}/registration`)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load registration.",
          );
      });
    return () => {
      active = false;
    };
  }, [event.id, refresh]);

  async function update(action: "join" | "withdraw") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await apiRequest<RegistrationState>(
        `/events/${event.id}/${action === "join" ? "register" : "registration"}`,
        { method: action === "join" ? "POST" : "DELETE" },
        account.csrf_token,
      );
      setData(result);
      setNotice(
        action === "withdraw"
          ? "Your registration has been withdrawn."
          : "Your registration has been saved.",
      );
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Could not update registration.",
      );
    } finally {
      setBusy(false);
    }
  }
  const active = data?.registration && data.registration.status !== "CANCELLED";
  return (
    <section
      className="mt-8 border-t border-stone-200 pt-6"
      aria-label="Your registration"
    >
      <h2>Your registration</h2>
      {error && (
        <p role="alert" className="mt-4 text-red-800">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="mt-4">
          {notice}
        </p>
      )}
      {!data && !error && (
        <p role="status" className="mt-4">
          Loading registration…
        </p>
      )}
      {data && (
        <>
          <p className="mt-4 font-semibold" aria-live="polite">
            {data.event_status === "CANCELLED"
              ? "Event cancelled"
              : data.registration
                ? registrationLabel(data.registration)
                : "You haven’t registered yet."}
          </p>
          <p className="mt-2">
            {data.registered_count} registered · {data.waitlisted_count}{" "}
            waitlisted ·{" "}
            {data.capacity === null
              ? "No fixed capacity"
              : `${data.capacity} seats`}
          </p>
          {!active &&
            ["PUBLISHED", "GROUPS_PROPOSED"].includes(data.event_status) &&
            !data.registration_open && (
              <p className="mt-3">
                Registration is not open. Check the schedule above.
              </p>
            )}
          {active &&
            !data.withdrawal_open &&
            ["PUBLISHED", "GROUPS_PROPOSED"].includes(data.event_status) && (
              <p className="mt-3">
                Self-service withdrawal closed at the grouping time.
              </p>
            )}
          <div className="mt-4 flex flex-wrap gap-4">
            {!active && data.registration_open && (
              <button
                className="button"
                disabled={busy}
                onClick={() => void update("join")}
              >
                {data.capacity !== null &&
                data.registered_count >= data.capacity
                  ? "Join waitlist"
                  : data.registration
                    ? "Register again"
                    : "Register for event"}
              </button>
            )}
            {active && data.withdrawal_open && (
              <button
                className="button"
                disabled={busy}
                onClick={() => void update("withdraw")}
              >
                Withdraw registration
              </button>
            )}
          </div>
        </>
      )}
      <button
        className="mt-4 underline"
        disabled={busy || (!data && !error)}
        onClick={() => {
          setData(null);
          setError("");
          setNotice("");
          setRefresh((value) => value + 1);
        }}
      >
        Refresh registration
      </button>
      <p className="mt-3 text-sm text-stone-600">
        Refresh to check for a waitlist promotion. Withdrawing and rejoining
        puts you at the back of the queue.
      </p>
    </section>
  );
}
