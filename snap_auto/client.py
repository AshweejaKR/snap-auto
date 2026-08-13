"""SnapAutoClient: Playwright-backed automation client for web.snapchat.com."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from snap_auto.config import Config
from snap_auto.exceptions import LoginFailedError, SelectorNotFoundError, UserNotFoundError
from snap_auto.locators import ChatLocators, LoginLocators

BASE_URL = "https://web.snapchat.com"

# Ordinary page elements (nav, form fields, markers).
DEFAULT_TIMEOUT_MS = 15_000
# OTP requires a human to read a code off another device; give them time.
OTP_TIMEOUT_MS = 120_000

logger = logging.getLogger(__name__)


def _prompt_for_otp() -> str:
    """Default OTP fallback: block on stdin. Pass otp_callback to login() to override
    (e.g. to source the code from an SMS-reading service instead of a human)."""
    return input("Snapchat is asking for a 2FA/OTP code. Enter it now: ").strip()


class SnapAutoClient:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.from_env()
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._fnd_list_cache: list[dict] | None = None
        self._chat_session_cache: list[dict] | None = None

    def __enter__(self) -> "SnapAutoClient":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def start(self) -> None:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.config.headless)
        storage_state = (
            str(self.config.storage_state_path)
            if self.config.storage_state_path.exists()
            else None
        )
        self._context = self._browser.new_context(storage_state=storage_state)
        self._page = self._context.new_page()

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    # -- Session & auth (Phase 1) ----------------------------------------

    def login(
        self,
        username: str,
        password: str,
        otp_callback: Callable[[], str] | None = None,
    ) -> bool:
        """Log in to web.snapchat.com, reusing a saved session if one is still valid.

        `otp_callback` is called with no arguments and must return the code as a
        str if Snapchat challenges the login with a 2FA/OTP prompt. Defaults to a
        blocking stdin prompt so first-time/manual runs still work.
        """
        self._require_started()
        assert self._page is not None

        if self.verify_login():
            logger.info("Reusing saved session; skipping login.")
            return True

        otp_callback = otp_callback or _prompt_for_otp

        logger.info("Navigating to %s to log in.", BASE_URL)
        if not self._page.url.startswith(BASE_URL):
            self._page.goto(BASE_URL)

        self._page.locator(LoginLocators.username_input).first.fill(username)
        self._page.locator(LoginLocators.username_submit_button).first.click()
        self._resolve_username_step()

        self._page.locator(LoginLocators.password_input).first.fill(password)
        self._page.locator(LoginLocators.password_submit_button).first.click()
        self._resolve_login_outcome(otp_callback)

        self._save_storage_state()
        logger.info("Login succeeded for %s.", username)
        return True

    def logout(self) -> None:
        self._require_started()
        assert self._page is not None

        self._page.locator(LoginLocators.account_menu_button).first.click()
        self._page.locator(LoginLocators.logout_button).first.click()

        try:
            self._page.wait_for_selector(LoginLocators.username_input, timeout=DEFAULT_TIMEOUT_MS)
        except PlaywrightTimeoutError as exc:
            raise LoginFailedError("Logout did not return to the login page as expected.") from exc

        if self.config.storage_state_path.exists():
            self.config.storage_state_path.unlink()

        self._fnd_list_cache = None
        self._chat_session_cache = None
        logger.info("Logged out and cleared saved session state.")

    def verify_login(self) -> bool:
        self._require_started()
        assert self._page is not None

        if not self._page.url.startswith(BASE_URL):
            self._page.goto(BASE_URL)

        try:
            self._page.wait_for_selector(LoginLocators.logged_in_marker, timeout=DEFAULT_TIMEOUT_MS)
            return True
        except PlaywrightTimeoutError:
            return False

    # -- Discovery (Phase 2) ----------------------------------------------

    def get_fnd_list(self, refresh: bool = False) -> list[dict]:
        """Scrape the friends list into structured dicts, caching per session.

        web.snapchat.com has no dedicated friends page, so this is derived from
        get_all_chat_session() — every chat row is a friend. Each dict has
        'username' (str) and 'user_id' (str, or None if no internal id is
        discoverable — see ChatLocators.chat_item_user_id_attribute). This only
        covers friends you have an existing chat with, not your full friend graph.
        Pass refresh=True to force a re-scrape instead of returning the cached list.
        """
        if self._fnd_list_cache is not None and not refresh:
            return self._fnd_list_cache

        sessions = self.get_all_chat_session(refresh=refresh)
        friends = [{"username": s["username"], "user_id": s["user_id"]} for s in sessions]
        self._fnd_list_cache = friends
        return friends

    def get_all_chat_session(self, refresh: bool = False) -> list[dict]:
        """Scrape the chat/conversation list into structured dicts, caching per session.

        Each row's accessible text is "{username} , {status}" (confirmed via a
        live codegen session, e.g. "Anagha Hegde , New Snap"); see _parse_chat_row.
        Each dict has 'username', 'user_id' (opportunistic, may be None), 'preview'
        (the raw status text, e.g. "New Snap"/"Say Hi!"/"Received"), 'timestamp'
        (None — no confirmed separate element yet), and 'unread' (None — no
        confirmed presence-based marker yet; status text alone isn't a reliable
        enough signal to turn into a bool). Pass refresh=True to force a re-scrape
        instead of returning the cached list.
        """
        if self._chat_session_cache is not None and not refresh:
            return self._chat_session_cache
        self._require_started()
        assert self._page is not None

        self._click_if_present(ChatLocators.nav_button)
        self._page.locator(ChatLocators.chat_list_container).first.wait_for(
            timeout=DEFAULT_TIMEOUT_MS
        )

        items = self._page.locator(ChatLocators.chat_list_item)
        sessions: list[dict] = []
        for i in range(items.count()):
            item = items.nth(i)
            text = item.text_content()
            if not text:
                continue
            username, status = self._parse_chat_row(text)
            if not username:
                continue
            sessions.append(
                {
                    "username": username,
                    "user_id": self._opportunistic_attr(
                        item, ChatLocators.chat_item_user_id_attribute
                    ),
                    "preview": status or None,
                    "timestamp": None,
                    "unread": self._unread_state(item),
                }
            )

        self._chat_session_cache = sessions
        return sessions

    def get_user_id(self, name: str | None = None, index: int | None = None) -> str:
        """Resolve a friend to an id: name lookup or list-index lookup (exactly one).

        Returns the internal id if one was discoverable (see get_fnd_list), else
        falls back to the username itself, since Snapchat's web UI doesn't reliably
        expose a raw numeric id.
        """
        if (name is None) == (index is None):
            raise ValueError("Provide exactly one of 'name' or 'index'.")

        friends = self.get_fnd_list()
        if index is not None:
            friend = self._friend_at_index(friends, index)
        else:
            matches = [f for f in friends if f["username"] == name]
            if not matches:
                raise UserNotFoundError(f"No friend found with username {name!r}.")
            friend = matches[0]

        return friend["user_id"] or friend["username"]

    def get_username(self, index: int) -> str:
        """Reverse lookup: friend list index -> username."""
        friends = self.get_fnd_list()
        return self._friend_at_index(friends, index)["username"]

    # -- Messaging (Phase 3) -----------------------------------------------

    def send_msg(self, user_id: str, msg_txt: str) -> bool:
        """Open the conversation with user_id (username or resolved id), send
        msg_txt, and confirm delivery via DOM state (input cleared + a new
        message bubble landed) rather than a blind sleep.

        Returns True if delivery was confirmed within DEFAULT_TIMEOUT_MS, False
        otherwise (message may or may not have actually sent - caller should
        treat False as "unconfirmed", not necessarily "failed").
        """
        self._require_started()
        assert self._page is not None

        self._open_conversation(user_id)

        message_input = self._page.locator(ChatLocators.message_input).first
        message_input.click()
        message_input.fill(msg_txt)

        bubbles_before = self._page.locator(ChatLocators.message_bubble).count()
        self._page.locator(ChatLocators.send_button).first.click()

        return self._confirm_message_sent(message_input, bubbles_before)

    def read_msg(self, user_id: str) -> list[dict]:
        """Open the conversation with user_id (username or resolved id) and
        return its visible messages as structured dicts: 'sender', 'text',
        'timestamp', 'read' (bool, or None if no read-marker element is
        confirmed - see ChatLocators.message_bubble_read_marker).

        Note: Snapchat chat messages can disappear/expire once opened. This
        reads whatever is currently rendered without taking any action beyond
        opening the conversation, so it doesn't itself trigger a mark-as-read.
        """
        self._require_started()
        assert self._page is not None

        self._open_conversation(user_id)

        bubbles = self._page.locator(ChatLocators.message_bubble)
        try:
            bubbles.first.wait_for(timeout=DEFAULT_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            return []

        return [self._parse_message_bubble(bubbles.nth(i)) for i in range(bubbles.count())]

    # -- internal helpers ---------------------------------------------------

    def _require_started(self) -> None:
        if self._page is None:
            raise RuntimeError(
                "Client not started; call start() or use 'with SnapAutoClient() as client:'."
            )

    def _resolve_username_step(self) -> None:
        """After submitting the username-only page, wait for the navigation to the
        separate password page (or a rejection, e.g. "user not found")."""
        assert self._page is not None

        password_input = self._page.locator(LoginLocators.password_input)
        error = self._page.locator(LoginLocators.login_error_banner)

        outcome = self._wait_for_any(
            [(password_input, "password"), (error, "error")],
            timeout_ms=DEFAULT_TIMEOUT_MS,
        )

        if outcome == "password":
            return

        if outcome == "error":
            message = error.first.text_content() or "Snapchat rejected the username."
            raise LoginFailedError(message.strip())

        raise LoginFailedError(
            "Username step did not reach the password page (no password field or error appeared)."
        )

    def _resolve_login_outcome(self, otp_callback: Callable[[], str]) -> None:
        """After submitting credentials, resolve to success, an OTP challenge, or failure."""
        assert self._page is not None

        marker = self._page.locator(LoginLocators.logged_in_marker)
        otp = self._page.locator(LoginLocators.otp_input)
        error = self._page.locator(LoginLocators.login_error_banner)

        outcome = self._wait_for_any(
            [(marker, "success"), (otp, "otp"), (error, "error")],
            timeout_ms=DEFAULT_TIMEOUT_MS,
        )

        if outcome == "success":
            self._dismiss_post_login_interstitial()
            return

        if outcome == "error":
            message = error.first.text_content() or "Login rejected by Snapchat."
            raise LoginFailedError(message.strip())

        if outcome == "otp":
            code = otp_callback()
            if not code:
                raise LoginFailedError("No OTP code provided.")
            otp.first.fill(code)
            self._page.locator(LoginLocators.otp_submit_button).first.click()
            try:
                marker.first.wait_for(timeout=OTP_TIMEOUT_MS)
            except PlaywrightTimeoutError as exc:
                raise LoginFailedError("Login failed after submitting OTP code.") from exc
            self._dismiss_post_login_interstitial()
            return

        raise LoginFailedError(
            "Login did not reach a known outcome (no success/OTP/error marker appeared)."
        )

    def _dismiss_post_login_interstitial(self) -> None:
        """Best-effort dismissal of a post-login nag screen (e.g. 'enable notifications?').
        Not every account/session shows one, so this is a no-op if it's absent."""
        assert self._page is not None
        dismiss = self._page.locator(LoginLocators.post_login_dismiss_button)
        if dismiss.count() > 0:
            dismiss.first.click()

    def _wait_for_any(
        self, candidates: list[tuple[Locator, str]], timeout_ms: int
    ) -> str | None:
        """Poll several locators until one has a match; return its tag, or None on timeout.

        Plain polling (rather than a single combined selector) keeps this agnostic
        to whatever selector syntax locators.py ends up using per-case (CSS, text=,
        etc.) once real selectors replace the current TODO placeholders.
        """
        assert self._page is not None
        poll_interval_ms = 250
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            for locator, tag in candidates:
                if locator.count() > 0:
                    return tag
            self._page.wait_for_timeout(poll_interval_ms)
        return None

    def _save_storage_state(self) -> None:
        assert self._context is not None
        self.config.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        self._context.storage_state(path=str(self.config.storage_state_path))

    def _click_if_present(self, selector: str) -> None:
        """Best-effort nav click, mirroring _dismiss_post_login_interstitial: a no-op
        if the selector is an unresolved TODO or the control isn't present (e.g. the
        target view is already showing)."""
        if selector == "TODO":
            return
        assert self._page is not None
        control = self._page.locator(selector)
        if control.count() > 0:
            control.first.click()

    def _text_or_none(self, locator: Locator) -> str | None:
        if locator.count() == 0:
            return None
        text = locator.first.text_content()
        return text.strip() if text else None

    def _parse_chat_row(self, text: str) -> tuple[str, str]:
        """Split a chat row's combined accessible text "{username} , {status}"
        into its parts. Falls back to (text, "") if the separator isn't present,
        so callers still get a username instead of dropping the row."""
        username, sep, status = text.partition(" , ")
        if not sep:
            return text.strip(), ""
        return username.strip(), status.strip()

    def _opportunistic_attr(self, item: Locator, attribute: str) -> str | None:
        """Best-effort scrape of an internal id from a data-* attribute on a list
        item, if one has been identified and filled into locators.py. Returns None
        (callers fall back to username as the id) until that TODO is resolved."""
        if attribute == "TODO":
            return None
        return item.get_attribute(attribute)

    def _unread_state(self, item: Locator) -> bool | None:
        if ChatLocators.chat_item_unread_marker == "TODO":
            return None
        return item.locator(ChatLocators.chat_item_unread_marker).count() > 0

    def _open_conversation(self, user_id: str) -> None:
        """Resolve user_id (an id or, per get_user_id's fallback, a username) to
        a friend, click their chat-list row, and wait for the message thread to
        open."""
        assert self._page is not None

        friends = self.get_fnd_list()
        matches = [f for f in friends if f["user_id"] == user_id or f["username"] == user_id]
        if not matches:
            raise UserNotFoundError(f"No friend found for user_id/username {user_id!r}.")
        username = matches[0]["username"]

        self._click_if_present(ChatLocators.nav_button)
        items = self._page.locator(ChatLocators.chat_list_item)
        for i in range(items.count()):
            item = items.nth(i)
            row_username, _ = self._parse_chat_row(item.text_content() or "")
            if row_username == username:
                item.click()
                break
        else:
            raise UserNotFoundError(f"No chat row found for username {username!r}.")

        try:
            self._page.locator(ChatLocators.message_input).first.wait_for(timeout=DEFAULT_TIMEOUT_MS)
        except PlaywrightTimeoutError as exc:
            raise SelectorNotFoundError(
                "Conversation view did not open (message input not found)."
            ) from exc

    def _confirm_message_sent(
        self, message_input: Locator, bubbles_before: int, timeout_ms: int = DEFAULT_TIMEOUT_MS
    ) -> bool:
        """Poll DOM state instead of sleeping a fixed amount: delivery counts as
        confirmed once the compose box has cleared itself AND a new bubble has
        landed in the thread (both are how web.snapchat.com's optimistic-send UI
        is expected to behave; revisit if either signal proves unreliable)."""
        assert self._page is not None
        poll_interval_ms = 250
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            input_cleared = (message_input.input_value() or "") == ""
            bubble_added = self._page.locator(ChatLocators.message_bubble).count() > bubbles_before
            if input_cleared and bubble_added:
                return True
            self._page.wait_for_timeout(poll_interval_ms)
        return False

    def _parse_message_bubble(self, bubble: Locator) -> dict:
        text = self._text_or_none(bubble.locator(ChatLocators.message_bubble_text))
        if text is None:
            raw = bubble.text_content()
            text = raw.strip() if raw else None
        return {
            "sender": self._text_or_none(bubble.locator(ChatLocators.message_bubble_sender)),
            "text": text,
            "timestamp": self._text_or_none(bubble.locator(ChatLocators.message_bubble_timestamp)),
            "read": self._bubble_read_state(bubble),
        }

    def _bubble_read_state(self, bubble: Locator) -> bool | None:
        if ChatLocators.message_bubble_read_marker == "TODO":
            return None
        return bubble.locator(ChatLocators.message_bubble_read_marker).count() > 0

    def _friend_at_index(self, friends: list[dict], index: int) -> dict:
        try:
            return friends[index]
        except IndexError as exc:
            raise UserNotFoundError(
                f"No friend at index {index} (list has {len(friends)})."
            ) from exc
