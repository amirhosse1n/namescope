# Architecture

NameScope is a local FastAPI application with a static browser UI. The code is intentionally small and keeps platform-specific behavior behind separate checker modules.

## Runtime flow

```text
Browser UI
   │
   ▼
FastAPI routes
   │
   ├── Quick check ──► CheckService ──► Platform checker
   │                                  │
   │                                  └── ResultStore
   │
   └── Generated scan ──► JobManager ──► Generator
                                      │
                                      └── CheckService ──► Platform checker
                                                         │
                                                         └── ResultStore
```

## Modules

### `app.py`

Creates the FastAPI application, owns the application lifespan, serves the static UI, and exposes the JSON API. Runtime services are created inside the lifespan instead of at import time so tests can use isolated settings and temporary databases.

### `config.py`

Loads non-sensitive defaults from `config.yaml` and secrets or local overrides from environment variables. Configuration is validated before the server starts.

### `rules.py`

Contains local format validation for each platform. Network requests are never used to reject a username that is already invalid by local rules.

### `generator.py`

Builds candidate alphabets and produces random or lexicographic username sequences. It accepts a set of previously checked usernames so history can be excluded before any platform request is made.

### `checkers/`

Each checker owns one platform's network behavior and response classification.

- `github.py`: GitHub REST lookup plus a conservative signup availability check.
- `instagram.py`: public web-profile JSON lookup plus HTML fallback.
- `telegram.py`: public `t.me` lookup plus optional authenticated Telegram API checking.

The HTTP clients are long-lived for the life of the app so connections and cookies can be reused across a scan.

### `service.py`

Coordinates cache lookup, platform checking, result persistence, and quick checks across all three platforms.

### `jobs.py`

Runs generated scans as asynchronous jobs, applies per-platform delays, stops after explicit rate-limit responses, and keeps only a bounded number of completed jobs in memory.

### `storage.py`

Stores reusable results and durable history in SQLite. All SQL values are parameterized. The schema is compatible with earlier NameScope databases and includes a small migration marker so one-time data corrections are not repeated on every startup.

## Persistence

NameScope keeps two logical data sets in one SQLite database:

- `checks`: results that are safe to reuse for a configured TTL.
- `history`: every attempted username, including uncertain and rate-limited outcomes.

`Unknown`, `Rate limited`, `Setup required`, and `Error` results are retained in history but are not reused as cache hits.

## Security assumptions

NameScope is designed for one local user.

- The default bind address is loopback-only.
- The app has no account system or authorization layer.
- Non-loopback binding is blocked unless the operator explicitly opts in.
- Secrets stay in environment variables and are never sent to the browser.
- API responses use `no-store` caching headers.
- Browser responses include a restrictive Content Security Policy, clickjacking protection, and MIME-sniffing protection.
- Usernames are validated server-side before platform requests are sent.
- The frontend inserts result text using DOM text nodes rather than rendering returned strings as HTML.

If this project is deployed for multiple users, add authentication, authorization, request rate limiting, HTTPS termination, and stronger job isolation before exposing it publicly.

## Extending a platform checker

A checker should:

1. Validate locally first.
2. Use a bounded timeout.
3. Return a `CheckResult` rather than raising expected platform errors.
4. Distinguish confirmed availability from inferred availability.
5. Treat throttling as `RATE_LIMITED` so scan jobs can stop cleanly.
6. Keep credentials on the server side.
7. Add regression tests for any response shape used in classification.
