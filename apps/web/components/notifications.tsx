"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiRequest, formatDate } from "../lib/api";
import { useAccount } from "./account-provider";

type Notice = {
  id: string;
  event_id: string;
  kind: string;
  message: string;
  destination: "ACCOUNT" | "EVENT" | "ORGANIZER";
  created_at: string;
  read_at: string | null;
};
type Page = {
  items: Notice[];
  total: number;
  unread_count: number;
  offset: number;
  limit: number;
};

export function Notifications() {
  const { account } = useAccount();
  const [data, setData] = useState<Page | null>(null);
  const [offset, setOffset] = useState(0);
  const [unread, setUnread] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    apiRequest<Page>(
      `/me/notifications?offset=${offset}&limit=20&unread_only=${unread}`,
    )
      .then((result) => {
        if (active) setData(result);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load notifications.",
          );
      });
    return () => {
      active = false;
    };
  }, [offset, unread, refresh]);
  async function markRead(id: string) {
    if (!account) return;
    setBusy(true);
    setError("");
    try {
      await apiRequest(
        `/me/notifications/${id}/read`,
        { method: "POST" },
        account.csrf_token,
      );
      setRefresh((v) => v + 1);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Could not mark notification as read.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="panel mt-6"
      aria-label="Your notifications"
      id="notifications"
    >
      <h2>Your notifications</h2>
      {data && (
        <p className="mt-3" aria-live="polite">
          {data.unread_count} unread notifications
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-4">
        <button
          className="underline"
          disabled={busy}
          onClick={() => {
            setError("");
            setRefresh((v) => v + 1);
          }}
        >
          Refresh notifications
        </button>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={unread}
            disabled={busy}
            onChange={(e) => {
              setUnread(e.target.checked);
              setOffset(0);
              setError("");
              setData(null);
            }}
          />
          Unread only
        </label>
      </div>
      {error && (
        <p role="alert" className="mt-4 text-red-800">
          {error}
        </p>
      )}
      {!data && !error && (
        <p role="status" className="mt-4">
          Loading notifications…
        </p>
      )}
      {data && (
        <>
          {data.items.length === 0 && (
            <p className="mt-4">No notifications on this page.</p>
          )}
          <ul className="mt-4 grid gap-4">
            {data.items.map((n) => (
              <li key={n.id} className="rounded-lg border border-stone-200 p-4">
                <p className={n.read_at ? "" : "font-semibold"}>{n.message}</p>
                <p className="mt-2 text-sm">
                  {formatDate(n.created_at, "UTC")} · UTC ·{" "}
                  {n.read_at ? "Read" : "Unread"}
                </p>
                <div className="mt-3 flex gap-4">
                  <Link
                    className="underline"
                    href={
                      n.destination === "ORGANIZER"
                        ? `/organizer/events/${n.event_id}`
                        : n.destination === "EVENT"
                          ? `/events/${n.event_id}`
                          : "/dashboard"
                    }
                  >
                    View update
                  </Link>
                  {!n.read_at && (
                    <button
                      className="underline"
                      disabled={busy}
                      onClick={() => void markRead(n.id)}
                    >
                      Mark as read
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex gap-4">
            <button
              className="underline"
              disabled={busy || offset === 0}
              onClick={() => {
                setOffset((v) => Math.max(0, v - 20));
                setData(null);
                setError("");
              }}
            >
              Previous notifications
            </button>
            <button
              className="underline"
              disabled={busy || offset + 20 >= data.total}
              onClick={() => {
                setOffset((v) => v + 20);
                setData(null);
                setError("");
              }}
            >
              Next notifications
            </button>
          </div>
        </>
      )}
      <p className="mt-3 text-sm">Refresh to check for new updates.</p>
    </section>
  );
}
