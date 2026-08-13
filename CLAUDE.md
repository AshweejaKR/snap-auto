# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

`snap-auto` is a Python client for automating Snapchat via Playwright against `web.snapchat.com` (see `plan.md` for the full phased implementation plan). Phase 0 (project setup) is done: packaging, Playwright + Chromium, and the `snap_auto/` package layout exist. Phase 1 (session & auth) is done and verified end-to-end against a real account: `login()`, `logout()`, and `verify_login()` on `SnapAutoClient` are wired up against `LoginLocators`, with `storage_state` session persistence and a manual-OTP fallback hook (`otp_callback` param on `login()`, defaults to a stdin prompt). A manual smoke test (`scripts/manual_login_test.py`) has run the full `login()` → `verify_login()` → `logout()` → `verify_login()` cycle successfully headed. Two caveats remain: (1) the login page's username-step UI is not stable across sessions (observed both English/Hindi field labels and "Log in"/"Next" button labels), so `LoginLocators.username_submit_button` uses a best-effort `button[type="submit"]` guess rather than matching translated text — revisit if login starts failing at that step; (2) `otp_input`, `otp_submit_button`, and `login_error_banner` are still `"TODO"` placeholders, unverified because no real OTP challenge or rejected-login case has been hit yet.

Phase 2 (discovery) is **implemented, with the chat list's row structure confirmed via a live Playwright codegen session** (sub-fields beyond username/status still unverified). `web.snapchat.com` has **no dedicated friends page**: every friend shows up as a row in the chat list instead, each a `<button>` whose text is `"{username} , {status}"` (e.g. `"Anagha Hegde , New Snap"`, `"kiran , Received"`). `ChatLocators.chat_list_container`/`chat_list_item` use the heuristic selector `button:has-text(",")` to match these rows. `get_all_chat_session()` parses each row via `SnapAutoClient._parse_chat_row` into `{"username", "user_id", "preview", "timestamp", "unread"}` dicts (`preview` is the raw status text; `timestamp`/`unread` are `None` — no confirmed separate DOM elements for those yet). `get_fnd_list()` is derived from `get_all_chat_session()` (`{"username", "user_id"}` dicts) since there's no separate friends source to scrape — this only covers friends with an existing chat, not the full friend graph; a richer "New Chat" contact-picker source was seen in the same codegen session but its selectors were too fragile (unlabeled search box, `div.nth(3)`) to use yet. `get_user_id(name=..., index=...)` and `get_username(index)` are wired up on `SnapAutoClient`, with per-session caching (`_fnd_list_cache`/`_chat_session_cache`) and a `refresh=True` param on the two scrape methods to force a re-scrape. `user_id` is resolved as a hybrid: every friend/chat dict always has `username`; `user_id` is populated only if `chat_item_user_id_attribute` (currently `"TODO"`) ends up pointing at a real `data-*` attribute once the DOM is inspected further, otherwise it's `None` and `get_user_id()` falls back to returning the username. Remaining gaps: `chat_item_unread_marker`/`chat_item_user_id_attribute` are still `"TODO"`, and the `button:has-text(",")` heuristic should be tightened to a real container/class selector (via `scripts/inspect_dom.py`) if it ever starts matching unrelated buttons. Messaging (Phase 3) methods (`send_msg`, `read_msg`) are still stubs (`raise NotImplementedError`).

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
- `snap_auto/locators.py` — all CSS/text selectors, grouped by page (`LoginLocators`, `FriendsLocators`, `ChatLocators`). UI/selector drift should only ever require editing this file, not `client.py`. `LoginLocators` is filled in and verified except `otp_input`/`otp_submit_button`/`login_error_banner` (still `"TODO"`). `FriendsLocators` is intentionally empty — there's no dedicated friends page, so `get_fnd_list()` derives from the chat list instead (see Project status). `ChatLocators.chat_list_container`/`chat_list_item` use the confirmed heuristic `button:has-text(",")` (every chat row's text is `"{username} , {status}"`); `chat_item_username`/`chat_item_preview`/`chat_item_timestamp`/`chat_item_unread_marker`/`chat_item_user_id_attribute` are still `"TODO"` since no separate sub-elements are confirmed yet — `client.py` parses the combined row text instead. `ChatLocators.message_input`/`send_button`/`message_bubble` are for the Phase 3 message thread UI, not the chat list.
- `snap_auto/exceptions.py` — exception hierarchy rooted at `SnapAutoError` (`LoginFailedError`, `SessionExpiredError`, `SelectorNotFoundError`, `RateLimitedError`, `UserNotFoundError`).
- `snap_auto/config.py` — `Config` dataclass loaded from environment/`.env` via `python-dotenv` (`Config.from_env()`). Holds credentials, headless flag, and the Playwright `storage_state` path.
- `tests/` — empty, reserved for Phase 5 (unit tests against saved HTML fixtures, plus opt-in integration tests gated behind an env flag).

Session cookies get saved to `.auth/storage_state.json` (path configurable via `SNAP_STORAGE_STATE_PATH`) once login is implemented; that directory is gitignored.

## Working in this repo

- Follow `plan.md`'s phase order — don't implement Phase 2/3 scraping logic before Phase 1 (login/session) is solid, since everything downstream depends on an authenticated `Page`.
- Keep selectors in `locators.py` only; never inline a CSS/text selector inside `client.py`.
- Never hardcode or log credentials; they must only ever come through `Config`/`.env`.
- Update this file's "Project status" section as phases land, so it doesn't go stale again.
