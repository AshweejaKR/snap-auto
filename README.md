# snap-auto

A Python client for automating [Snapchat's web app](https://web.snapchat.com) via
[Playwright](https://playwright.dev/python/). See [`plan.md`](plan.md) for the full
phased implementation plan and [`CLAUDE.md`](CLAUDE.md) for repo/architecture notes.

## Status

- **Phase 0 (project setup):** done.
- **Phase 1 (session & auth):** done and verified end-to-end against a real account —
  `login()`, `logout()`, `verify_login()` work with session persistence and a
  manual-OTP fallback. Two known gaps: the username-step submit button selector is a
  best-effort guess (Snapchat's login page shows inconsistent labels/languages across
  sessions), and the OTP/error-banner selectors are still unverified since no real
  challenge or rejection has been hit yet.
- **Phase 2+ (friends/chat discovery, messaging, reliability, tests):** not started —
  those methods currently raise `NotImplementedError`.

## Setup

```bash
uv sync                              # install dependencies into .venv
uv run playwright install chromium   # install the Chromium browser binary
cp .env.example .env                 # then fill in SNAP_USERNAME / SNAP_PASSWORD
```

## Usage

```python
from snap_auto.client import SnapAutoClient

with SnapAutoClient() as client:
    client.login(username="...", password="...")
    assert client.verify_login()
    client.logout()
```

`login()` takes `username`/`password` explicitly — read them from `os.environ` (or
`Config.from_env()`, which loads `SNAP_USERNAME`/`SNAP_PASSWORD` from `.env`) rather
than hardcoding them. `SnapAutoClient()` itself also calls `Config.from_env()` when no
`Config` is passed in, for the `headless` flag and `storage_state` path.

A session's cookies/localStorage are saved to `.auth/storage_state.json` (path
configurable via `SNAP_STORAGE_STATE_PATH`) after a successful login, so a later
`login()` call reuses the saved session instead of re-authenticating.

### Handling 2FA/OTP

If Snapchat challenges the login with a one-time code, `login()` blocks and prompts
for it on stdin by default. Pass `otp_callback` to source the code from somewhere else
(e.g. an SMS-reading service) instead of a human at the terminal:

```python
client.login(username="...", password="...", otp_callback=lambda: fetch_code_from_sms())
```

## Development

```bash
uv run python -c "import snap_auto"  # sanity-check the package imports
uv run pytest                        # run tests (once pytest is added in Phase 5)
```
