"use client";

import { useEffect, useState } from "react";

type HealthState = "loading" | "online" | "offline";
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function ServiceStatus() {
  const [status, setStatus] = useState<HealthState>("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    let active = true;

    async function checkHealth() {
      try {
        const response = await fetch(`${apiUrl.replace(/\/$/, "")}/health`, {
          signal: controller.signal,
          cache: "no-store",
        });
        if (!response.ok) throw new Error("Health request failed");
        const data: unknown = await response.json();
        if (
          typeof data !== "object" ||
          data === null ||
          !("status" in data) ||
          data.status !== "ok"
        ) {
          throw new Error("Unexpected health response");
        }
        if (active) setStatus("online");
      } catch {
        if (active) setStatus("offline");
      } finally {
        window.clearTimeout(timeout);
      }
    }

    void checkHealth();
    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [attempt]);

  return (
    <section
      aria-label="Service status"
      className="mt-12 max-w-xl rounded-2xl border border-stone-300 bg-white p-6"
    >
      <h2 className="font-semibold">Service status</h2>
      <div
        role="status"
        aria-live="polite"
        className="mt-2 text-sm text-stone-600"
      >
        {status === "loading" && "Checking connection…"}
        {status === "online" && (
          <>
            <p>Connected to rapo.</p>
            <pre className="mt-3 text-emerald-800">{'{ "status": "ok" }'}</pre>
          </>
        )}
        {status === "offline" &&
          "We couldn’t connect. Please try again in a moment."}
      </div>
      <button
        type="button"
        disabled={status === "loading"}
        onClick={() => {
          setStatus("loading");
          setAttempt((value) => value + 1);
        }}
        className="mt-4 rounded-lg bg-emerald-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
      >
        {status === "loading" ? "Checking…" : "Check again"}
      </button>
    </section>
  );
}
