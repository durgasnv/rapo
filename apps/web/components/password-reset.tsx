"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiRequest } from "../lib/api";
import { useAccount } from "./account-provider";

export function ForgotPassword() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await apiRequest<{ message: string }>(
        "/auth/forgot-password",
        {
          method: "POST",
          body: JSON.stringify({ email: fields.get("email") }),
        },
      );
      setMessage(result.message);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Could not request a reset link.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="page-shell max-w-xl">
      <h1>Forgot your password?</h1>
      <p className="intro">
        Enter your account email to request a password-reset link.
      </p>
      <form
        className="panel form-stack"
        onSubmit={(event) => void submit(event)}
      >
        <label>
          Email
          <input
            type="email"
            name="email"
            autoComplete="email"
            required
            maxLength={254}
            disabled={busy}
          />
        </label>
        {error && (
          <p role="alert" className="text-red-800">
            {error}
          </p>
        )}
        {message && <p role="status">{message}</p>}
        <button className="button" disabled={busy}>
          {busy ? "Please wait…" : "Send reset link"}
        </button>
      </form>
      <Link className="mt-6 inline-block underline" href="/sign-in">
        Back to sign in
      </Link>
    </main>
  );
}

export function ResetPassword() {
  const { setAccount } = useAccount();
  const [token, setToken] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  useEffect(() => {
    let active = true;
    // Initialize from the browser after hydration. Cleanup also handles Strict Mode's replay.
    function loadToken() {
      if (!active) return;
      const value =
        new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "";
      setToken(/^[A-Za-z0-9_-]{43}$/.test(value) ? value : "");
      setDone(false);
      setError("");
      window.history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search,
      );
      setLoaded(true);
    }
    Promise.resolve().then(loadToken);
    window.addEventListener("hashchange", loadToken);
    return () => {
      active = false;
      window.removeEventListener("hashchange", loadToken);
    };
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setError("");
    if (fields.get("password") !== fields.get("confirm")) {
      setError("Passwords must match.");
      return;
    }
    setBusy(true);
    try {
      await apiRequest("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, password: fields.get("password") }),
      });
      form.reset();
      setToken("");
      setAccount(null);
      setDone(true);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Could not reset your password.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="page-shell max-w-xl">
      <h1>Reset your password</h1>
      {!loaded ? (
        <p role="status" className="intro">
          Loading reset link…
        </p>
      ) : done ? (
        <>
          <p role="status" className="intro">
            Your password has been reset. Sign in with your new password.
          </p>
          <Link className="button" href="/sign-in">
            Sign in
          </Link>
        </>
      ) : !token ? (
        <>
          <p role="alert" className="intro">
            This reset link is missing or invalid. Request a new one.
          </p>
          <Link className="underline" href="/forgot-password">
            Request a new reset link
          </Link>
        </>
      ) : (
        <>
          <p className="intro">
            Choose a password of 12–128 characters. You’ll sign in again
            afterward.
          </p>
          <form
            className="panel form-stack"
            onSubmit={(event) => void submit(event)}
          >
            <label>
              New password
              <input
                name="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={128}
                disabled={busy}
              />
            </label>
            <label>
              Confirm new password
              <input
                name="confirm"
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={128}
                disabled={busy}
              />
            </label>
            {error && (
              <p role="alert" className="text-red-800">
                {error}
              </p>
            )}
            <button className="button" disabled={busy}>
              {busy ? "Please wait…" : "Reset password"}
            </button>
          </form>
          <Link className="mt-6 inline-block underline" href="/forgot-password">
            Request a new reset link
          </Link>
        </>
      )}
    </main>
  );
}
