"""Interactive helper for filling in FriendsLocators/ChatLocators (Phase 2).

Logs in, then opens the Playwright Inspector attached to the live,
authenticated page so you can use its "Pick locator" tool to find real
selectors for the friends list and chat list. Run headed:

    set SNAP_HEADLESS=false
    python scripts/inspect_dom.py

In the Inspector window: click "Pick locator", then hover/click elements in
the browser window (friend list container, one friend row, the friend's name
text, the chat list container, one chat row, etc). Copy each suggested
selector into the matching field in snap_auto/locators.py, then close the
Inspector (resume) to let the script exit.

Tip: also check the Elements/Network tabs in the browser's own devtools
(F12) while paused — e.g. to see if a friend/chat row has a data-* attribute
holding an internal id (for friend_user_id_attribute /
chat_item_user_id_attribute), or a distinguishing dot/class for unread state.
"""

from __future__ import annotations

import logging

from snap_auto.client import SnapAutoClient

logging.basicConfig(level=logging.INFO)


def main() -> None:
    with SnapAutoClient() as client:
        client.login(client.config.username, client.config.password)
        print(
            "Logged in. Opening Playwright Inspector — use 'Pick locator' to find "
            "selectors, then resume/close it to end the script."
        )
        client._page.pause()  # type: ignore[union-attr]


if __name__ == "__main__":
    main()
