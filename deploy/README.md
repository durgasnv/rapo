# Manual free deployment

Deploy **one Vercel Hobby project** with Next.js and FastAPI behind the same
domain. Use **Neon Free PostgreSQL**, Gmail SMTP, and a bounded GitHub Actions
grouping job. No Render resource or paid worker is required.

The root [vercel.json](../vercel.json) uses **Vercel Services (beta)**. The frontend
service lives in `apps/web`; the backend uses the root Python lockfile and
`api_entry.py`. `/api/*` routes to FastAPI with that prefix stripped. This keeps
the existing HttpOnly, Secure, SameSite=Lax cookie on the website's host. The
backend still checks organizer roles, ownership, origins, and CSRF tokens.

References: [Vercel Services](https://vercel.com/docs/services),
[service configuration](https://vercel.com/docs/services/config-reference),
[SMTP support](https://vercel.com/kb/guide/serverless-functions-and-smtp), and
[Neon Free limits](https://neon.com/docs/introduction/plans).

## 1. Create the database

Use the existing **Free** Neon project `shy-voice-66766417`, with PostgreSQL
**18** in `aws-us-east-2`. Keep automatic scale-to-zero enabled. Do not select
a paid plan or enable usage-based upgrades for this demo. If creating a separate
project, choose a region close to the Vercel functions.

Keep both connection URLs privately:

- **Pooled URL:** API runtime and scheduled grouping.
- **Direct URL:** Alembic migrations, backups, and organizer administration.

Use TLS (`sslmode=require`; keep `channel_binding=require` if Neon supplies it).
The app accepts `postgresql://`, `postgres://`, or `postgresql+psycopg://` and
selects the installed psycopg 3 driver. Do not commit either URL or expose it in
a `NEXT_PUBLIC_*` variable.

## 2. Prepare environment values and migrate

### Neon CLI setup for this repository

Install the CLI with `npm i -g neon@latest` (or use `npx neon@latest`), then
run `neon login` yourself and finish the browser sign-in. The workspace uses:

```bash
neon init -y --org-id org-wispy-credit-53871014 --project-id shy-voice-66766417 --branch production --services postgres
neon config plan
neon deploy
```

`neon.ts` declares a Postgres-only policy. The initializer installs the Neon
agent plugin, including its OAuth MCP server; authorize that connection in your
agent when prompted. CLI login and MCP authorization are separate. Neither
requires putting an API key into repository files.

The CLI updates the existing ignored root `.env`, preserving the Docker values.
The API and worker accept its `DATABASE_URL` (pooled); Alembic and backups prefer
`DATABASE_URL_UNPOOLED` (direct). Existing `RAPO_DATABASE_URL` and
`RAPO_MIGRATION_DATABASE_URL` settings take precedence over the corresponding
Neon variables. Do not combine the local `apps/api/.env` with the Neon file:
its local database override would select Docker instead.

For a local API connected to the linked Neon branch:

Set `NEXT_PUBLIC_API_URL=/api` in the ignored `apps/web/.env.local` before
building. An old absolute localhost API URL is embedded in the build and can
break session cookies when the browser uses `127.0.0.1` instead.

```bash
uv run --env-file .env alembic upgrade head
uv run --env-file .env alembic check
uv run --env-file .env uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
# In a second terminal, after npm run build:
npm run start
```

Migration commands change the linked database: review migrations and test them
on an isolated branch first. Building the frontend never migrates the database.
For Vercel, copy the pooled URL privately into `DATABASE_URL` (or
`RAPO_DATABASE_URL`) in Production settings and redeploy manually. Pulling the
local file does not update Vercel or GitHub Actions secrets. Keep the direct URL
in the release/migration environment, rather than the frontend browser bundle.

This database starts empty; local Docker accounts are not copied automatically.
Create your account on the deployed site, then grant it organizer access using
the linked production environment:

```bash
PYTHONPATH=apps/api uv run --env-file .env python -m app.cli YOUR-ACCOUNT-EMAIL
```

Refresh the website afterward to load the organizer role.

### Production security settings

Use [api.env.production.example](api.env.production.example) as the template for
an ignored local `apps/api/.env.production`. Replace the database URL with the
**direct** Neon URL and use the intended stable Vercel domain. Keep the Gmail app
password only in this ignored file and the hosting secret settings.

```bash
cp deploy/api.env.production.example apps/api/.env.production
# Edit the ignored file locally, then run:
uv run --env-file apps/api/.env.production alembic upgrade head
uv run --env-file apps/api/.env.production alembic check
PYTHONPATH=apps/api uv run --env-file apps/api/.env.production python -m app.operations preflight
```

This is an explicit migration step, not a build command: building a preview must
never modify the live database. For later releases, take a backup first and
apply only reviewed forward migrations. A website rollback does not roll back
the database; review migration downgrade behavior before attempting recovery.

## 3. Import into Vercel

Push the prepared commit to GitHub yourself, then import the repository into
Vercel on the **Hobby** plan:

- **Root Directory:** repository root (`.`), **not** `apps/web`.
- Leave project-level install/build/output overrides unset. The root Services
  configuration selects Next.js and FastAPI independently.
- Use Node.js 24. Python is pinned to 3.12 by `.python-version`.
- Add the following **Production** environment values before deploying.

| Key                       | Value                                 |
| ------------------------- | ------------------------------------- |
| `NEXT_PUBLIC_API_URL`     | `/api`                                |
| `RAPO_ENVIRONMENT`        | `production`                          |
| `RAPO_DATABASE_URL`       | Neon **pooled** URL (secret)          |
| `RAPO_COOKIE_SECURE`      | `true`                                |
| `RAPO_CORS_ORIGINS`       | `["https://YOUR-PROJECT.vercel.app"]` |
| `RAPO_RESET_FRONTEND_URL` | `https://YOUR-PROJECT.vercel.app`     |
| `RAPO_SMTP_HOST`          | `smtp.gmail.com`                      |
| `RAPO_SMTP_PORT`          | `587`                                 |
| `RAPO_SMTP_SECURITY`      | `starttls`                            |
| `RAPO_SMTP_USERNAME`      | Your approved Gmail sender            |
| `RAPO_SMTP_SENDER`        | The same Gmail address                |
| `RAPO_SMTP_PASSWORD`      | Google app password (secret)          |

Enter the CORS JSON directly in Vercel without surrounding shell single quotes.
`RAPO_API_ORIGIN` is only a local/separate-host proxy setting; leave it unset for
this Services deployment. Keep `NEXT_PUBLIC_API_URL=/api` at build time.

If Vercel assigns a different stable domain, update both frontend-origin values
and redeploy. Do not use wildcard CORS. Configure previews with a separate Neon
branch/database and their exact origin; do not give arbitrary previews the live
database credentials. If Vercel's Services beta is unavailable in your account,
stop at configuration validation rather than starting a paid plan.

## 4. Verify the deployed site and Gmail

Open `https://YOUR-PROJECT.vercel.app/api/health` and `/api/ready`. Both should
return `{"status":"ok"}`. Readiness returns a generic 503 if the database or
required reset-token table is unavailable. Health alone checks liveness.

Create an account through the site, refresh, sign out, and sign in. Grant an
existing account organizer access through the trusted command using the direct
database environment, then refresh the website:

```bash
PYTHONPATH=apps/api uv run --env-file apps/api/.env.production python -m app.cli YOUR-ACCOUNT-EMAIL
```

Use **Forgot password?** on the deployed site. Verify delivery to your real inbox
and spam folder, the HTTPS domain in the link, successful reset, old-session
revocation, and sign-in with the new password. This is the check that proves mail
works from Vercel. Optionally send one transport check from your own machine:

```bash
PYTHONPATH=apps/api uv run --env-file apps/api/.env.production python -m app.operations mail-check
```

The CLI sends only to the configured sender; it does not prove Vercel delivery.
Use a [Google app password](https://support.google.com/accounts/answer/185833).

## 5. Enable scheduled grouping and backup operations

In GitHub, create a `production` environment restricted to the default branch.
Add environment variable `RAPO_FRONTEND_URL` with the stable HTTPS origin, and
these environment secrets:

| Secret                        | Purpose                                   |
| ----------------------------- | ----------------------------------------- |
| `RAPO_DATABASE_URL`           | Pooled Neon URL for grouping              |
| `RAPO_MIGRATION_DATABASE_URL` | Direct Neon URL for release operations    |
| `RAPO_SMTP_USERNAME`          | Gmail sender for optional transport check |
| `RAPO_SMTP_SENDER`            | Gmail sender for optional transport check |
| `RAPO_SMTP_PASSWORD`          | Gmail app password                        |
| `RAPO_BACKUP_PASSPHRASE`      | Strong, separately retained backup secret |

First run **Scheduled grouping → Run workflow** manually. It calls the existing
idempotent worker with `--once`; it creates proposals only, leaving approval to
the organizer. Enable scheduling with repository variable
`RAPO_SCHEDULE_ENABLED=true`. Public repositories run every 15 minutes; private
repositories run hourly to conserve included runner minutes. GitHub schedules
can be delayed or disabled after inactivity. Manual dispatch remains available.

**Release operations** supports explicit `preflight`, `migrate`, `mail-check`,
and `backup` runs. It never auto-migrates on pushes. After a successful manual
backup, set repository variable `RAPO_BACKUPS_ENABLED=true` to enable weekly
encrypted backup artifacts retained for 14 days. Download a verified backup and
keep its passphrase separately. Artifacts are not permanent disaster recovery.

Public repositories have free standard Linux runners. Private runs consume
included minutes, and artifacts consume storage allowance. Keep GitHub spending
budgets at zero/stop usage at the free allowance, monitor usage, and leave the
schedule flags off if the allowance is insufficient. Do not change repository
visibility merely to enable a schedule without reviewing what would become public.

## 6. Restore rehearsal

Neon Free currently provides a short restore-history window; it does not replace
independent backups. Use PostgreSQL 18 dump/restore tools for this PostgreSQL 18 database.
The backup workflow installs that client using the
[official PostgreSQL Apt repository](https://www.postgresql.org/download/linux/ubuntu/).
To create a local backup, first make an ignored directory:

```bash
mkdir -p backups
PYTHONPATH=apps/api uv run --env-file apps/api/.env.production python -m app.operations backup backups/rapo.dump
```

The command refuses overwrites and creates a private file. For a downloaded
workflow artifact, set `RAPO_BACKUP_PASSPHRASE` privately in the local environment
and decrypt it with:

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in backups/rapo.dump.enc -out backups/rapo.dump -pass env:RAPO_BACKUP_PASSPHRASE
```

Create a separate **empty** database ending in `_restore_test`. Copy its URL
into an ignored `apps/api/.env.restore` as `RAPO_DATABASE_URL`, then run:

```bash
PYTHONPATH=apps/api uv run --env-file apps/api/.env.restore python -m app.operations restore-check backups/rapo.dump
```

The restore command rejects other database names and populated databases, uses
one transaction, and checks restored schema access. It never drops the live
database. Inspect restored records before deciding on a recovery cutover; point
both the API and worker to the recovered database together.

## 7. Hosted organizer/participant verification

The optional [hosted test](../tests/hosted/release.spec.ts) uses real HTTPS,
cookies, the live worker, approval, and confirmation without changing database
timestamps. Put these in an ignored local `apps/web/.env.hosted` file:

```dotenv
RAPO_HOSTED_TESTS=1
RAPO_HOSTED_URL=https://YOUR-PROJECT.vercel.app
RAPO_SMOKE_ORGANIZER_EMAIL=your-dedicated-test-organizer@example.com
RAPO_SMOKE_ORGANIZER_PASSWORD=
```

```bash
node --env-file=apps/web/.env.hosted node_modules/@playwright/test/cli.js test --config playwright.hosted.config.ts
```

It creates two synthetic participants and an event, checks participant denial
of organizer actions and missing-CSRF rejection, waits for the actual scheduled
proposal, then finalizes and confirms through the browser. It cancels its event
afterward; synthetic accounts and audit records remain. Trace/video/screenshots
are disabled to avoid recording real credentials. The test can take up to 80
minutes with an hourly worker; manually dispatching the worker after its 90-second
registration window closes shortens verification. Use an isolated demo deployment.

## Current limits and review

This slice follows the approved free-hosting constraint and retains the existing
Next.js/FastAPI/PostgreSQL architecture, grouping policies, and organizer approval.
The provider changed from the original Render suggestion because Gmail SMTP and
database recovery do not fit Render's free tier. No paid resources are configured.

Free plans have cold starts, quotas, and no guarantee of timely scheduled jobs.
Vercel Services is beta. SMTP background tasks are in-process and delivery can be
lost on interruption; request a new link. Verify client-IP behavior on Vercel
before broad use: the authentication limiter uses the ASGI client address, and a
shared proxy address can make users share a quota. Do not blindly trust arbitrary
forwarded-IP headers to bypass that limiter.

Local checks cover production-setting validation, secret-safe errors, provider
URLs, readiness, backup failure/overwrite guards, and restore safety. Live service
creation, production migration, real Gmail delivery, and hosted test execution
are manual release steps, not completed by creating these files.
