"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { AccountSession, apiRequest } from "../lib/api";
import { useAccount } from "./account-provider";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { setAccount } = useAccount();
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isRegister = mode === "register";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {
      email: form.get("email"),
      password: form.get("password"),
      ...(isRegister ? { name: form.get("name") } : {}),
    };
    setError("");
    setBusy(true);
    try {
      const session = await apiRequest<AccountSession>(`/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setAccount(session);
      router.push("/dashboard");
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="page-shell max-w-xl">
      <h1>{isRegister ? "Find your next team." : "Welcome back."}</h1>
      <p className="intro">
        {isRegister
          ? "Create your rapo. account to get started."
          : "Sign in to manage your account and events."}
      </p>
      <form
        onSubmit={(event) => void submit(event)}
        className="panel form-stack"
      >
        {isRegister && (
          <label>
            Your name
            <input name="name" autoComplete="name" required maxLength={100} />
          </label>
        )}
        <label>
          Email
          <input
            name="email"
            type="email"
            autoComplete="email"
            required
            maxLength={254}
          />
        </label>
        <label>
          Password
          <input
            name="password"
            type="password"
            autoComplete={isRegister ? "new-password" : "current-password"}
            required
            minLength={isRegister ? 12 : 1}
            maxLength={128}
          />
        </label>
        {isRegister && (
          <p className="text-sm text-stone-600">
            Use at least 12 characters. A memorable passphrase works well.
          </p>
        )}
        {error && (
          <p role="alert" className="text-red-800">
            {error}
          </p>
        )}
        <button className="button" disabled={busy}>
          {busy ? "Please wait…" : isRegister ? "Create account" : "Sign in"}
        </button>
      </form>
      {!isRegister && (
        <Link className="mt-6 inline-block underline" href="/forgot-password">
          Forgot password?
        </Link>
      )}
      <p className="mt-6">
        {isRegister ? "Already have an account? " : "New to rapo.? "}
        <Link className="underline" href={isRegister ? "/sign-in" : "/sign-up"}>
          {isRegister ? "Sign in" : "Create account"}
        </Link>
      </p>
    </main>
  );
}
