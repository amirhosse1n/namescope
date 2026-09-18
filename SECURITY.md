# Security

NameScope is designed to run on a trusted local machine for a single user.

## Supported use

The default server binds to `127.0.0.1`. NameScope has no authentication or authorization layer, so it should not be exposed directly to the public internet.

A non-loopback bind is blocked unless `NAMESCOPE_ALLOW_REMOTE=true` is explicitly configured. That switch only removes the startup guard; it does not add authentication.

## Secrets

Keep these values out of Git history:

- `GITHUB_TOKEN`
- `TELEGRAM_API_HASH`
- `TELEGRAM_SESSION`
- any copied browser cookies or private platform responses

Use `.env` for local secrets. `.env` and Telethon session files are ignored by Git.

If a secret is committed accidentally, remove it from the repository and rotate or revoke it at the provider. Deleting the file in a later commit is not enough.

## Reporting a vulnerability

If the repository has GitHub private vulnerability reporting enabled, use it for security issues. Otherwise, open a minimal issue that does not include secrets or exploit details and ask for a private contact channel.
