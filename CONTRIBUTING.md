# Contributing

Contributions are welcome, especially fixes for platform response changes and regression tests that capture those changes.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

On Windows PowerShell, activate the virtual environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## Before opening a pull request

- Keep platform-specific behavior inside its checker module.
- Add or update tests for any response classifier change.
- Do not add real tokens, cookies, session strings, or captured private responses.
- Preserve the distinction between confirmed availability and inferred availability.
- Avoid adding dependencies when the standard library or an existing dependency is enough.
- Run the full test suite and `node --check src/namescope/web/static/app.js`.

## Platform changes

GitHub, Instagram, and Telegram can change public web behavior without notice. If you are fixing a checker, include a small sanitized response fixture or mocked response in the test suite rather than relying on a live request during CI.
