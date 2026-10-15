# Password reset by email

Participants and organizers use **Forgot password?** on the sign-in page. Both
receive the same generic response whether an account exists. The email opens a
form for a new password and confirmation. A successful reset signs out every
existing session and requires signing in again; the account's role is preserved.

## Local Gmail setup

Set these values in the ignored `apps/api/.env`, never in committed files:

```dotenv
RAPO_SMTP_HOST=smtp.gmail.com
RAPO_SMTP_PORT=587
RAPO_SMTP_SECURITY=starttls
RAPO_SMTP_USERNAME=your-address@gmail.com
RAPO_SMTP_SENDER=your-address@gmail.com
RAPO_SMTP_PASSWORD=your-app-password
RAPO_RESET_FRONTEND_URL=http://localhost:3000
```

Use a [Google app password](https://support.google.com/accounts/answer/185833)
with two-step verification, rather than your regular account password. Keep it
only in the local environment or deployment secret manager. Restart the API after
changing configuration. With PostgreSQL running, apply the migration:

```bash
uv run --env-file apps/api/.env alembic upgrade head
```

Open the site using the configured frontend origin, request a link, and check the
inbox and spam folder. Production needs an HTTPS frontend origin, secure cookies,
the matching CORS allowlist, and working SMTP credentials. SMTP supports STARTTLS
or implicit TLS with certificate verification; plaintext delivery is unsupported.
The frontend origin comes from server configuration, never the request Host header.

## Request and transaction flow

`password-reset.tsx` calls `POST /auth/forgot-password`. The existing origin and
persistent per-IP authentication limiter apply. Missing mail configuration returns
503 uniformly. Otherwise the API responds before background account lookup and
SMTP work, avoiding account-dependent SMTP response times.

The service applies a separate persistent quota of three requests per normalized
email per 15 minutes by default, including unknown addresses. Only the digest of
the email-derived limiter key is stored. Over-quota requests retain the same
generic response. Existing auth activity removes expired limiter counters.

For an existing account, the service locks its user row, generates a 256-bit
random token, stores its SHA-256 digest in `password_resets`, and commits before
sending. Default expiry is 30 minutes. A new request leaves earlier unexpired
links usable; it does not let another person invalidate a legitimate reset email.
Expired links for that user are removed on subsequent requests. Otherwise expired
rows remain unusable until that cleanup or account deletion; account deletion
cascades to all reset rows.

The emailed link carries the raw token in a URL fragment. The browser reads it
after hydration, removes the fragment from the address bar, and keeps it only in
component memory. The page sets `no-referrer`; fragments do not reach web server
request URLs. Reloading the page requires reopening the email link.

`POST /auth/reset-password` locks the same user, rechecks the digest and expiry,
hashes the new password with Argon2, and deletes all that user's sessions and reset
tokens in one transaction. A failure rolls everything back. Missing, expired,
and reused links return the same error. Password login also locks the user before
verification, preventing a concurrent old-password login from leaving a valid
session after reset. No event assignments or organizer permissions change.

After commit, a confirmation email is attempted without including any password
or token. Delivery failure cannot undo the password change. The browser cookie
and cached account are cleared; reset does not automatically create a session.

## Failure and recovery limits

Mail runs in an in-process FastAPI background task, not a durable queue. A process
crash or SMTP failure can lose delivery after the generic response; request a new
link after checking configuration and quota. SMTP errors are logged with static
messages, without exception details, addresses, links, or credentials. If the
password changed but confirmation delivery failed, sign in with the new password.
Never retry a used link to recover a confirmation email.

Migration `6a92d504b318` adds only the reset-token table and indexes. Downgrading
to `5c2d0e7a91b4` drops that table and invalidates outstanding links; it preserves
accounts, passwords, sessions, and events. Back up production before migrations.

## Review and verification

This implements FR-01 account recovery within the existing Next.js/FastAPI and
PostgreSQL architecture. It adds no provider SDK or runtime dependency, public
token-delivery endpoint, role escalation, or event policy change. The lock added
to login is required for reset/session consistency, not an unrelated refactor.
The approach follows the
[OWASP reset guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

API tests cover hashed tokens, expiry, generic responses, per-email/IP throttling,
origin checks, validation privacy, SMTP failures, transaction rollback, session
revocation, role preservation, competing resets, and concurrent old-password
login. Browser tests cover TLS SMTP delivery, opening the email link, password
confirmation, new-password sign-in, session revocation, link replay, and malformed
links. The loopback SMTP fixture is test infrastructure, guarded by a test database
name; it is not an application delivery mode. It requires Python and OpenSSL.

Review found and corrected a browser navigation race by waiting for the
forgot-password route before filling its email field. It also caught a real
same-tab link-reopening bug: fragment-only navigation retained the success screen.
The reset component now handles fragment changes and revalidates reopened links.
Backend tests exercise the
transaction and concurrency boundaries directly. Automated SMTP tests use only
synthetic recipients; real Gmail delivery and a hosted deployment still require
operator configuration and verification.

Verified on 2026-10-15 against disposable PostgreSQL 16: all 169 backend tests
passed, including 18 reset tests; both reset browser tests passed through the TLS
SMTP fixture. Migration upgrade, schema comparison, downgrade, and re-upgrade
passed. Python lint, formatting, and type checks passed. No real email was sent.
Frontend formatting, lint, types, and production build passed during implementation.
After the final fragment-change fix, frontend lint and both browser tests passed;
the duplicate frontend check sequence was stopped during lint because reads from
Windows-mounted dependencies stalled. The production build was not repeated after
that final fix. Hosted CI has not been run in this session.
