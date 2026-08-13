# snap-auto — Implementation Plan

## Overview

Python client for automating Snapchat via browser automation against
`web.snapchat.com` (the official Snapchat web app). Built incrementally,
phase by phase, starting with the 10 core methods below.

**Caveat (read once, move on):** this automates a consumer product with no
public personal-account API, so it relies on scraping a UI that changes
often and actively fights bots. Expect selector breakage over time and
build in the resilience/anti-detection work (Phase 4) rather than skipping
it — accounts can be flagged or locked for automated behavior that doesn't
look human.

## Framework decision

| Option | Verdict |
|---|---|
| **Playwright (Python), sync or async API** | **Recommended.** Auto-waiting, network interception (useful for detecting message-sent/read events instead of polling the DOM), codegen for finding selectors fast, one API across Chromium/Firefox/WebKit. |
| **Patchright** (drop-in Playwright fork with anti-detection patches) | **Recommended upgrade once Phase 1 works.** Patches the CDP-detectable fingerprints stock Playwright leaves behind (the biggest reason Playwright sessions get flagged by bot-detection like PerimeterX/Akamai, which Snap likely fronts its web app with). Same API — swap the import once login starts getting challenged. |
| Selenium | Slower, more boilerplate for waits, no built-in network interception. No advantage here. |
| Appium (mobile) | Only needed if `web.snapchat.com` is missing a feature you require (e.g. Snap/story sending) that's mobile-only. Treat as a fallback, not the starting point. |

Start with Playwright; move to Patchright the moment login/session checks
start getting blocked or captcha'd.

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
- Remaining gaps: `otp_input`/`otp_submit_button`/`login_error_banner`
  selectors are still unverified (no real OTP challenge or rejected login
  hit yet), and the username-step submit button selector is a best-effort
  guess since Snapchat's web login shows inconsistent field labels/languages
  and button text ("Log in" vs "Next") across sessions.

### Phase 2 — Discovery APIs ✅ Implemented, chat list selectors confirmed via codegen; sub-fields still unresolved
- `get_fnd_list()` — web.snapchat.com has **no dedicated friends page**
  (confirmed via a Playwright codegen session against a real, logged-in
  account); every friend appears as a row in the chat list instead. Derived
  from `get_all_chat_session()` into `{"username", "user_id"}` dicts — only
  covers friends with an existing chat, not the full friend graph. A richer
  source (the "New Chat" dialog's contact picker) was seen in the same
  codegen session but its selectors (an unlabeled search box, `div.nth(3)`)
  are too fragile to use as-is; revisit if the chat-list-derived list proves
  insufficient.
- `get_all_chat_session()` — scrapes chat rows, each a `<button>` whose text
  is `"{username} , {status}"` (e.g. `"Anagha Hegde , New Snap"`, `"kiran ,
  Received"`), confirmed via the same codegen session. Parsed via
  `_parse_chat_row` into `{"username", "user_id", "preview", "timestamp",
  "unread"}` dicts — `preview` is the raw status text, `timestamp` and
  `unread` are `None` (no confirmed separate DOM elements for those yet).
- `get_user_id(name)` / `get_user_id(index)` — resolve friend name or list
  index to an id.
- `get_username(index)` — reverse lookup from list index.
- Cache the friend/chat list per session (`refresh=True` forces a re-scrape).
- Gap: `ChatLocators.chat_list_item`/`chat_list_container` use a heuristic
  (`button:has-text(",")`) rather than a real container/class selector —
  works against the confirmed row shape but should be tightened via
  `scripts/inspect_dom.py` if it ever matches unrelated buttons.
  `chat_item_unread_marker`/`chat_item_user_id_attribute` and the Phase 3
  message-thread locators are still `"TODO"`.

### Phase 3 — Messaging APIs
- `send_msg(user_id, msg_txt)` — open conversation, send text, confirm
  delivery (network response or DOM state, not a blind `sleep`).
- `read_msg(user_id)` — open conversation, extract message(s), return
  structured data (sender, text, timestamp, read/unread state).
- Handle Snapchat-specific message semantics (chat messages can
  disappear/expire after being opened — decide whether `read_msg` should
  mark-as-read or attempt a non-destructive read).

### Phase 4 — Reliability & anti-detection
- Migrate to Patchright if not already needed by Phase 1.
- Retry/backoff wrapper for flaky selectors.
- Human-like delays/jitter between actions (avoid fixed sleeps; randomize).
- Screenshot + DOM dump on failure for debugging selector drift.
- Centralized exception types (`LoginFailedError`,
  `SelectorNotFoundError`, `RateLimitedError`, etc.).

### Phase 5 — Testing & docs
- Unit tests for parsing/mapping logic (friend list → id, etc.) using
  saved HTML fixtures — no live account needed.
- A small number of opt-in integration tests that run against a real test
  account (guarded behind an env flag, not run in normal CI).
- Update `CLAUDE.md` with real build/lint/test commands once the packaging
  tool is chosen and structure exists (per its own instructions).
- README usage example for the 10 core methods.

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
   dict always carries `username`; `user_id` is populated opportunistically
   only if `FriendsLocators.friend_user_id_attribute` /
   `ChatLocators.chat_item_user_id_attribute` end up pointing at a real
   data attribute once the DOM is inspected, else it's `None`.
   `get_user_id()` returns `user_id` if present, else falls back to
   `username`.
4. ~~2FA on the target account — enabled? If so, `login()` needs a manual
   step or callback the first time.~~ Resolved: `login()` takes an
   `otp_callback` hook (defaults to a blocking stdin prompt); not yet
   exercised against a real challenge.
5. ~~Is a personal test account available to develop/test against, separate
   from any production account?~~ Resolved: yes, in use for Phase 1
   testing.
