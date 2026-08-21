"""Open Playwright Inspector to diagnose Snapchat Web selector drift.

Run headed with credentials configured in ``.env``:

    SNAP_HEADLESS=false uv run python scripts/inspect_dom.py

In the Inspector, use "Pick locator" on the failing chat-list or message-thread
element. Prefer semantic roles, aria attributes, element ids, or test ids, then add
the new selector as an ordered fallback in ``snap_auto/locators.py``.

Failure screenshots/HTML are written to ``.snap-auto-artifacts/`` by default.
Those files can contain private chat content and must never be committed.
"""

from __future__ import annotations

import logging

from snap_auto import SnapAutoClient

logging.basicConfig(level=logging.INFO)


def main() -> None:
    with SnapAutoClient() as client:
        client.login()
        print(
            "Logged in. Opening Playwright Inspector — use 'Pick locator', then "
            "resume/close it to end the script."
        )
        assert client._page is not None
        client._page.pause()


if __name__ == "__main__":
    main()
