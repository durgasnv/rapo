"use client";
import Link from "next/link";
import { useAccount } from "../../components/account-provider";

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
          <p className="intro">You’re signed in as {account.user.email}.</p>
          <section className="panel">
            <h2>Make a new connection.</h2>
            <p className="my-4">
              Discover what your community is planning. Participant registration
              is coming next.
            </p>
            <Link className="button" href="/events">
              Explore events
            </Link>
            {account.user.role === "organizer" && (
              <Link className="ml-5 underline" href="/organizer">
                Manage your events
              </Link>
            )}
          </section>
        </>
      )}
    </main>
  );
}
