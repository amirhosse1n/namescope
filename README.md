# NameScope

NameScope is a small web app for generating username candidates and checking them across **GitHub**, **Instagram**, and **Telegram**.

It is useful when you want to explore short handles, scan a custom character set, or check the same username on all three platforms without manually opening each site. NameScope also keeps a local history so later scans can skip usernames you have already checked.

## What it does

- Check one username across GitHub, Instagram, and Telegram.
- Generate candidates by minimum length, maximum length, count, and character groups.
- Use random or lexicographic generation.
- Apply platform-specific username rules before making network requests.
- Keep a persistent SQLite history and skip previously checked names by default.
- Recheck old names when you explicitly want a fresh pass.
- Keep a separate shortlist of names that look available or unclaimed.
- Cache reusable results to reduce unnecessary requests.

## Availability labels

The three platforms do not expose the same kind of availability signal, so NameScope deliberately distinguishes confirmed and inferred results.

| Label | Meaning |
| --- | --- |
| **Available** | A first-party availability check returned a positive result. |
| **Likely available / Possibly available / Likely unclaimed** | No public account was found, but registration is not guaranteed. |
| **Taken** | A public account or entity exists. |
| **Unavailable** | The platform does not currently allow the username to be claimed even though no public profile resolves. |
| **Fragment purchase** | Telegram reports the username as purchasable rather than freely claimable. |
| **Unknown** | The response was gated, ambiguous, or could not be classified safely. |
| **Rate limited** | The platform asked the client to slow down. |

Always verify a candidate on the platform before relying on it. Availability can change between the check and registration.

## Quick start

NameScope requires **Python 3.11 or newer**.

```bash
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

Run the app:

```bash
python main.py
```

NameScope starts on `http://127.0.0.1:8765` and opens your browser by default.

## Optional GitHub token

Public GitHub user lookup works without authentication, but the unauthenticated REST API quota is limited. Add a token to `.env` if you plan to run larger scans:

```env
GITHUB_TOKEN=your_token_here
```

NameScope only needs the token for GitHub API authentication; public user lookup does not require repository permissions.

## Optional Telegram API setup

Public `t.me` checks do not require login, but they can only tell you whether a public Telegram entity resolves. For a definitive username availability check, NameScope can call Telegram's official `account.checkUsername` method using your own user session.

Install Telegram support:

```bash
python -m pip install -r requirements-telegram.txt
```

Create a local session:

```bash
python scripts/setup_telegram.py
```

Then place the generated values in `.env`:

```env
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_SESSION=your_string_session
```

Treat `TELEGRAM_SESSION` like a password. Never commit or share it.

## How each platform is checked

### GitHub

NameScope first queries the GitHub REST API for a public user. If no public profile exists, it tries GitHub's web signup availability check using a normal form POST and a warmed cookie session.

A REST `404` by itself is **not** treated as proof that the name can be registered. GitHub can keep namespaces unavailable even when no public profile resolves.

### Instagram

Instagram does not provide a public anonymous username-registration API. NameScope uses public web-profile signals and falls back conservatively when Instagram returns a login wall, interstitial, or throttling response.

A missing public profile is shown as **Possibly available**, not as a registration guarantee.

NameScope also excludes all-digit Instagram candidates from generation. Legacy or exceptional numeric-only accounts may exist, but they are not treated as normal claimable candidates by this project.

### Telegram

Without credentials, NameScope reads the public `t.me/<username>` page. That is enough to identify many existing public users, bots, groups, and channels, and to identify the generic unclaimed shell in many cases.

With an authorized Telegram user session, NameScope uses the official `account.checkUsername` method and can distinguish available, occupied, invalid, purchasable, and flood-wait results.

More detail is available in [docs/platform-behavior.md](docs/platform-behavior.md).

## Persistent history

Every attempted username is stored in `data/namescope.sqlite3`, including uncertain and rate-limited results.

By default, a new scan excludes anything already present in history for that platform. This prevents random scans from repeatedly spending requests on the same names after you restart the app.

Use **Recheck usernames already saved in history** when you intentionally want to scan old candidates again. Use **Clear history** to reset one platform completely.

The database is ignored by Git and stays on your machine.

## Configuration

Non-sensitive defaults live in `config.yaml`. Secrets and local overrides belong in `.env`.

Useful environment variables:

| Variable | Purpose |
| --- | --- |
| `GITHUB_TOKEN` | Optional GitHub REST API authentication. |
| `TELEGRAM_API_ID` | Telegram user API ID. |
| `TELEGRAM_API_HASH` | Telegram user API hash. |
| `TELEGRAM_SESSION` | Telegram StringSession. |
| `NAMESCOPE_HOST` | Bind address. Default: `127.0.0.1`. |
| `NAMESCOPE_PORT` | Web server port. Default: `8765`. |
| `NAMESCOPE_OPEN_BROWSER` | Open the browser automatically. |
| `NAMESCOPE_DATABASE` | Override the SQLite path. |
| `NAMESCOPE_CONFIG` | Use another YAML configuration file. |
| `NAMESCOPE_ALLOW_REMOTE` | Allow binding to a non-loopback address. Default: `false`. |

NameScope has no authentication layer. It refuses to bind to a non-loopback address unless `NAMESCOPE_ALLOW_REMOTE=true` is explicitly set. Do not expose the app directly to the public internet.

## API

The web UI uses a small local JSON API:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | App and optional integration status. |
| `GET` | `/api/rules` | Platform generation rules. |
| `POST` | `/api/check` | Check one username across all platforms. |
| `POST` | `/api/scans` | Start a generated scan. |
| `GET` | `/api/scans/{job_id}` | Poll scan progress and results. |
| `POST` | `/api/scans/{job_id}/cancel` | Cancel a running scan. |
| `GET` | `/api/history/{platform}` | Read recent local history. |
| `DELETE` | `/api/history/{platform}` | Clear history and cache for one platform. |

## Development

Install the development dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Run the tests:

```bash
python -m pytest -q
```

Check the browser JavaScript syntax:

```bash
node --check src/namescope/web/static/app.js
```

The test suite uses mocked platform responses; it does not spend live API quota.

## Project layout

```text
NameScope/
├── .github/workflows/tests.yml
├── docs/
│   ├── architecture.md
│   └── platform-behavior.md
├── scripts/
│   └── setup_telegram.py
├── src/namescope/
│   ├── checkers/
│   ├── web/static/
│   ├── app.py
│   ├── config.py
│   ├── generator.py
│   ├── jobs.py
│   ├── models.py
│   ├── rules.py
│   ├── service.py
│   └── storage.py
├── tests/
├── config.yaml
├── main.py
└── pyproject.toml
```

See [docs/architecture.md](docs/architecture.md) if you want to understand the internal flow before changing a checker or adding another platform.

## Responsible use

NameScope intentionally adds per-platform delays and stops a scan after a clear rate-limit response. Keep scan sizes reasonable and respect platform terms and limits. Public web behavior can change without notice, especially on Instagram and undocumented GitHub web endpoints.

## License

MIT [LICENSE](LICENSE). |
