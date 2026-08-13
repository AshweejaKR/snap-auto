# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

`snap-auto` is a Python client for automating Snapchat via Playwright against `web.snapchat.com` (see `plan.md` for the full phased implementation plan). Phase 0 (project setup) is done: packaging, Playwright + Chromium, and the `snap_auto/` package layout exist. `SnapAutoClient`'s methods (`login`, `send_msg`, etc.) are still stubs (`raise NotImplementedError`) pending Phase 1+.

## Tooling

- Packaging/dependency manager: **uv** (`pyproject.toml`, `uv.lock`).
- Browser automation: **Playwright**, sync API, Chromium only for now.
- Python: `>=3.11` (see `.python-version`).

## Common commands

```bash
uv sync                        # install/update dependencies into .venv
uv add <package>                # add a new dependency
uv run playwright install chromium   # (re)install the Chromium browser binary
uv run python -c "import snap_auto"  # sanity-check the package imports
uv run pytest                   # run tests (once pytest is added in Phase 5)
```

Copy `.env.example` to `.env` and fill in `SNAP_USERNAME`/`SNAP_PASSWORD` before running anything that logs in.

## Architecture

- `snap_auto/client.py` — `SnapAutoClient`, the public API surface (Page Object Model consumer). Wraps a Playwright `Browser`/`BrowserContext`/`Page`; supports use as a context manager (`with SnapAutoClient() as client:`).
- `snap_auto/locators.py` — all CSS/text selectors, grouped by page (`LoginLocators`, `FriendsLocators`, `ChatLocators`). UI/selector drift should only ever require editing this file, not `client.py`. Values are currently `"TODO"` placeholders pending live DOM inspection in Phase 1.
- `snap_auto/exceptions.py` — exception hierarchy rooted at `SnapAutoError` (`LoginFailedError`, `SessionExpiredError`, `SelectorNotFoundError`, `RateLimitedError`, `UserNotFoundError`).
- `snap_auto/config.py` — `Config` dataclass loaded from environment/`.env` via `python-dotenv` (`Config.from_env()`). Holds credentials, headless flag, and the Playwright `storage_state` path.
- `tests/` — empty, reserved for Phase 5 (unit tests against saved HTML fixtures, plus opt-in integration tests gated behind an env flag).

Session cookies get saved to `.auth/storage_state.json` (path configurable via `SNAP_STORAGE_STATE_PATH`) once login is implemented; that directory is gitignored.

## Working in this repo

- Follow `plan.md`'s phase order — don't implement Phase 2/3 scraping logic before Phase 1 (login/session) is solid, since everything downstream depends on an authenticated `Page`.
- Keep selectors in `locators.py` only; never inline a CSS/text selector inside `client.py`.
- Never hardcode or log credentials; they must only ever come through `Config`/`.env`.
- Update this file's "Project status" section as phases land, so it doesn't go stale again.
