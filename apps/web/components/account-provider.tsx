"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { AccountSession, ApiError, apiRequest } from "../lib/api";

type AccountContext = {
  account: AccountSession | null;
  loading: boolean;
  setAccount: (account: AccountSession | null) => void;
};

const Context = createContext<AccountContext | null>(null);

export function useAccount() {
  const context = useContext(Context);
  if (!context) throw new Error("AccountProvider is required");
  return context;
}

export function AccountProvider({ children }: { children: React.ReactNode }) {
  const [account, setAccount] = useState<AccountSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // The landing page ships its own fixed navigation.
  const showChrome = usePathname() !== "/";

  useEffect(() => {
    let active = true;
    apiRequest<AccountSession>("/me")
      .then((session) => {
        if (active) setAccount(session);
      })
      .catch((failure: unknown) => {
        if (
          active &&
          !(failure instanceof ApiError && failure.status === 401)
        ) {
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not check your account.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function signOut() {
    if (!account) return;
    setBusy(true);
    setError("");
    try {
      await apiRequest<void>(
        "/auth/logout",
        { method: "POST" },
        account.csrf_token,
      );
      setAccount(null);
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401)
        setAccount(null);
      else
        setError(
          failure instanceof Error ? failure.message : "Could not sign out.",
        );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Context.Provider
      value={{
        account,
        loading,
        setAccount: (session) => {
          setAccount(session);
          setError("");
          setLoading(false);
        },
      }}
    >
      {showChrome && (
        <header className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-5 px-6 py-6">
          <Link
            href="/"
            className="text-3xl font-bold tracking-tight"
            aria-label="rapo. home"
          >
            rapo.
          </Link>
          <nav
            aria-label="Main navigation"
            className="flex flex-wrap items-center gap-5 text-sm font-semibold"
          >
            <Link href="/events">Explore events</Link>
            {loading ? (
              <span>Checking account…</span>
            ) : account ? (
              <>
                <Link href="/dashboard">Dashboard</Link>
                {account.user.role === "organizer" && (
                  <Link href="/organizer">Manage events</Link>
                )}
                <button onClick={() => void signOut()} disabled={busy}>
                  {busy ? "Signing out…" : "Sign out"}
                </button>
              </>
            ) : (
              <>
                <Link href="/sign-in">Sign in</Link>
                <Link href="/sign-up">Create account</Link>
              </>
            )}
          </nav>
        </header>
      )}
      {showChrome && error && (
        <p role="alert" className="mx-auto max-w-6xl px-6 text-red-800">
          {error}
        </p>
      )}
      {children}
    </Context.Provider>
  );
}
