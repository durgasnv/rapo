"use client";

import { useEffect, useRef, useState } from "react";
import {
  AccountSession,
  ApiError,
  EventData,
  FinalRoster,
  apiRequest,
  apiUrl,
  formatDate,
} from "../lib/api";
import { useAccount } from "./account-provider";

const refreshWarningMessage =
  "Change saved, but event details couldn’t refresh. Refresh the page to reload them.";

export function TeamRoster({
  event,
  onChanged,
}: {
  event: EventData;
  onChanged?: () => Promise<void>;
}) {
  const { account, loading } = useAccount();
  if (loading) return <p role="status">Loading team access…</p>;
  if (!account)
    return <p className="mt-4">Sign in to view your team assignment.</p>;
  return (
    <RosterControls
      key={`${event.id}:${account.user.id}`}
      event={event}
      account={account}
      onChanged={onChanged}
    />
  );
}

function RosterControls({
  event,
  account,
  onChanged,
}: {
  event: EventData;
  account: AccountSession;
  onChanged?: () => Promise<void>;
}) {
  const [data, setData] = useState<FinalRoster | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{
    teamId: string;
    message: string;
    error: boolean;
  } | null>(null);
  const [refreshWarning, setRefreshWarning] = useState<{
    teamId?: string;
  } | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const pending = useRef<{ key: string; body: Record<string, unknown> } | null>(
    null,
  );
  const owner =
    account.user.role === "organizer" && account.user.id === event.organizer_id;
  useEffect(() => {
    let active = true;
    apiRequest<FinalRoster>(`/events/${event.id}/teams`)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((failure: unknown) => {
        if (active)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load teams.",
          );
      })
      .finally(() => {
        if (active) setLoaded(true);
      });
    return () => {
      active = false;
    };
  }, [event.id, refresh]);
  async function change(
    path: string,
    values: Record<string, unknown> = {},
    ownerAction = false,
    teamId?: string,
  ) {
    if (!data) return;
    setBusy(true);
    setError("");
    setFeedback(null);
    setRefreshWarning(null);
    let body = values;
    if (ownerAction) {
      body = { ...values, version: data.version };
      const key = path + JSON.stringify(body);
      if (pending.current?.key !== key)
        pending.current = {
          key,
          body: { ...body, request_id: crypto.randomUUID() },
        };
      body = pending.current.body;
    }
    try {
      const result = await apiRequest<FinalRoster>(
        `/events/${event.id}/teams${path}`,
        { method: "POST", body: JSON.stringify(body) },
        account.csrf_token,
      );
      setData(result);
      if (teamId) {
        const updated = result.teams.find((team) => team.id === teamId);
        const pendingCount =
          updated?.members.filter((m) => m.status === "PENDING").length ?? 0;
        let message = path.endsWith("/continue")
          ? `Current size approved: ${updated?.target_size} active ${updated?.target_size === 1 ? "member" : "members"}.`
          : "Vacancy filled from the waitlist.";
        if (updated?.status === "NEEDS_ATTENTION")
          message += ` Still needs attention: ${updated.reasons.join(" ")}`;
        else if (pendingCount)
          message += ` Awaiting confirmation from ${pendingCount} ${pendingCount === 1 ? "member" : "members"}.`;
        else message += " Team is ready.";
        setFeedback({ teamId, message, error: false });
      }
      pending.current = null;
      // The mutation has committed; a failed follow-up read must not report save failure.
      try {
        await onChanged?.();
      } catch {
        setRefreshWarning({ teamId });
      }
    } catch (failure) {
      if (failure instanceof ApiError) pending.current = null;
      const message =
        failure instanceof Error ? failure.message : "Could not update teams.";
      if (teamId) setFeedback({ teamId, message, error: true });
      else setError(message);
    } finally {
      setBusy(false);
    }
  }
  async function download() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `${apiUrl}/events/${event.id}/teams/export`,
        {
          credentials: "include",
          cache: "no-store",
          signal: AbortSignal.timeout(15000),
        },
      );
      if (!response.ok)
        throw new Error(
          "Could not export the roster. Refresh your account and try again.",
        );
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `rapo-${event.id}-teams.csv`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "Could not export roster.",
      );
    } finally {
      setBusy(false);
    }
  }
  const activeMembers =
    data?.teams.flatMap((team) =>
      team.members.filter((m) => ["PENDING", "CONFIRMED"].includes(m.status)),
    ) ?? [];
  return (
    <section
      className="panel mt-6"
      aria-label={owner ? "Final team roster" : "Your team"}
    >
      <h2>{owner ? "Final team roster" : "Your team"}</h2>
      <div className="mt-4 flex flex-wrap gap-4">
        <button
          className="underline"
          disabled={busy || !loaded}
          onClick={() => {
            setError("");
            setFeedback(null);
            setRefreshWarning(null);
            setRefresh((v) => v + 1);
          }}
        >
          Refresh teams
        </button>
        {owner && (
          <button
            className="underline"
            disabled={busy || !data}
            onClick={() => void download()}
          >
            Export teams CSV
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-4 text-red-800">
          {error}
        </p>
      )}
      {refreshWarning && !refreshWarning.teamId && (
        <p role="alert" className="mt-4 text-amber-800">
          {refreshWarningMessage}
        </p>
      )}
      {!loaded && (
        <p role="status" className="mt-4">
          Loading teams…
        </p>
      )}
      {data && (
        <>
          <p className="mt-4">
            Event: {data.event_status.replaceAll("_", " ")} · Confirmation
            deadline: {formatDate(data.confirmation_deadline, event.timezone)} ·{" "}
            {event.timezone}
          </p>
          {data.teams.length === 0 && (
            <p className="mt-4">
              {data.own_status
                ? `Your assignment is ${data.own_status.toLowerCase()}.`
                : "No finalized team assignment yet."}
            </p>
          )}
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {data.teams.map((team) => {
              const own = team.members.find(
                (member) => member.user_id === account.user.id,
              );
              const ownActive =
                own && ["PENDING", "CONFIRMED"].includes(own.status);
              const count = team.members.filter((m) =>
                ["PENDING", "CONFIRMED"].includes(m.status),
              ).length;
              const validSize =
                count >= event.min_team_size && count <= event.max_team_size;
              const vacancy = count < team.target_size;
              const approvalHelp = !validSize
                ? count < event.min_team_size
                  ? `Cannot approve: at least ${event.min_team_size} active members required. Fill the vacancy or reassign members.`
                  : `Cannot approve: at most ${event.max_team_size} active members allowed. Reassign members.`
                : !vacancy
                  ? "Current size already approved. Member confirmations are separate."
                  : "Approve continuing with this smaller team. Members must still confirm.";
              return (
                <section
                  key={team.id}
                  className="rounded-lg border border-stone-200 p-4"
                  aria-label={`Final team ${team.number}`}
                >
                  <h3 className="font-semibold">
                    Team {team.number} · {team.status.replaceAll("_", " ")}
                  </h3>
                  <p className="mt-2 text-sm">
                    {count} active · Target {team.target_size} · Allowed{" "}
                    {event.min_team_size}–{event.max_team_size}
                  </p>
                  {feedback?.teamId === team.id && (
                    <p
                      role={feedback.error ? "alert" : "status"}
                      className={`mt-2 ${feedback.error ? "text-red-800" : "text-emerald-800"}`}
                    >
                      {feedback.message}
                    </p>
                  )}
                  {refreshWarning?.teamId === team.id && (
                    <p role="alert" className="mt-2 text-amber-800">
                      {refreshWarningMessage}
                    </p>
                  )}
                  {team.reasons.map((reason) => (
                    <p key={reason} className="mt-2 text-red-800">
                      {reason}
                    </p>
                  ))}
                  <ul className="mt-3 list-inside list-disc">
                    {team.members.map((member) => (
                      <li key={member.user_id}>
                        {member.name} · {member.status.toLowerCase()}
                      </li>
                    ))}
                  </ul>
                  {ownActive && (
                    <div className="mt-4 flex flex-wrap gap-3">
                      {data.confirmation_open && (
                        <>
                          <button
                            className="button"
                            disabled={busy || own.status === "CONFIRMED"}
                            onClick={() =>
                              void change(`/${team.id}/confirm`, {
                                decision: "confirm",
                                team_version: team.version,
                              })
                            }
                          >
                            {own.status === "CONFIRMED"
                              ? "Confirmed"
                              : "Confirm my team"}
                          </button>
                          <button
                            className="underline"
                            disabled={busy}
                            onClick={() =>
                              void change(`/${team.id}/confirm`, {
                                decision: "decline",
                                team_version: team.version,
                              })
                            }
                          >
                            Decline assignment
                          </button>
                        </>
                      )}
                      {data.withdrawal_open && (
                        <button
                          className="underline"
                          disabled={busy}
                          onClick={() => void change("/withdraw")}
                        >
                          Withdraw from team
                        </button>
                      )}
                    </div>
                  )}
                  {owner && data.withdrawal_open && (
                    <div className="mt-4 flex flex-wrap gap-3">
                      <button
                        className="button"
                        disabled={busy || !data.confirmation_open}
                        onClick={() =>
                          void change(`/${team.id}/replace`, {}, true, team.id)
                        }
                      >
                        Fill vacancy from waitlist
                      </button>
                      <button
                        className="team-approval underline"
                        disabled={busy || !validSize || !vacancy}
                        aria-describedby={`approval-help-${team.id}`}
                        onClick={() =>
                          void change(`/${team.id}/continue`, {}, true, team.id)
                        }
                      >
                        Approve current team size
                      </button>
                      <p
                        id={`approval-help-${team.id}`}
                        className="w-full text-sm"
                      >
                        {approvalHelp}
                      </p>
                    </div>
                  )}
                </section>
              );
            })}
          </div>
          <p className="mt-4 text-sm">
            Changing teammates requires affected members to confirm again. A
            missed deadline keeps members unconfirmed; it does not remove them
            automatically.
          </p>
          {owner && data.withdrawal_open && (
            <>
              <form
                key={data.confirmation_deadline}
                className="mt-6 flex flex-wrap items-end gap-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  const fields = new FormData(e.currentTarget);
                  void change(
                    "/deadline",
                    {
                      confirmation_deadline: new Date(
                        String(fields.get("deadline")) + "Z",
                      ).toISOString(),
                    },
                    true,
                  );
                }}
              >
                <label>
                  New confirmation deadline (UTC)
                  <input
                    className="mt-2 block"
                    name="deadline"
                    type="datetime-local"
                    required
                    defaultValue={new Date(data.confirmation_deadline)
                      .toISOString()
                      .slice(0, 16)}
                    disabled={busy}
                  />
                </label>
                <button className="button" disabled={busy}>
                  Extend confirmation deadline
                </button>
              </form>
              <form
                className="mt-6 grid gap-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  const fields = new FormData(e.currentTarget);
                  void change(
                    "/reassign",
                    {
                      user_id: fields.get("user"),
                      target_team_id: fields.get("target"),
                      swap_user_id: fields.get("swap") || null,
                    },
                    true,
                  );
                }}
              >
                <h3 className="font-semibold">Move or swap participants</h3>
                <label>
                  Participant to move
                  <select
                    className="mt-2 block"
                    name="user"
                    required
                    disabled={busy}
                  >
                    {activeMembers.map((m) => (
                      <option key={m.user_id} value={m.user_id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Target team
                  <select
                    className="mt-2 block"
                    name="target"
                    required
                    disabled={busy}
                  >
                    {data.teams.map((t) => (
                      <option key={t.id} value={t.id}>
                        Team {t.number}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Swap with (optional)
                  <select className="mt-2 block" name="swap" disabled={busy}>
                    <option value="">Move without swap</option>
                    {activeMembers.map((m) => (
                      <option key={m.user_id} value={m.user_id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="button justify-self-start"
                  disabled={busy || !data.confirmation_open}
                >
                  Save reassignment
                </button>
              </form>
            </>
          )}
        </>
      )}
    </section>
  );
}
