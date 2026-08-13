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
from snap_auto.exceptions import LoginFailedError
from snap_auto.locators import LoginLocators

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
        raise NotImplementedError

    def get_all_chat_session(self, refresh: bool = False) -> list[dict]:
        raise NotImplementedError

    def get_user_id(self, name: str | None = None, index: int | None = None) -> str:
        raise NotImplementedError

    def get_username(self, index: int) -> str:
        raise NotImplementedError

    # -- Messaging (Phase 3) -----------------------------------------------

    def send_msg(self, user_id: str, msg_txt: str) -> bool:
        raise NotImplementedError

    def read_msg(self, user_id: str) -> list[dict]:
        raise NotImplementedError

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
