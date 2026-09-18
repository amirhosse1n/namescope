# Platform behavior

NameScope uses different rules and confidence levels for each platform. This document describes what the application actually checks and where the limitations are.

## GitHub

### Local format rules

NameScope accepts 1–39 characters containing letters, digits, and hyphens. A hyphen cannot be the first or last character and consecutive hyphens are rejected.

GitHub's own documentation notes that usernames may be unavailable even when they do not appear active publicly, and GitHub Enterprise documentation describes the 39-character limit and dash normalization restrictions.

References:

- https://docs.github.com/en/site-policy/other-site-policies/github-username-policy
- https://docs.github.com/en/account-and-profile/concepts/username-changes
- https://docs.github.com/en/rest/about-the-rest-api/api-versions

### Availability flow

1. `GET https://api.github.com/users/<username>`
2. `200` means a public account exists, so the result is `Taken`.
3. `404` means no public user resource was found. It is not considered proof of claimability.
4. NameScope warms a GitHub signup session and sends a form POST to GitHub's web username checker.
5. A positive signup response becomes `Available`.
6. An explicit taken/reserved response becomes `Unavailable`.
7. Cookie gates or unrecognized responses remain `Likely available` and require manual verification.

The signup checker is a web endpoint rather than a documented REST API and can change without notice.

## Instagram

### Local format rules

NameScope uses a 1–30 character range and allows letters, digits, underscores, and periods. Periods cannot lead, trail, or repeat. The generator excludes usernames made only of digits.

Numeric-only accounts have existed historically, so this is intentionally a conservative generation rule rather than a claim that no such Instagram account can exist.

### Availability flow

Instagram does not expose a public anonymous API that confirms whether a username can be registered. NameScope therefore treats Instagram as a public-profile discovery check:

1. Query Instagram's public web-profile JSON route.
2. If a public user is returned, mark the username `Taken`.
3. If the response explicitly contains no user, mark it `Possibly available`.
4. If the JSON route is gated, retry after establishing a browser-like session and then fall back to the public profile page.
5. Public profile markers mean `Taken`.
6. A missing-profile shell means `Possibly available`.
7. Login walls, challenges, throttling, and unrecognized pages do not become availability claims.

Because these are web endpoints, Instagram can change the response format or block anonymous requests at any time.

## Telegram

### Local format rules

NameScope accepts 5–32 characters using Latin letters, digits, and underscores. It requires the username to start with a letter and does not allow a trailing underscore.

Telegram documents the 5–32 range and accepted characters for `account.checkUsername`. Telegram's own client translation strings also expose validation messages for usernames that start with a number or end with an underscore.

References:

- https://core.telegram.org/method/account.checkUsername
- https://telegram.org/faq#usernames-and-t-me
- https://translations.telegram.org/en/android_x/settings/UsernameHelp

### Public mode

Without credentials, NameScope loads `https://t.me/<username>`.

- Public profile/page markers become `Taken`.
- The generic Telegram page becomes `Likely unclaimed`.
- An unrecognized response becomes `Unknown`.

This does not prove that Telegram will let you claim the username.

### Authenticated mode

With `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_SESSION`, NameScope calls `account.checkUsername` through Telethon.

The official method can return:

- available
- occupied
- invalid
- purchase available through Fragment
- flood wait / rate limiting

Telegram documents that this method is available to authenticated users only.
