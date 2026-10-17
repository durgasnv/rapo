"use client";
import Link from "next/link";
import { useAccount } from "../../components/account-provider";
import { EventList } from "../../components/event-list";
import { Notifications } from "../../components/notifications";
import { ParticipantRegistrations } from "../../components/participant-registrations";

export default function Dashboard() {
  const { account, loading } = useAccount();
  return (
    <main className="page-shell">
      {loading ? (
        <p role="status">Loading your account…</p>
      ) : !account ? (
        <>
          <h1>Your account</h1>
          <p className="intro">
            <Link href="/sign-in" className="underline">
              Sign in
            </Link>{" "}
            to continue.
          </p>
        </>
      ) : (
        <>
          <h1>Hello, {account.user.name}.</h1>
          <p className="intro">Find your next event and meet your community.</p>
          {account.user.role === "organizer" && (
            <Link className="mb-6 inline-block underline" href="/organizer">
              Manage your events
            </Link>
          )}
          <section aria-label="Community events" className="mb-10">
            <EventList />
          </section>
          <Notifications key={`notifications:${account.user.id}`} />
          <ParticipantRegistrations key={account.user.id} />
        </>
      )}
    </main>
  );
}
