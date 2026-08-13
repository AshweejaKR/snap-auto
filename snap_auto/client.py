"""SnapAutoClient: Playwright-backed automation client for web.snapchat.com."""

from __future__ import annotations

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from snap_auto.config import Config

BASE_URL = "https://web.snapchat.com"


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

    def login(self, username: str, password: str) -> bool:
        raise NotImplementedError

    def logout(self) -> None:
        raise NotImplementedError

    def verify_login(self) -> bool:
        raise NotImplementedError

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
