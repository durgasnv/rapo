import Link from "next/link";
import type { ReactNode } from "react";
import { Reveal } from "../components/landing/reveal";
import { TeamSceneLoader } from "../components/landing/team-scene-loader";
import { ServiceStatus } from "./service-status";

const gutter = "px-5 md:px-12";
const kicker =
  "m-0 text-[13px] font-semibold uppercase tracking-[0.16em] text-(--color-accent-700)";
const label = "text-[13px] font-semibold uppercase tracking-[0.14em]";
const cta =
  "flex min-w-[220px] items-center gap-10 px-5 py-4 text-left text-base font-semibold";

const indexRow = ["Register", "Read history", "Generate", "Confirm"];

const steps: {
  label: string;
  title: ReactNode;
  body: string;
  tags: [string, string];
}[] = [
  {
    label: "Register",
    title: "Open the doors. Keep the line fair.",
    body: "Publish an activity with a team-size rule and an optional capacity. Seats fill in order; when they run out, a first-in, first-out waitlist takes over.",
    tags: ["FIFO waitlist", "Capacity-safe"],
  },
  {
    label: "Read history",
    title: (
      <>
        Every past pairing,{" "}
        <span className="text-(--color-accent)">remembered.</span>
      </>
    ),
    body: "rapo. counts how often each pair has shared a team at completed events. Those red lines are the repeats the engine is built to avoid.",
    tags: ["Pair frequency", "Completed events only"],
  },
  {
    label: "Generate",
    title: "Balanced sizes. Fresh faces.",
    body: "Team sizes are fixed first, then a seeded search swaps members until repeat pairs are as low as it can find — and spreads any that remain so no one carries them all.",
    tags: ["Seeded & reproducible", "Up to 100 people"],
  },
  {
    label: "Confirm",
    title: "Approve, confirm, repair.",
    body: "Organizers finalize the preview. Participants confirm or decline; vacancies pull from the waitlist, reassignments are validated, and the roster exports to CSV.",
    tags: ["Vacancy repair", "CSV export"],
  },
];

const pairs = [
  { names: "Alice–Bob", count: 3 },
  { names: "Bob–Carol", count: 1 },
  { names: "Alice–Carol", count: 0 },
];
const maxPair = Math.max(...pairs.map((pair) => pair.count));

const audiences = [
  {
    letter: "A",
    title: "College clubs & hackathons",
    body: "Mix cohorts every round instead of the same four friends.",
  },
  {
    letter: "B",
    title: "Workshops & training",
    body: "Rotate who learns alongside whom, session to session.",
  },
  {
    letter: "C",
    title: "Volunteer programs",
    body: "Spread shifts across new faces without spreadsheets.",
  },
  {
    letter: "D",
    title: "Team-building events",
    body: "Meet colleagues you haven't worked with — on purpose.",
  },
];

function Arrow({ children }: { children: string }) {
  return <span aria-hidden="true">{children}</span>;
}

export default function Home() {
  return (
    <Reveal className="landing">
      <TeamSceneLoader />

      <div
        aria-hidden="true"
        className={`pointer-events-none fixed inset-0 z-0 grid grid-cols-4 ${gutter}`}
      >
        <div className="border-l border-(--color-rule)" />
        <div className="border-l border-(--color-rule)" />
        <div className="border-l border-(--color-rule)" />
        <div className="border-x border-(--color-rule)" />
      </div>

      <nav
        aria-label="Main"
        className={`fixed inset-x-0 top-0 z-10 flex h-16 items-center gap-4 border-b-2 md:gap-8 border-(--color-text) bg-(--color-bg) ${gutter}`}
      >
        <a
          href="#top"
          className="text-2xl font-extrabold tracking-[-0.04em]"
          aria-label="rapo. — back to top"
        >
          rapo<span className="text-(--color-accent)">.</span>
        </a>
        <div className="hidden flex-1 flex-wrap gap-6 text-[15px] font-semibold md:flex">
          <a href="#how">How it works</a>
          <a href="#fair">Fairness</a>
          <Link href="/events">Events</Link>
        </div>
        <div className="ml-auto flex gap-2 whitespace-nowrap md:ml-0">
          <Link
            href="/sign-in"
            className="border-2 border-(--color-text) px-3 py-2.5 text-[15px] sm:px-4 font-semibold hover:bg-(--color-text) hover:text-(--color-bg)"
          >
            Sign in
          </Link>
          <Link
            href="/sign-up"
            className="border-2 border-(--color-accent) bg-(--color-accent) px-3 py-2.5 text-[15px] sm:px-4 font-semibold text-white hover:border-(--color-accent-600) hover:bg-(--color-accent-600) hover:text-white"
          >
            Create account
          </Link>
        </div>
      </nav>

      <main>
        <header
          id="top"
          className={`relative z-[1] box-border flex min-h-screen flex-col pt-[140px] ${gutter}`}
        >
          <div className="flex max-w-[760px] flex-1 flex-col justify-center gap-8">
            <p data-hero-fade="" className={kicker}>
              Less repetition. More connection.
            </p>
            <h1 className="m-0 text-[clamp(40px,8.4vw,136px)] font-extrabold leading-[0.9] tracking-[-0.045em]">
              <span className="block overflow-hidden pb-[0.06em]">
                <span data-hero-line="" className="block">
                  New teammates.
                </span>
              </span>
              <span className="block overflow-hidden pb-[0.06em]">
                <span data-hero-line="" className="block">
                  More possi<span className="text-(--color-accent)">-</span>
                </span>
              </span>
              <span className="block overflow-hidden pb-[0.06em]">
                <span data-hero-line="" className="block">
                  bilities.
                </span>
              </span>
            </h1>
            <p
              data-hero-fade=""
              className="m-0 max-w-[480px] text-xl leading-normal text-pretty"
            >
              Fresh, fair teams for communities that collaborate. rapo. reads
              who has worked together before — and introduces people who
              haven&apos;t.
            </p>
            <div data-hero-fade="" className="flex flex-wrap gap-2">
              <Link
                href="/events"
                className={`${cta} bg-(--color-accent) text-white hover:bg-(--color-accent-600) hover:text-white`}
              >
                <span className="flex-1">Explore events</span>
                <Arrow>→</Arrow>
              </Link>
              <a
                href="#how"
                className={`${cta} border-2 border-(--color-text) px-[18px] py-3.5 hover:bg-(--color-text) hover:text-(--color-bg)`}
              >
                <span className="flex-1">See how teams form</span>
                <Arrow>↓</Arrow>
              </a>
            </div>
          </div>
          <ol
            data-hero-fade=""
            aria-label="How rapo. works"
            className="m-0 mt-12 grid list-none grid-cols-2 border-t-2 border-(--color-text) p-0 md:grid-cols-4"
          >
            {indexRow.map((item, i) => (
              <li
                key={item}
                className={`flex gap-2 pt-4 pb-4 text-[13px] md:pb-6 font-semibold ${i % 2 ? "pl-4" : i ? "md:pl-4" : ""}`}
              >
                <span className="text-(--color-accent)">0{i + 1}</span>
                {item}
              </li>
            ))}
          </ol>
        </header>

        <section id="how" aria-label="How it works" className="relative z-[1]">
          {steps.map((step, i) => (
            <div
              key={step.label}
              className={`box-border flex min-h-screen items-center py-24 ${gutter}`}
            >
              <div data-reveal="" className="flex max-w-[500px] flex-col gap-6">
                <div className="flex items-baseline gap-4 border-b-2 border-(--color-text) pb-3">
                  <span className="text-[15px] font-extrabold text-(--color-accent)">
                    0{i + 1}
                  </span>
                  <span className={label}>{step.label}</span>
                </div>
                <h2 className="m-0 text-[clamp(40px,4.6vw,72px)] font-extrabold leading-[0.95] tracking-[-0.04em]">
                  {step.title}
                </h2>
                <p className="m-0 text-[19px] leading-[1.55] text-pretty">
                  {step.body}
                </p>
                <div className="flex flex-wrap gap-2 text-[13px] font-semibold">
                  <span className="bg-(--color-accent-100) px-2.5 py-1.5 text-(--color-accent-800)">
                    {step.tags[0]}
                  </span>
                  <span className="border-2 border-(--color-text) px-2.5 py-1.5">
                    {step.tags[1]}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </section>

        <section
          id="fair"
          aria-labelledby="fair-title"
          className={`relative z-[2] scroll-mt-16 border-t-2 border-(--color-text) bg-(--color-bg) py-[120px] ${gutter}`}
        >
          <div
            data-reveal=""
            className="mb-16 grid grid-cols-[repeat(auto-fit,minmax(min(100%,420px),1fr))] items-end gap-12"
          >
            <div className="flex flex-col gap-5">
              <p className={kicker}>The scoring</p>
              <h2
                id="fair-title"
                className="m-0 text-[clamp(44px,5.4vw,88px)] font-extrabold leading-[0.92] tracking-[-0.045em]"
              >
                Fair, and you can see why.
              </h2>
            </div>
            <p className="m-0 max-w-[520px] text-[19px] leading-[1.55] text-pretty">
              No black box, no compatibility claims. Every proposal is scored on
              two numbers — total repeats, then how evenly they fall — and the
              seed is saved so it can be reproduced.
            </p>
          </div>

          <div
            data-reveal=""
            className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,280px),1fr))] gap-0.5 border-2 border-(--color-text) bg-(--color-text)"
          >
            <div className="flex min-h-80 flex-col gap-6 bg-(--color-bg) p-8">
              <h3 className={`m-0 ${label}`}>Pair history · one team</h3>
              <ul className="m-0 mt-auto flex list-none flex-col gap-4 p-0">
                {pairs.map((pair) => (
                  <li
                    key={pair.names}
                    className="grid grid-cols-[110px_1fr_28px] items-center gap-3 text-base font-semibold"
                  >
                    <span>{pair.names}</span>
                    <div
                      aria-hidden="true"
                      className="h-3.5 bg-(--color-neutral-200)"
                    >
                      {pair.count > 0 && (
                        <div
                          data-bar=""
                          className="h-full origin-left bg-(--color-accent)"
                          style={{ width: `${(pair.count / maxPair) * 100}%` }}
                        />
                      )}
                    </div>
                    <span data-count={pair.count} className="text-right">
                      {pair.count}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="flex min-h-80 flex-col gap-4 bg-(--color-bg) p-8">
              <h3 className={`m-0 ${label}`}>Repeat cost</h3>
              <div
                data-count="4"
                className="mt-auto text-[160px] font-extrabold leading-[0.8] tracking-[-0.06em] text-(--color-accent)"
              >
                4
              </div>
              <p className="m-0 text-base leading-normal">
                3 + 1 + 0. The sum of shared history inside the team — the
                number the engine minimizes first.
              </p>
            </div>
            <div className="flex min-h-80 flex-col gap-4 bg-(--color-bg) p-8">
              <h3 className={`m-0 ${label}`}>Fairness penalty</h3>
              <div
                data-count="26"
                className="mt-auto text-[160px] font-extrabold leading-[0.8] tracking-[-0.06em]"
              >
                26
              </div>
              <p className="m-0 text-base leading-normal">
                3² + 4² + 1². Each person&apos;s burden, squared — the
                tie-breaker that keeps repeats from piling onto one person.
              </p>
            </div>
          </div>
        </section>

        <section
          aria-labelledby="audience-title"
          className={`relative z-[2] bg-(--color-bg) pb-[120px] ${gutter}`}
        >
          <div
            data-reveal=""
            className="flex flex-wrap items-baseline justify-between gap-6 border-t-2 border-(--color-text) pt-6 pb-10"
          >
            <h2
              id="audience-title"
              className="m-0 text-[clamp(32px,3.4vw,52px)] font-extrabold leading-none tracking-[-0.04em]"
            >
              Built for groups that meet again.
            </h2>
            <span className={`${label} text-(--color-accent-700)`}>
              History compounds with every event
            </span>
          </div>
          <ul
            data-reveal=""
            className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(min(100%,240px),1fr))] gap-0.5 border-2 border-(--color-text) bg-(--color-text) p-0"
          >
            {audiences.map((item) => (
              <li
                key={item.letter}
                className="flex flex-col gap-14 bg-(--color-bg) p-7 hover:bg-(--color-accent-100)"
              >
                <span
                  aria-hidden="true"
                  className="text-[15px] font-extrabold text-(--color-accent)"
                >
                  {item.letter}
                </span>
                <div className="flex flex-col gap-2">
                  <h3 className="m-0 text-[22px] font-extrabold tracking-[-0.02em]">
                    {item.title}
                  </h3>
                  <p className="m-0 text-[15px] leading-normal">{item.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section
          aria-labelledby="closing-title"
          className={`landing-closing relative z-[2] flex flex-col gap-16 bg-(--color-accent) pt-[120px] pb-16 text-white ${gutter}`}
        >
          <h2
            id="closing-title"
            data-reveal=""
            className="m-0 text-[clamp(56px,9vw,160px)] font-extrabold leading-[0.88] tracking-[-0.05em]"
          >
            Less repetition.
            <br />
            More connection.
          </h2>
          <div data-reveal="" className="flex flex-wrap gap-2">
            <Link
              href="/events"
              className={`${cta} bg-(--color-text) text-white hover:bg-black hover:text-white`}
            >
              <span className="flex-1">Explore events</span>
              <Arrow>→</Arrow>
            </Link>
            <Link
              href="/sign-up"
              className={`${cta} border-2 border-white px-[18px] py-3.5 text-white hover:bg-white hover:text-(--color-accent-700)`}
            >
              <span className="flex-1">Start organizing</span>
              <Arrow>→</Arrow>
            </Link>
          </div>
        </section>
      </main>

      <footer
        className={`landing-closing relative z-[2] bg-(--color-accent) pb-12 text-white ${gutter}`}
      >
        <div className="flex flex-wrap justify-between gap-4 border-t-2 border-white pt-5 text-sm font-semibold">
          <span className="text-xl font-extrabold tracking-[-0.04em]">
            rapo.
          </span>
          <span>Built for communities that collaborate.</span>
        </div>
        <details className="landing-status mt-6 text-sm font-semibold">
          <summary className="cursor-pointer">Service status</summary>
          <ServiceStatus />
        </details>
      </footer>
    </Reveal>
  );
}
