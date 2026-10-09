import { ServiceStatus } from "./service-status";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-6 py-10 sm:px-12">
      <header className="text-3xl font-bold tracking-tight">rapo.</header>
      <section className="my-auto py-16">
        <p className="mb-6 text-sm font-semibold uppercase tracking-widest text-emerald-800">
          Less repetition. More connection.
        </p>
        <h1 className="max-w-3xl text-5xl font-bold leading-tight tracking-tight sm:text-7xl">
          New teammates.
          <br />
          More possibilities.
        </h1>
        <p className="mt-8 max-w-xl text-lg leading-relaxed text-stone-600">
          Bring your community together with fresh, fair teams. Event
          registration and history-aware team formation are coming soon.
        </p>
        <ServiceStatus />
      </section>
      <footer className="text-sm text-stone-600">
        Built for communities that collaborate.
      </footer>
    </main>
  );
}
