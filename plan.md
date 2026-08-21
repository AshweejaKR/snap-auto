# snap-auto — Implementation Plan

## Overview

Python client for automating Snapchat via browser automation against
`www.snapchat.com/web` and its `web.snapchat.com` compatibility host. Built incrementally,
phase by phase, starting with the 10 core methods below.

**Caveat (read once, move on):** this automates a consumer product with no
public personal-account API, so it relies on scraping a UI that changes
often. Expect selector breakage over time and keep the Phase 4 reliability,
rate-limit handling, and diagnostics intact. Accounts can be flagged or locked
for high-volume or abusive automation, so use a dedicated test account and keep
actions conservative.

## Framework decision

| Option | Verdict |
|---|---|
| **Playwright (Python), sync or async API** | **Recommended.** Auto-waiting, network interception (useful for detecting message-sent/read events instead of polling the DOM), codegen for finding selectors fast, one API across Chromium/Firefox/WebKit. |
| Patchright or stealth patches | Not used. Reliability here must not depend on bypassing platform bot protections. |
| Selenium | Slower, more boilerplate for waits, no built-in network interception. No advantage here. |
| Appium (mobile) | Only needed if `web.snapchat.com` is missing a feature you require (e.g. Snap/story sending) that's mobile-only. Treat as a fallback, not the starting point. |

Use stock Playwright. If Snapchat challenges or blocks a session, stop and use the
account manually rather than trying to bypass the protection.

## Architecture

- **Page Object Model**: keep CSS/text selectors in a `locators.py` (or
  per-page locator classes) separate from logic, so UI changes only touch
  one file.
- **`SnapAutoClient`** class wraps a Playwright `BrowserContext`/`Page` and
  exposes the public API methods.
- **Persistent session**: use Playwright's `storage_state` to save
  cookies/localStorage after login, so `login()` short-circuits to a
  session check on subsequent runs instead of re-authenticating every time.
- **Config**: credentials via `.env` (already gitignored) or OS keyring —
  never hardcoded, never committed.
- **Logging**: structured logging around every action (useful once
  selectors start breaking — you'll want to know exactly which step
  failed).

## Milestones

### Phase 0 — Project setup ✅ Done
- Confirm packaging tool (`uv` recommended for speed, else `poetry`) —
  ask user if not already decided.
- `pyproject.toml`, install `playwright`, run `playwright install
  chromium`.
- `.env.example` for `SNAP_USERNAME` / `SNAP_PASSWORD`.
- Basic project layout:
  ```
  snap_auto/
    __init__.py
    client.py        # SnapAutoClient
    locators.py       # selectors, isolated from logic
    exceptions.py
    config.py
  tests/
  plan.md
  ```

### Phase 1 — Session & auth ✅ Done, verified end-to-end against a real account
- `login(username, password)` — navigate, fill credentials, handle 2FA/OTP
  prompt (likely needs a manual/callback hook since OTP can't be scraped),
  save `storage_state`.
- `verify_login()` — cheapest possible check (e.g. presence of a
  known-logged-in DOM element or a lightweight API call) without a full
  page reload if avoidable.
- `logout()` — click through logout flow, clear stored session state.
- Decide and document how repeated runs reuse a saved session vs. force a
  fresh login.
- OTP/error states use ordered semantic fallbacks (`autocomplete=one-time-code`,
  alert/live-region/test-id selectors). The earlier live account did not present
  an OTP challenge, so that path still requires an opt-in live test when available.

### Phase 2 — Discovery APIs ✅ Implemented
- `get_fnd_list()` — web.snapchat.com has **no dedicated friends page**
  (confirmed via a Playwright codegen session against a real, logged-in
  account); every friend appears as a row in the chat list instead. Derived
  from `get_all_chat_session()` into `{"username", "user_id"}` dicts — only
  covers friends with an existing chat, not the full friend graph. A richer
  source (the "New Chat" dialog's contact picker) was seen in the same
  codegen session but its selectors (an unlabeled search box, `div.nth(3)`)
  are too fragile to use as-is; revisit if the chat-list-derived list proves
  insufficient.
- `get_all_chat_session()` — scans the virtualized sidebar to its bottom and
  parses semantic `title-*`, `status-*`, `time`, `aria-*`, and `/web/<id>`
  attributes into `{"username", "user_id", "preview", "timestamp", "unread"}`.
  The earlier live-confirmed `"{username} , {status}"` row parser remains as a
  compatibility fallback.
- `get_user_id(name)` / `get_user_id(index)` — resolve friend name or list
  index to an id.
- `get_username(index)` — reverse lookup from list index.
- Cache the friend/chat list per session (`refresh=True` forces a re-scrape).
- `user_id` is the stable conversation id from `title-<id>` or `/web/<id>` when
  available; it falls back to the username only for legacy rows without an id.

### Phase 3 — Messaging APIs ✅ Implemented
- `send_msg(user_id, msg_txt)` — resolves `user_id` (id or username) via
  `get_fnd_list()`, opens the matching chat row (`_open_conversation`),
  opens `/web/<conversation-id>` with sidebar/search fallback, fills the semantic
  contenteditable/textbox composer, submits once by send button or Enter, and
  confirms it from the outgoing message/composer state. Returns `False` (not an
  exception) on an unconfirmed timeout, since the message may still have sent.
- `read_msg(user_id)` — opens the conversation and returns every currently
  rendered message bubble as `{"sender", "text", "timestamp", "read"}`
  (`_parse_message_bubble`) from `ul[id^="cv-"] > li`; media-only entries use
  `[Media]`, and read/delivery markers map to a tri-state value.
- Snapchat-specific disappearing-message semantics: resolved as
  non-destructive for now — `read_msg` only opens the conversation and reads
  whatever is currently rendered, without clicking into individual messages,
  so it doesn't itself trigger mark-as-read/expiry beyond that.
- The send path is intentionally not auto-retried after submission, preventing an
  unconfirmed response from creating duplicate messages.

### Phase 4 — Reliability & account safety ✅ Done
- Ordered semantic selector candidates with compatibility fallbacks.
- Bounded exponential retry/backoff for idempotent browser operations only.
- Conservative configurable spacing between actions.
- Private screenshot + DOM + sanitized metadata capture on unexpected failure.
- HTTP 429 and visible throttle/block detection via `RateLimitedError`.
- IndexedDB-aware session persistence, clean lifecycle, and cache invalidation.
- Centralized exception types (`LoginFailedError`, `SessionExpiredError`,
  `SelectorNotFoundError`, `RateLimitedError`, etc.).

### Phase 5 — Testing & docs ✅ Done
- Offline unit tests cover saved DOM snapshots, parsing/mapping, configuration,
  caching, virtualized scan deduplication, retry exhaustion, 429 handling,
  single-submit messaging, Enter fallback, diagnostics, and session persistence.
- Live login/discovery tests require `SNAP_RUN_LIVE_TESTS=1`; sending additionally
  requires `SNAP_RUN_LIVE_SEND_TEST=1`, an exact recipient, and a message.
- GitHub Actions runs lock verification, Ruff, formatting, and pytest across Python
  3.11–3.13 without accessing Snapchat.
- README and `CLAUDE.md` document installation, all core methods, data shapes,
  safety gates, limitations, and selector-drift troubleshooting.

### Phase 6 — Stretch (after core API is solid)
- Send/receive images or Snaps (may require Appium/mobile if web app
  doesn't support it).
- Group chat support.
- Story posting/viewing.
- Event-driven inbound message handling (poll `get_all_chat_session()` on
  an interval, or intercept network responses for push-like updates)
  instead of manual `read_msg()` calls.

## Initial API surface

```python
class SnapAutoClient:
    def login(self, username: str, password: str) -> bool: ...
    def logout(self) -> None: ...
    def verify_login(self) -> bool: ...

    def get_fnd_list(self, refresh: bool = False) -> list[dict]: ...
    def get_all_chat_session(self, refresh: bool = False) -> list[dict]: ...

    def get_user_id(self, name: str | None = None, index: int | None = None) -> str: ...
    def get_username(self, index: int) -> str: ...

    def send_msg(self, user_id: str, msg_txt: str) -> bool: ...
    def read_msg(self, user_id: str) -> list[dict]: ...
```

Note: `get_user_id` is listed twice in the request (by name, by index) —
collapsed here into one method with two optional params; open to splitting
back into two if that's preferred.

## Open questions for user

1. ~~Packaging tool: `uv`, `poetry`, or plain `pip` + `requirements.txt`?~~
   Resolved: `uv`.
2. ~~Sync or async Playwright API?~~ Resolved: sync API.
3. ~~Definition of "user_id" — Snapchat username, or an internal id scraped
   from the DOM/network responses?~~ Resolved: hybrid — every friend/chat
   dict always carries `username`; `user_id` is the conversation id parsed from
   `title-<id>` or `/web/<id>` when present. `get_user_id()` falls back to the
   username for legacy rows that expose no id.
4. ~~2FA on the target account — enabled? If so, `login()` needs a manual
   step or callback the first time.~~ Resolved: `login()` takes an
   `otp_callback` hook (defaults to a blocking stdin prompt); not yet
   exercised against a real challenge.
5. ~~Is a personal test account available to develop/test against, separate
   from any production account?~~ Resolved: yes, in use for Phase 1
   testing.
