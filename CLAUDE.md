# CLAUDE.md

Repository guidance for coding agents working on `snap-auto`.

## Project status

`snap-auto` is a synchronous Python/Playwright client for Snapchat Web. Phases 0–5
of `plan.md` are implemented on this branch:

- Project/package setup uses `uv`, Python 3.11+, and Playwright Chromium.
- Login, saved-session reuse, verification, logout, and manual/callback OTP handling
  are implemented. Phase 1 was previously smoke-tested against a real account.
- Discovery scans the virtualized chat sidebar and returns friends/chat sessions.
  Current semantic rows expose `aria-labelledby="title-<conversation-id>"`; the
  earlier live-verified `button:has-text(",")` row remains a compatibility fallback.
- Messaging opens a conversation by `/web/<conversation-id>` or sidebar/search,
  sends text once, confirms it from composer/message state, and parses currently
  rendered messages from `ul[id^="cv-"] > li`.
- Reliability includes ordered selector fallbacks, retries only for idempotent
  operations, paced actions, HTTP 429 handling, IndexedDB-aware saved state, and
  private screenshot/HTML/metadata artifacts on unexpected failures.

No live credentials or saved browser state are committed. Offline parsing, config,
cache, retry, rate-limit, messaging-flow, diagnostics, and persistence tests run in
CI across Python 3.11–3.13. Live tests remain explicitly gated.

## Tooling

- Packaging/dependency manager: `uv` (`pyproject.toml`, `uv.lock`).
- Browser automation: Playwright sync API, Chromium.
- Python: `>=3.11` (`.python-version`).

## Common commands

```bash
uv sync
uv run playwright install chromium
uv run python -c "import snap_auto"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

Copy `.env.example` to `.env` for live-account work. Never hardcode, print, log, or
commit credentials, storage state, screenshots, or DOM dumps.

## Architecture

- `snap_auto/client.py` — public `SnapAutoClient`, lifecycle, auth, discovery,
  messaging, retry/rate-limit behavior, and local diagnostics.
- `snap_auto/locators.py` — ordered selector candidates only. Do not inline UI
  selectors in `client.py`.
- `snap_auto/parsing.py` — pure normalization/parsing functions for DOM snapshots;
  keep UI parsing testable without a live account.
- `snap_auto/config.py` — immutable environment-backed configuration.
- `snap_auto/exceptions.py` — exception hierarchy rooted at `SnapAutoError`.
- `scripts/` — explicitly invoked live/manual helpers.
- `tests/` — offline unit tests plus separately gated live and live-send tests.

Saved session state lives under `.auth/`. Failure artifacts live under
`.snap-auto-artifacts/`; both are gitignored and may contain sensitive account/chat
data.

## Working rules

- Follow `plan.md` phase order and keep its status accurate.
- Prefer semantic attributes/roles over generated CSS classes. Retain a confirmed
  fallback when changing a selector.
- Never retry a message after submission; an unconfirmed send may still have
  succeeded, and retrying can create duplicates.
- Unit tests must not contact Snapchat. Live tests must be opt-in and must not send
  unless both a recipient and test message are explicitly configured.
- Keep public methods backward-compatible unless `plan.md` and README document a
  deliberate versioned change.
