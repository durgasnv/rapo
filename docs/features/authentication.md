# Accounts and sessions

## User experience

Participants can create an account, sign in, refresh the browser without losing
their session, and sign out. Account creation signs the user in immediately.
All public accounts start as participants. A trusted operator grants organizer
access to an existing account using the server-side command:

```bash
PYTHONPATH=apps/api uv run --env-file apps/api/.env python -m app.cli person@example.com
```

Refresh the browser after a role change. There is no public role-promotion API.
This is a conservative initial policy because organizer onboarding is not yet
specified in the requirements. A self-service onboarding workflow can replace it
when its policy is agreed.

## Request flow and security

`POST /auth/register` validates a name, email, and password of 12–128 characters.
The server normalizes the email to lowercase, hashes the password with Argon2id,
and stores the account transactionally. The database rejects duplicate emails.
`POST /auth/login` verifies the password and uses the same error for missing
accounts and incorrect passwords. Unknown accounts still perform hash verification.

Successful authentication generates a random session token. Its SHA-256 digest,
user ID, expiry, and random CSRF token are stored in PostgreSQL. The raw session
token goes only into the host-only `rapo_session` cookie, with HttpOnly,
SameSite=Lax, a one-day default lifetime, and path `/`. Enable
`RAPO_COOKIE_SECURE=true` for HTTPS deployments; local HTTP needs `false`.
Tokens are rotated when signing in again, and expired sessions are cleaned up
on successful authentication. Logout deletes the server session and cookie.

`GET /me` restores the current profile and CSRF token. The frontend holds profile
and CSRF state in memory; it never puts session credentials in localStorage.
Authenticated writes require `X-CSRF-Token`, compared against the server session.
Write requests also reject a supplied Origin outside the configured allowlist.
The API reads the user's current role from the database on each request.

All account and organizer responses, including errors, use `Cache-Control:
no-store`. Validation errors omit submitted values so passwords are not echoed.
Backend role checks remain authoritative even when someone bypasses the UI.

## Throttling and privacy

Authentication attempts share an atomic PostgreSQL counter per direct client IP,
defaulting to 20 requests per 60 seconds. Failed attempts count too. Counters
survive API restarts and work across workers. Only a digest of the IP is stored;
expired counters are removed on later authentication activity. This digest is
pseudonymous, not anonymous. The limiter uses the client address supplied by the
ASGI server; the documented local command disables forwarded-header trust.
Production proxy configuration needs deliberate review. A busy shared network
may hit the same limit.

## Verification and limitations

API tests cover hashed passwords/tokens, normalized duplicate emails, expiry,
session rotation/revocation, role-injection rejection, CSRF and origin failures,
throttling, and private-response caching. Browser tests cover signup, refresh,
logout, login, and participant denial of organizer access.

[Email password reset](password-reset.md) revokes all existing sessions and reset
links when a new password is saved. Email verification, account deletion/retention,
MFA, and a device-session management screen are not implemented.
The current cookie setup expects frontend
and API on the same site (localhost with different ports during development).
A cross-site production domain arrangement needs an explicit cookie/CSRF design.

The session design follows [OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
and its [CSRF token guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
