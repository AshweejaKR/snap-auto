"""Playwright-backed automation client for Snapchat Web."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Self, TypeVar
from urllib.parse import quote, urlsplit, urlunsplit

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    Response,
    sync_playwright,
)
from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from snap_auto.config import Config
from snap_auto.exceptions import (
    LoginFailedError,
    RateLimitedError,
    SelectorNotFoundError,
    SessionExpiredError,
    UserNotFoundError,
)
from snap_auto.locators import ChatLocators, LoginLocators, SelectorSpec
from snap_auto.parsing import (
    conversation_id_from,
    infer_unread_state,
    normalize_text,
    parse_chat_row_text,
    parse_message_snapshot,
)

OTP_TIMEOUT_MS = 120_000
_RATE_LIMIT_TEXT = re.compile(
    r"too many requests|rate.?limit|try again later|temporarily blocked", re.IGNORECASE
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _prompt_for_otp() -> str:
    """Default manual fallback for first-time 2FA challenges."""

    return input("Snapchat is asking for a 2FA/OTP code. Enter it now: ").strip()


class SnapAutoClient:
    """Synchronous Snapchat Web client.

    The client is intentionally single-user and single-threaded. Use it as a
    context manager so Chromium and the saved session are closed cleanly.
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.from_env()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._authenticated = False
        self._fnd_list_cache: list[dict[str, object]] | None = None
        self._chat_session_cache: list[dict[str, object]] | None = None
        self._last_action_at = 0.0
        self._rate_limited_at: float | None = None
        self._rate_limited_url = ""
        self._last_rate_limit_text_check_at = 0.0
        self._artifact_counter = 0

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def start(self) -> None:
        """Start Chromium and create a browser context. Calling twice is safe."""

        if self._page is not None and not self._page.is_closed():
            return

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(
                headless=self.config.headless
            )
            self._context = self._new_browser_context()
            self._context.set_default_timeout(self.config.default_timeout_ms)
            self._context.set_default_navigation_timeout(
                self.config.navigation_timeout_ms
            )
            self._page = self._context.new_page()
            self._page.on("response", self._on_response)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Persist an authenticated session and release browser resources."""

        if self._authenticated and self._context is not None:
            try:
                self._save_storage_state()
            except (OSError, PlaywrightError):
                logger.warning("Could not persist the browser session during close.")

        for resource in (self._context, self._browser, self._playwright):
            if resource is None:
                continue
            try:
                if resource is self._playwright:
                    resource.stop()
                else:
                    resource.close()
            except PlaywrightError:
                logger.debug("Browser resource was already closed.", exc_info=True)

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._authenticated = False
        self._invalidate_caches()

    # -- Session and authentication -------------------------------------

    def login(
        self,
        username: str | None = None,
        password: str | None = None,
        otp_callback: Callable[[], str] | None = None,
    ) -> bool:
        """Log in, reusing a saved session when it is still valid.

        Credentials may be passed directly or loaded from ``Config``. If Snapchat
        presents a 2FA field, ``otp_callback`` supplies the one-time code; the
        default prompts on stdin.
        """

        self._require_started()
        assert self._page is not None
        resolved_username, resolved_password = self.config.resolve_credentials(
            username, password
        )

        if self.verify_login():
            logger.info("Reusing a valid saved Snapchat session.")
            return True

        otp_callback = otp_callback or _prompt_for_otp
        self._navigate_to_app()

        username_input = self._wait_for_locator(
            LoginLocators.username_input, description="username field"
        )
        username_input.fill(resolved_username)
        self._safe_click(
            self._wait_for_locator(
                LoginLocators.username_submit_button,
                description="username submit button",
            )
        )
        self._resolve_username_step()

        password_input = self._wait_for_locator(
            LoginLocators.password_input, description="password field"
        )
        password_input.fill(resolved_password)
        self._safe_click(
            self._wait_for_locator(
                LoginLocators.password_submit_button,
                description="password submit button",
            )
        )
        self._resolve_login_outcome(otp_callback)

        self._authenticated = True
        self._invalidate_caches()
        self._save_storage_state()
        logger.info("Snapchat login succeeded.")
        return True

    def logout(self) -> None:
        """Log out in the UI and remove local cookies/session state."""

        self._require_started()
        assert self._page is not None

        if not self.verify_login():
            self._clear_local_session()
            return

        menu = self._wait_for_locator(
            LoginLocators.account_menu_button, description="account menu"
        )
        self._safe_click(menu)
        logout_control = self._wait_for_locator(
            LoginLocators.logout_button, description="logout control"
        )
        self._safe_click(logout_control)

        outcome = self._wait_for_any(
            [(LoginLocators.username_input, "login")],
            timeout_ms=self.config.default_timeout_ms,
        )
        self._clear_local_session()
        if outcome is None:
            raise LoginFailedError(
                "Logout was requested, but Snapchat did not return to a login page. "
                "Local session data was still cleared."
            )
        logger.info("Logged out and cleared local session state.")

    def verify_login(self) -> bool:
        """Return whether the current/saved browser session is authenticated."""

        self._require_started()
        assert self._page is not None

        if self._page.url == "about:blank" or not self._is_snapchat_url(self._page.url):
            self._navigate_to_app()

        outcome = self._wait_for_any(
            [
                (LoginLocators.logged_in_marker, "authenticated"),
                (ChatLocators.message_input, "authenticated"),
                (LoginLocators.username_input, "login"),
                (LoginLocators.password_input, "login"),
            ],
            timeout_ms=self.config.default_timeout_ms,
        )
        self._authenticated = outcome is not None and outcome[0] == "authenticated"
        return self._authenticated

    # -- Discovery -------------------------------------------------------

    def get_fnd_list(self, refresh: bool = False) -> list[dict]:
        """Return friends represented in the chat list.

        Snapchat Web does not expose a dedicated full-friends page, so this is a
        projection of chat sessions. ``user_id`` is the conversation id when the
        DOM exposes one, otherwise ``None``.
        """

        if self._fnd_list_cache is not None and not refresh:
            return [dict(friend) for friend in self._fnd_list_cache]

        sessions = self.get_all_chat_session(refresh=refresh)
        friends = [
            {"username": session["username"], "user_id": session["user_id"]}
            for session in sessions
        ]
        self._fnd_list_cache = [dict(friend) for friend in friends]
        return friends

    def get_all_chat_session(self, refresh: bool = False) -> list[dict]:
        """Return cached or freshly scraped chat sessions.

        A fresh scan walks the virtualized sidebar until its bottom, deduplicating
        rows by conversation id (or username when no id is exposed).
        """

        if self._chat_session_cache is not None and not refresh:
            return [dict(session) for session in self._chat_session_cache]

        self._ensure_authenticated()
        sessions = self._run_with_retries("scan-chat-list", self._collect_chat_sessions)
        self._chat_session_cache = [dict(session) for session in sessions]
        self._fnd_list_cache = None
        return [dict(session) for session in sessions]

    def get_user_id(self, name: str | None = None, index: int | None = None) -> str:
        """Resolve exactly one username or friend-list index to an id.

        If a conversation id is not exposed by the UI, the username is returned as
        a backward-compatible fallback.
        """

        if (name is None) == (index is None):
            raise ValueError("Provide exactly one of 'name' or 'index'.")

        friends = self.get_fnd_list()
        if index is not None:
            friend = self._friend_at_index(friends, index)
        else:
            assert name is not None
            normalized_name = normalize_text(name).casefold()
            friend = next(
                (
                    item
                    for item in friends
                    if normalize_text(item["username"]).casefold() == normalized_name
                ),
                None,
            )
            if friend is None:
                raise UserNotFoundError(f"No friend found with username {name!r}.")
        return str(friend["user_id"] or friend["username"])

    def get_username(self, index: int) -> str:
        """Resolve a friend-list index to its username."""

        return str(self._friend_at_index(self.get_fnd_list(), index)["username"])

    # -- Messaging -------------------------------------------------------

    def send_msg(self, user_id: str, msg_txt: str) -> bool:
        """Send one text message and confirm it without retrying the send action.

        A ``False`` return means the submission could not be confirmed; it does
        not prove the message failed. The method intentionally never retries after
        submission because doing so could produce duplicate messages.
        """

        message = str(msg_txt)
        if not message.strip():
            raise ValueError("msg_txt must not be empty.")

        self._ensure_authenticated()
        self._raise_if_rate_limited()
        self._open_conversation(user_id)
        assert self._page is not None

        composer = self._wait_for_locator(
            ChatLocators.message_input, description="message composer"
        )
        bubbles_before = self._message_bubbles().count()
        self._set_composer_text(composer, message)

        send_button = self._first_matching(ChatLocators.send_button)
        if send_button is not None:
            self._safe_click(send_button)
        else:
            self._polite_delay()
            composer.press("Enter")
            self._last_action_at = time.monotonic()

        confirmed = self._confirm_message_sent(
            composer, bubbles_before=bubbles_before, expected_text=message
        )
        if not confirmed:
            self._capture_diagnostics("message-send-unconfirmed")
        return confirmed

    def read_msg(self, user_id: str) -> list[dict]:
        """Open a conversation and return currently rendered text/media entries."""

        self._ensure_authenticated()
        self._open_conversation(user_id)
        assert self._page is not None
        self._page.wait_for_timeout(400)

        messages: list[dict] = []
        bubbles = self._message_bubbles()
        for index in range(bubbles.count()):
            parsed = self._parse_message_bubble(bubbles.nth(index))
            if parsed is not None:
                messages.append(parsed)
        return messages

    # -- Browser/session helpers ----------------------------------------

    def _new_browser_context(self) -> BrowserContext:
        assert self._browser is not None
        context_options: dict[str, object] = {
            "viewport": {"width": 1440, "height": 960},
        }
        if self.config.storage_state_path.exists():
            context_options["storage_state"] = str(self.config.storage_state_path)

        try:
            return self._browser.new_context(**context_options)
        except PlaywrightError:
            if "storage_state" not in context_options:
                raise
            logger.warning(
                "Saved storage state could not be loaded; starting a clean session."
            )
            context_options.pop("storage_state")
            return self._browser.new_context(**context_options)

    def _require_started(self) -> None:
        if self._page is None or self._page.is_closed():
            raise RuntimeError(
                "Client not started; call start() or use "
                "'with SnapAutoClient() as client:'."
            )

    def _navigate_to_app(self) -> None:
        assert self._page is not None

        def navigate() -> None:
            assert self._page is not None
            self._page.goto(
                self.config.base_url,
                wait_until="domcontentloaded",
                timeout=self.config.navigation_timeout_ms,
            )

        self._run_with_retries("navigate-to-snapchat", navigate)

    def _is_snapchat_url(self, url: str) -> bool:
        host = urlsplit(url).hostname or ""
        return host == "snapchat.com" or host.endswith(".snapchat.com")

    def _ensure_authenticated(self) -> None:
        self._require_started()
        if self._authenticated and (
            self._first_matching(LoginLocators.logged_in_marker) is not None
            or self._first_matching(ChatLocators.message_input) is not None
        ):
            return
        if not self.verify_login():
            raise SessionExpiredError(
                "Snapchat session is not authenticated; call login() first."
            )

    def _save_storage_state(self) -> None:
        assert self._context is not None
        path = self.config.storage_state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._context.storage_state(path=str(path), indexed_db=True)
        except TypeError:  # compatibility with older Playwright releases
            self._context.storage_state(path=str(path))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _clear_local_session(self) -> None:
        if self._context is not None:
            try:
                self._context.clear_cookies()
            except PlaywrightError:
                pass
        if self._page is not None and not self._page.is_closed():
            try:
                self._page.evaluate("localStorage.clear(); sessionStorage.clear();")
            except PlaywrightError:
                pass
        self.config.storage_state_path.unlink(missing_ok=True)
        self._authenticated = False
        self._invalidate_caches()

    def _invalidate_caches(self) -> None:
        self._fnd_list_cache = None
        self._chat_session_cache = None

    # -- Authentication flow helpers -----------------------------------

    def _resolve_username_step(self) -> None:
        outcome = self._wait_for_any(
            [
                (LoginLocators.password_input, "password"),
                (LoginLocators.login_error_banner, "error"),
            ],
            timeout_ms=self.config.default_timeout_ms,
        )
        if outcome is None:
            self._capture_diagnostics("username-step-timeout")
            raise LoginFailedError(
                "Username step did not reach a password field or an error message."
            )
        tag, locator = outcome
        if tag == "password":
            return
        message = (
            normalize_text(locator.text_content()) or "Snapchat rejected the username."
        )
        raise LoginFailedError(message)

    def _resolve_login_outcome(self, otp_callback: Callable[[], str]) -> None:
        outcome = self._wait_for_any(
            [
                (LoginLocators.logged_in_marker, "success"),
                (ChatLocators.message_input, "success"),
                (LoginLocators.otp_input, "otp"),
                (LoginLocators.login_error_banner, "error"),
            ],
            timeout_ms=self.config.default_timeout_ms,
        )
        if outcome is None:
            self._capture_diagnostics("login-outcome-timeout")
            raise LoginFailedError(
                "Login did not reach a success, OTP, or error state."
            )

        tag, locator = outcome
        if tag == "success":
            self._dismiss_post_login_interstitial()
            return
        if tag == "error":
            message = (
                normalize_text(locator.text_content()) or "Login rejected by Snapchat."
            )
            raise LoginFailedError(message)

        code = otp_callback().strip()
        if not code:
            raise LoginFailedError("No OTP code was provided.")
        locator.fill(code)
        self._safe_click(
            self._wait_for_locator(
                LoginLocators.otp_submit_button, description="OTP submit button"
            )
        )
        otp_outcome = self._wait_for_any(
            [
                (LoginLocators.logged_in_marker, "success"),
                (ChatLocators.message_input, "success"),
                (LoginLocators.login_error_banner, "error"),
            ],
            timeout_ms=OTP_TIMEOUT_MS,
        )
        if otp_outcome is None or otp_outcome[0] != "success":
            message = (
                normalize_text(otp_outcome[1].text_content())
                if otp_outcome is not None
                else "Login failed after submitting the OTP code."
            )
            raise LoginFailedError(message)
        self._dismiss_post_login_interstitial()

    def _dismiss_post_login_interstitial(self) -> None:
        dismiss = self._first_matching(LoginLocators.post_login_dismiss_button)
        if dismiss is not None:
            self._safe_click(dismiss)

    # -- Chat discovery/open helpers ------------------------------------

    def _collect_chat_sessions(self) -> list[dict[str, object]]:
        assert self._page is not None
        self._clear_chat_search()
        self._click_if_present(ChatLocators.nav_button)
        self._scroll_chat_list("top")

        sessions_by_key: dict[str, dict[str, object]] = {}
        idle_passes = 0
        for _ in range(self.config.max_chat_scrolls):
            before = len(sessions_by_key)
            for session in self._snapshot_visible_chats():
                key = str(session["user_id"] or session["username"]).casefold()
                sessions_by_key.setdefault(key, session)

            idle_passes = idle_passes + 1 if len(sessions_by_key) == before else 0
            scroll = self._scroll_chat_list("down")
            if bool(scroll.get("at_bottom")) or (
                not bool(scroll.get("moved")) and idle_passes >= 2
            ):
                break

        self._scroll_chat_list("top")
        return list(sessions_by_key.values())

    def _snapshot_visible_chats(self) -> list[dict[str, object]]:
        items = self._first_collection(ChatLocators.chat_list_item)
        if items is None:
            return []

        sessions: list[dict[str, object]] = []
        for index in range(items.count()):
            item = items.nth(index)
            raw_text = normalize_text(item.text_content())
            fallback_username, fallback_status = parse_chat_row_text(raw_text)
            username = self._text_from(item, ChatLocators.chat_item_username)
            status = self._text_from(item, ChatLocators.chat_item_preview)
            username = username or fallback_username
            status = status or fallback_status
            if not username:
                continue

            title = self._first_matching(
                ChatLocators.chat_item_username, scope=item, visible=False
            )
            title_id = title.get_attribute("id") if title is not None else None
            user_id = conversation_id_from(
                aria_labelledby=item.get_attribute("aria-labelledby"),
                title_element_id=title_id,
                href=item.get_attribute("href"),
            )
            timestamp_locator = self._first_matching(
                ChatLocators.chat_item_timestamp, scope=item, visible=False
            )
            timestamp = self._timestamp_from(timestamp_locator)
            unread_marker = self._first_matching(
                ChatLocators.chat_item_unread_marker, scope=item, visible=False
            )
            unread = (
                True
                if unread_marker is not None
                else infer_unread_state(
                    aria_label=item.get_attribute("aria-label"),
                    class_name=item.get_attribute("class"),
                    status=status,
                )
            )
            sessions.append(
                {
                    "username": username,
                    "user_id": user_id,
                    "preview": status or None,
                    "timestamp": timestamp,
                    "unread": unread,
                }
            )
        return sessions

    def _scroll_chat_list(self, direction: str) -> dict[str, object]:
        assert self._page is not None
        try:
            result = self._page.evaluate(
                """
                ({ selector, direction }) => {
                    const row = document.querySelector(selector);
                    if (!row) return { moved: false, at_bottom: true };

                    const candidates = [];
                    let parent = row.parentElement;
                    while (parent) {
                        if (parent.scrollHeight > parent.clientHeight + 8) {
                            candidates.push(parent);
                        }
                        parent = parent.parentElement;
                    }
                    const scroller = candidates[0] || document.scrollingElement;
                    if (!scroller) return { moved: false, at_bottom: true };

                    const before = scroller.scrollTop;
                    if (direction === "top") {
                        scroller.scrollTop = 0;
                    } else {
                        scroller.scrollTop += Math.max(320, scroller.clientHeight * 0.8);
                    }
                    scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
                    const after = scroller.scrollTop;
                    return {
                        moved: Math.abs(after - before) > 2,
                        at_bottom: after + scroller.clientHeight >= scroller.scrollHeight - 8,
                    };
                }
                """,
                {
                    "selector": ChatLocators.chat_list_dom_selector,
                    "direction": direction,
                },
            )
            self._page.wait_for_timeout(250)
            return (
                result
                if isinstance(result, dict)
                else {"moved": False, "at_bottom": True}
            )
        except PlaywrightError:
            return {"moved": False, "at_bottom": True}

    def _clear_chat_search(self) -> None:
        search = self._first_matching(ChatLocators.search_input)
        if search is None:
            return
        try:
            search.fill("")
            search.press("Escape")
        except PlaywrightError:
            logger.debug("Could not clear the chat search box.", exc_info=True)

    def _open_conversation(self, user_id: str) -> None:
        target = normalize_text(user_id)
        if not target:
            raise ValueError("user_id must not be empty.")

        friends = self.get_fnd_list()
        friend = self._match_friend(friends, target)
        if friend is None:
            friend = self._match_friend(self.get_fnd_list(refresh=True), target)
        if friend is None:
            raise UserNotFoundError(
                f"No friend found for user_id/username {user_id!r}."
            )

        username = str(friend["username"])
        conversation_id = str(friend["user_id"] or "")
        if conversation_id:
            try:
                self._open_conversation_url(conversation_id)
                return
            except (PlaywrightError, SelectorNotFoundError):
                logger.debug(
                    "Direct conversation navigation failed; falling back to sidebar.",
                    exc_info=True,
                )

        self._clear_chat_search()
        if self._click_matching_chat_row(username, conversation_id):
            self._wait_for_locator(
                ChatLocators.message_input, description="message composer"
            )
            return

        search = self._first_matching(ChatLocators.search_input)
        if search is not None:
            search.fill(username)
            assert self._page is not None
            self._page.wait_for_timeout(700)
            if self._click_matching_chat_row(username, conversation_id):
                self._wait_for_locator(
                    ChatLocators.message_input, description="message composer"
                )
                return

        self._capture_diagnostics("conversation-not-found")
        raise UserNotFoundError(f"No chat row found for username {username!r}.")

    def _match_friend(self, friends: list[dict], target: str) -> dict | None:
        normalized = target.casefold()
        return next(
            (
                friend
                for friend in friends
                if normalize_text(friend.get("user_id")).casefold() == normalized
                or normalize_text(friend.get("username")).casefold() == normalized
            ),
            None,
        )

    def _open_conversation_url(self, conversation_id: str) -> None:
        assert self._page is not None
        url = f"{self.config.base_url.rstrip('/')}/{quote(conversation_id, safe='-_')}"
        self._page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=self.config.navigation_timeout_ms,
        )
        self._wait_for_locator(
            ChatLocators.message_input, description="message composer"
        )

    def _click_matching_chat_row(self, username: str, conversation_id: str) -> bool:
        items = self._first_collection(ChatLocators.chat_list_item)
        if items is None:
            return False
        normalized_username = normalize_text(username).casefold()
        for index in range(items.count()):
            item = items.nth(index)
            title = self._text_from(item, ChatLocators.chat_item_username)
            if not title:
                title, _ = parse_chat_row_text(normalize_text(item.text_content()))
            labelledby = normalize_text(item.get_attribute("aria-labelledby"))
            id_match = conversation_id and f"title-{conversation_id}" in labelledby
            if id_match or normalize_text(title).casefold() == normalized_username:
                self._safe_click(item)
                return True
        return False

    # -- Message helpers -------------------------------------------------

    def _message_bubbles(self) -> Locator:
        assert self._page is not None
        return self._page.locator(ChatLocators.message_bubble)

    def _set_composer_text(self, composer: Locator, text: str) -> None:
        self._polite_delay()
        composer.click()
        try:
            composer.fill(text)
        except PlaywrightError:
            composer.press("ControlOrMeta+A")
            composer.press("Backspace")
            composer.type(text)

        if normalize_text(self._composer_value(composer)) != normalize_text(text):
            self._capture_diagnostics("composer-fill-failed")
            raise SelectorNotFoundError("Could not populate the message composer.")

    def _composer_value(self, composer: Locator) -> str:
        try:
            return str(
                composer.evaluate(
                    "el => ('value' in el && typeof el.value === 'string') "
                    "? el.value : (el.textContent || '')"
                )
            )
        except PlaywrightError:
            try:
                return composer.input_value()
            except PlaywrightError:
                return composer.text_content() or ""

    def _confirm_message_sent(
        self,
        composer: Locator,
        *,
        bubbles_before: int,
        expected_text: str,
    ) -> bool:
        assert self._page is not None
        deadline = time.monotonic() + self.config.default_timeout_ms / 1000
        expected = normalize_text(expected_text)
        while time.monotonic() < deadline:
            self._raise_if_rate_limited()
            bubbles = self._message_bubbles()
            bubble_added = bubbles.count() > bubbles_before
            composer_cleared = not normalize_text(self._composer_value(composer))
            message_match = False
            for index in range(max(0, bubbles.count() - 6), bubbles.count()):
                parsed = self._parse_message_bubble(bubbles.nth(index))
                if parsed is None:
                    continue
                if normalize_text(parsed.get("text")) == expected and parsed.get(
                    "sender"
                ) in {"You", None}:
                    message_match = True
                    break
            if message_match or (composer_cleared and bubble_added):
                return True
            self._page.wait_for_timeout(250)
        return False

    def _parse_message_bubble(self, bubble: Locator) -> dict | None:
        sender = self._text_from(bubble, ChatLocators.message_bubble_sender)
        texts = self._all_texts_from(bubble, ChatLocators.message_bubble_text)
        timestamp_locator = self._first_matching(
            ChatLocators.message_bubble_timestamp, scope=bubble, visible=False
        )
        marker_text = self._text_from(bubble, ChatLocators.message_bubble_read_marker)
        has_media = bubble.locator(ChatLocators.message_media).count() > 0
        return parse_message_snapshot(
            raw_text=bubble.text_content(),
            sender=sender,
            text_candidates=texts,
            timestamp=self._timestamp_from(timestamp_locator),
            marker_text=marker_text,
            has_media=has_media,
        )

    # -- Locator/action helpers -----------------------------------------

    def _selector_candidates(self, selectors: SelectorSpec) -> tuple[str, ...]:
        if isinstance(selectors, str):
            return (selectors,)
        return tuple(selectors)

    def _first_matching(
        self,
        selectors: SelectorSpec,
        *,
        scope: Page | Locator | None = None,
        visible: bool = True,
    ) -> Locator | None:
        assert self._page is not None
        owner = scope or self._page
        for selector in self._selector_candidates(selectors):
            try:
                matches = owner.locator(selector)
                if matches.count() == 0:
                    continue
                first = matches.first
                if not visible or first.is_visible():
                    return first
            except PlaywrightError:
                continue
        return None

    def _first_collection(self, selectors: SelectorSpec) -> Locator | None:
        assert self._page is not None
        for selector in self._selector_candidates(selectors):
            try:
                matches = self._page.locator(selector)
                if matches.count() > 0:
                    return matches
            except PlaywrightError:
                continue
        return None

    def _wait_for_locator(
        self,
        selectors: SelectorSpec,
        *,
        description: str,
        timeout_ms: int | None = None,
    ) -> Locator:
        assert self._page is not None
        timeout = timeout_ms or self.config.default_timeout_ms
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            self._raise_if_rate_limited()
            match = self._first_matching(selectors)
            if match is not None:
                return match
            self._page.wait_for_timeout(200)
        artifacts = self._capture_diagnostics(f"selector-not-found-{description}")
        suffix = f" Diagnostics: {artifacts}" if artifacts else ""
        raise SelectorNotFoundError(f"Could not locate {description}.{suffix}")

    def _wait_for_any(
        self,
        candidates: list[tuple[SelectorSpec, str]],
        *,
        timeout_ms: int,
    ) -> tuple[str, Locator] | None:
        assert self._page is not None
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            self._raise_if_rate_limited()
            for selectors, tag in candidates:
                locator = self._first_matching(selectors)
                if locator is not None:
                    return tag, locator
            self._page.wait_for_timeout(200)
        return None

    def _click_if_present(self, selectors: SelectorSpec) -> None:
        control = self._first_matching(selectors)
        if control is not None:
            self._safe_click(control)

    def _safe_click(self, locator: Locator) -> None:
        self._raise_if_rate_limited()
        self._polite_delay()
        locator.click()
        self._last_action_at = time.monotonic()

    def _polite_delay(self) -> None:
        assert self._page is not None
        delay = random.uniform(
            self.config.action_delay_min_seconds,
            self.config.action_delay_max_seconds,
        )
        since_last = time.monotonic() - self._last_action_at
        remaining = max(0.0, delay - since_last)
        if remaining:
            self._page.wait_for_timeout(round(remaining * 1000))

    def _text_from(self, scope: Locator, selectors: SelectorSpec) -> str | None:
        locator = self._first_matching(selectors, scope=scope, visible=False)
        if locator is None:
            return None
        text = normalize_text(locator.text_content())
        return text or None

    def _all_texts_from(self, scope: Locator, selectors: SelectorSpec) -> list[str]:
        for selector in self._selector_candidates(selectors):
            try:
                matches = scope.locator(selector)
                values = [
                    normalize_text(matches.nth(index).text_content())
                    for index in range(matches.count())
                ]
                values = [value for value in values if value]
                if values:
                    return values
            except PlaywrightError:
                continue
        return []

    def _timestamp_from(self, locator: Locator | None) -> str | None:
        if locator is None:
            return None
        for attribute in ("datetime", "title"):
            value = normalize_text(locator.get_attribute(attribute))
            if value:
                return value
        value = normalize_text(locator.text_content())
        return value or None

    def _friend_at_index(self, friends: list[dict], index: int) -> dict:
        try:
            return friends[index]
        except IndexError as exc:
            raise UserNotFoundError(
                f"No friend at index {index} (list has {len(friends)})."
            ) from exc

    # -- Reliability/diagnostics ----------------------------------------

    def _run_with_retries(
        self,
        operation: str,
        action: Callable[[], T],
    ) -> T:
        last_error: PlaywrightError | None = None
        for attempt in range(1, self.config.action_retries + 1):
            try:
                self._raise_if_rate_limited()
                return action()
            except (PlaywrightTimeoutError, PlaywrightError) as exc:
                last_error = exc
                if attempt >= self.config.action_retries:
                    break
                delay = self.config.retry_base_delay_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "%s failed on attempt %s/%s; retrying in %.2fs.",
                    operation,
                    attempt,
                    self.config.action_retries,
                    delay,
                )
                if self._page is not None:
                    self._page.wait_for_timeout(round(delay * 1000))
                else:
                    time.sleep(delay)

        artifacts = self._capture_diagnostics(operation, last_error)
        logger.error("%s failed; diagnostics=%s", operation, artifacts or "disabled")
        assert last_error is not None
        raise last_error

    def _on_response(self, response: Response) -> None:
        if response.status != 429:
            return
        self._rate_limited_at = time.monotonic()
        self._rate_limited_url = self._safe_url(response.url)

    def _raise_if_rate_limited(self) -> None:
        if self._rate_limited_at is not None:
            elapsed = time.monotonic() - self._rate_limited_at
            if elapsed < self.config.rate_limit_cooldown_seconds:
                remaining = max(
                    1, round(self.config.rate_limit_cooldown_seconds - elapsed)
                )
                raise RateLimitedError(
                    f"Snapchat returned HTTP 429 for {self._rate_limited_url or 'a request'}; "
                    f"wait at least {remaining}s before retrying."
                )
            self._rate_limited_at = None
            self._rate_limited_url = ""

        if self._page is None or self._page.is_closed():
            return
        now = time.monotonic()
        if now - self._last_rate_limit_text_check_at < 1.0:
            return
        self._last_rate_limit_text_check_at = now
        try:
            body_text = self._page.locator("body").inner_text(timeout=100)
        except PlaywrightError:
            return
        if _RATE_LIMIT_TEXT.search(body_text):
            raise RateLimitedError(
                "Snapchat is displaying a throttling/block message; stop and retry later."
            )

    def _capture_diagnostics(
        self, operation: str, error: BaseException | None = None
    ) -> dict[str, str]:
        if (
            not self.config.capture_failure_artifacts
            or self._page is None
            or self._page.is_closed()
        ):
            return {}

        self._artifact_counter += 1
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", operation).strip("-")[:60]
        stem = f"{timestamp}-{self._artifact_counter:02d}-{slug or 'failure'}"
        directory = self.config.artifacts_path
        directory.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(directory, 0o700)
        except OSError:
            pass

        paths: dict[str, str] = {}
        screenshot_path = directory / f"{stem}.png"
        html_path = directory / f"{stem}.html"
        metadata_path = directory / f"{stem}.json"
        try:
            self._page.screenshot(path=str(screenshot_path), full_page=True)
            paths["screenshot"] = str(screenshot_path)
        except PlaywrightError:
            pass
        try:
            html_path.write_text(self._page.content(), encoding="utf-8")
            paths["html"] = str(html_path)
        except (OSError, PlaywrightError):
            pass

        metadata = {
            "operation": operation,
            "captured_at": datetime.now(UTC).isoformat(),
            "url": self._safe_url(self._page.url),
            "error_type": type(error).__name__ if error else None,
            "error": normalize_text(error)[:500] if error else None,
        }
        try:
            metadata_path.write_text(
                json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
            )
            paths["metadata"] = str(metadata_path)
        except OSError:
            pass

        for path in (screenshot_path, html_path, metadata_path):
            if not path.exists():
                continue
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        return paths

    def _safe_url(self, url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
