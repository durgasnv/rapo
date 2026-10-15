# Manual deployment preparation

The approved slice prepares a free demo deployment without creating or publishing
hosted resources. [The deployment guide](../../deploy/README.md) contains the
manual steps, environment values, migration, worker, email, and recovery commands.

## Flow and boundaries

The root `vercel.json` defines Next.js and FastAPI services in one Vercel project.
Vercel Services is beta. Requests under `/api` enter the Python service with the
prefix removed; other requests enter Next.js. `api_entry.py` exposes the existing
application without moving its package or changing local server commands.
The frontend defaults to relative `/api` requests, including CSV downloads and
landing-page health checks. Local Next.js rewrites proxy that path to port 8000.
Existing explicit API URL overrides continue to work.

Same-origin browser requests keep the session cookie on the frontend host.
Production settings require Secure cookies, an HTTPS reset origin, and an explicit
CORS allowlist containing that origin. Configuration errors hide input values.
Provider PostgreSQL URLs select psycopg 3 without rewriting encoded credentials
or URL options. `/health` is liveness; `/ready` checks database/schema access and
returns a private generic error when unavailable.

The grouping workflow calls the existing transaction-safe worker once per run.
It creates proposals only; organizer approval remains required. Schedules are
opt-in and default-branch-only, with concurrency control. Public schedules run
every 15 minutes and private schedules hourly. These are best-effort demo timers,
not a guarantee of grouping at the exact target instant.

The release workflow explicitly selects migration, configuration check, mail
transport check, or backup. It does not migrate during frontend builds or on every
push. Only encrypted backups are uploaded; raw dumps are removed from the runner.
Restore rehearsal requires an empty disposable database and never drops objects.

## Alignment and review

This retains the modular Next.js/FastAPI/PostgreSQL application, role and ownership
checks, event lifecycle, and history-aware grouping. The free-hosting instruction
replaced the proposed paid Render resources. No new runtime dependency, public
administration endpoint, provider SDK, or event policy was added.

Review caught the need to preserve Neon's connection options in backup tools and
hide credentials in production configuration errors. Backup commands refuse
overwrites and remove partial files;
restore commands refuse populated/non-disposable targets. Workflows pin actions,
avoid secret-bearing test artifacts, and keep scheduling disabled until configured.

## Evidence and limits

All 186 backend tests passed, including production configuration, URL conversion,
readiness, private error output, and backup safety tests. A real PostgreSQL 16
backup restored into an empty test database; a second restore was rejected.
The Vercel configuration matches its published schema using Draft 7 validation.
Both GitHub workflows passed actionlint. Frontend lint, TypeScript, production
build, and separate hosted-test type checks passed. Python lint, formatting, and
strict type checks passed. The build used an isolated checkout and database.
Four browser checks passed through that production build's `/api` proxy:
sign-in persistence and participant authorization, organizer event management,
health connectivity, and retry after connection failure.

Production database access, Vercel SMTP delivery, and the full hosted browser
journey have not been verified. The user deploys manually.
Free quotas, cold starts, short database restore history, in-process mail delivery,
and potentially shared proxy client-IP quotas limit the demo's release readiness.

### Homepage routing follow-up

The user's first deployment at `https://rapo.vercel.app` was READY on commit
`1da958c`, with the Services framework and expected alias. Public checks returned
200 for `/sign-in` and `/api/health`, but `/` returned a Vercel `NOT_FOUND` 404.
This isolates the observed failure to homepage ingress; it does not establish
database readiness or successful sign-in. Build-log access returned 403, and no
authenticated Vercel CLI fallback was available.

The configuration now explicitly routes `/` to the frontend with lookup path `/`
and uses the documented `/(.*)` frontend catch-all after the API rule. This
addresses the suspected empty-path handling of the previous wildcard without
changing application routes, cookies, or API policy. JSON schema validation and
representative route-matching checks cover the configuration change. It still
needs verification on a deployment of the new commit. Push the commit and deploy
the newest `main` revision, then check `/`, `/sign-in`, and `/api/health` again.
