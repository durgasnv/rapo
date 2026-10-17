# Manual deployment preparation

The application uses a free demo deployment, with manual publishing to Vercel.
[The deployment guide](../../deploy/README.md) contains the manual steps,
environment values, migration, worker, email, and recovery commands. The Neon
setup follow-up below connects the existing hosted database under the user's
explicit authorization.

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

At this initial checkpoint, production database access, Vercel SMTP delivery, and
the full hosted browser journey had not been verified. The Neon follow-up below
records subsequent database verification. The user deploys Vercel manually.
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

### Neon setup follow-up

The Neon CLI and agent skills are installed. The initializer installed the Neon
plugin with its OAuth MCP configuration; MCP still requires authorization in the
agent before its first use. After the user completed CLI login, `neon deploy`
verified the Postgres-only policy and pulled the pooled and direct URLs into the
ignored root `.env`. Local Docker keys were preserved. The linked production
project is `shy-voice-66766417`, PostgreSQL 18 in `aws-us-east-2`.

FastAPI and the grouping worker now accept `DATABASE_URL`, while Alembic and the
backup CLI prefer `DATABASE_URL_UNPOOLED`. Explicit `RAPO_DATABASE_URL` and
`RAPO_MIGRATION_DATABASE_URL` override their corresponding Neon variables. Both
connection types retain psycopg 3, URL encoding, and TLS parameters. This keeps
SQLAlchemy transactions and existing authentication, authorization, and grouping
behavior intact. No JavaScript database client or new application service was
introduced. The generated Neon configuration dependencies support CLI policy
management. Agent skills and link metadata are excluded from Vercel uploads.
The backup workflow installs the PostgreSQL 18 client explicitly instead of
depending on the runner's default version, which may be too old for this server.

Migrations passed on an expiring, schema-only branch with a dedicated
`rapo_neon_test` database before being applied to the confirmed-empty production
database. Both databases reached Alembic revision `6a92d504b318`; `alembic check`
reported `No new upgrade operations detected.` Production remained free of test
users. The running API with production security settings returned 200 from
`/health`, `/ready`, and `/events`, and 401 from anonymous `/me`.

Deployment tests cover the real Neon database readiness check, pooled/direct URL
selection, explicit environment overrides, legacy fallback, and backup connection
selection. Twenty deployment tests passed against the isolated Neon database;
the additional backup CLI test passed separately. Python lint, formatting, and
configuration type checks passed. Review confirmed that credentials and local
link metadata remain ignored and no migrations run as part of the frontend build.

The first browser run found a stale ignored frontend setting that embedded
`http://localhost:8000` while the browser used `127.0.0.1:3000`. Account creation
worked, but the cross-site session cookie did not survive the refresh flow. The
local setting was corrected to `/api` and the frontend rebuilt. An IPv6 routing
failure recurred in Playwright's organizer promotion subprocess even though
standalone pooled/direct connections and the same Node-to-Python command passed.
The temporary verification process therefore uses a freshly resolved IPv4 address
through libpq's `PGHOSTADDR`, retaining the original hostname and TLS options.
No permanent IP address was pinned into the app's database configuration.

The corrected root `npm run build` completed with exit code 0. Against that
production build, all four browser checks passed (`4 passed (2.8m)`): account
persistence/sign-out/sign-in and participant authorization; organizer draft,
edit, publish, discovery, and cancellation; API health connectivity; and retry
after a simulated connectivity failure. These checks used the isolated Neon
database, the production frontend server, and the real FastAPI `/api` proxy.
The updated backup workflow also passed actionlint; its hosted execution and a
PostgreSQL 18 backup/restore rehearsal remain unverified.
After verification, the temporary branch and credential file were removed;
the production branch and ignored production environment file were retained.

The CLI dependency install reported five high-severity npm audit findings in the
existing Next.js ESLint dependency tree; those package versions were unchanged.
No forced dependency downgrade was applied. Vercel environment values are still
set manually: a local Neon env pull does not update a deployed Vercel service or
GitHub Actions secrets. SMTP delivery and the hosted scheduled grouping journey
remain separate deployment checks.
