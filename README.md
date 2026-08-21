# snap-auto

A synchronous Python client that automates the Snapchat Web UI with Playwright.
It provides session reuse, chat discovery, user/conversation lookup, text sending,
and visible-message reading behind one `SnapAutoClient` API.

> Snapchat does not provide a public personal-account automation API. This project
> drives a changing consumer web UI, so selectors may eventually drift and automated
> activity may trigger an account challenge or lock. Use a dedicated test account,
> keep volume low, and stop if Snapchat displays a challenge or rate limit.

## Status

Core Phases 0–5 in [`plan.md`](plan.md) are implemented:

- `uv` package and reproducible lock file
- login, OTP callback, saved-session reuse, verification, and logout
- virtualized chat-sidebar scanning and cached friend/chat lookup
- single-send text messaging with confirmation and visible-message parsing
- ordered selector fallbacks, bounded idempotent retries, HTTP 429 handling, and
  private failure artifacts
- offline tests, opt-in live tests, lint/format checks, and GitHub Actions CI

Phase 1 was previously smoke-tested against a real account. Normal CI is deliberately
offline; live authentication/messaging must be verified with your dedicated test
account because credentials and browser state are never committed.

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- Chromium installed through Playwright

## Setup

```bash
git clone https://github.com/AshweejaKR/snap-auto.git
cd snap-auto
git switch phase-0-project-setup
uv sync --all-groups
uv run playwright install chromium
cp .env.example .env
```

On Windows PowerShell, use `Copy-Item .env.example .env` for the last command.
Fill in only your dedicated test-account credentials:

```dotenv
SNAP_USERNAME=your_test_username
SNAP_PASSWORD=your_test_password
SNAP_HEADLESS=false
```

Use headed mode for the initial login/OTP. After a successful login, cookies,
localStorage, and IndexedDB state are stored in `.auth/storage_state.json`; later
runs can normally use `SNAP_HEADLESS=true` and reuse that session.

## Usage

```python
from snap_auto import SnapAutoClient

with SnapAutoClient() as client:
    # Uses SNAP_USERNAME/SNAP_PASSWORD from .env. Credentials can instead be
    # passed as client.login(username="...", password="...").
    client.login()
    assert client.verify_login()

    chats = client.get_all_chat_session(refresh=True)
    friends = client.get_fnd_list()

    conversation_id = client.get_user_id(name="exact_snapchat_username")

    confirmed = client.send_msg(conversation_id, "Hello from snap-auto")
    if not confirmed:
        # Do not immediately send again: the first message may have succeeded.
        print("Message submission was not confirmed")

    messages = client.read_msg(conversation_id)
    for message in messages:
        print(message)
```

Call `client.logout()` only when you want to end the Snapchat session and delete
the saved local state.

### 2FA/OTP

If Snapchat presents a one-time-code field, `login()` prompts on stdin by default.
You can supply a callback instead:

```python
client.login(otp_callback=lambda: input("OTP: ").strip())
```

The callback must obtain a code for an account you control. The library does not
attempt to intercept SMS, email, or bypass a challenge.

## Public API

| Method | Result |
|---|---|
| `login(username=None, password=None, otp_callback=None)` | Authenticates or reuses valid saved state |
| `verify_login()` | `True` only when an authenticated app marker is visible |
| `logout()` | Logs out and clears local session/cache state |
| `get_all_chat_session(refresh=False)` | Chat dictionaries from the full scanned sidebar |
| `get_fnd_list(refresh=False)` | `username`/`user_id` projection of chats |
| `get_user_id(name=... or index=...)` | Conversation id, with username fallback for legacy rows |
| `get_username(index)` | Username at a cached friend-list index |
| `send_msg(user_id, msg_txt)` | Sends once; returns whether UI confirmation succeeded |
| `read_msg(user_id)` | Currently rendered message dictionaries |

Chat dictionaries have this shape:

```python
{
    "username": str,
    "user_id": str | None,  # Snapchat Web conversation id
    "preview": str | None,
    "timestamp": str | None,
    "unread": bool | None,
}
```

Message dictionaries have this shape:

```python
{
    "sender": str | None,
    "text": str,  # "[Media]" for media-only rendered entries
    "timestamp": str | None,
    "read": bool | None,  # seen/opened=True, sent/delivered=False
}
```

## Configuration

All supported environment variables and defaults are documented in
[`.env.example`](.env.example). Important controls include:

- `SNAP_BASE_URL` — defaults to `https://www.snapchat.com/web`
- `SNAP_DEFAULT_TIMEOUT_MS` / `SNAP_NAVIGATION_TIMEOUT_MS`
- `SNAP_ACTION_RETRIES` — applies only to idempotent operations, never a submitted
  message
- `SNAP_RATE_LIMIT_COOLDOWN_SECONDS`
- `SNAP_CAPTURE_FAILURE_ARTIFACTS` / `SNAP_ARTIFACTS_PATH`

## Testing and development

Offline checks do not launch a browser or contact Snapchat:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv build
```

To run the live login/discovery smoke test, configure a dedicated account and set:

```bash
SNAP_RUN_LIVE_TESTS=1 SNAP_HEADLESS=false uv run pytest -m live -k login
```

The send test has an additional explicit gate and sends exactly one real message:

```bash
SNAP_RUN_LIVE_TESTS=1 \
SNAP_RUN_LIVE_SEND_TEST=1 \
SNAP_LIVE_RECIPIENT=exact_username \
SNAP_LIVE_MESSAGE="snap-auto smoke test" \
SNAP_HEADLESS=false \
uv run pytest -m live_send
```

The same gated flow is available as `scripts/manual_messaging_test.py`.

## Limitations and privacy

- `get_fnd_list()` contains people with chat rows, not Snapchat's entire friend
  graph.
- `read_msg()` opens the conversation; Snapchat may mark content as opened and may
  apply its normal disappearing-message behavior.
- Only visible text/media placeholders are supported. Sending Snaps/images, group
  chat behavior, stories, and event streaming remain Phase 6 stretch work.
- `.auth/` contains reusable account state. `.snap-auto-artifacts/` screenshots and
  HTML may contain private chats. Both are gitignored; protect or delete them after
  debugging.
- On `send_msg()` returning `False`, inspect the conversation before retrying to
  avoid a duplicate.

When the UI changes, run `scripts/inspect_dom.py` headed and add a semantic fallback
to `snap_auto/locators.py`. Do not replace stable selectors with generated CSS
classes unless no semantic alternative exists.
