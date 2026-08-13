"""Manual smoke test for Phase 2 (friends/chat discovery) against a real account.

Requires SNAP_USERNAME / SNAP_PASSWORD (and optionally SNAP_HEADLESS=false) set in
.env, and reuses a saved session from scripts/manual_login_test.py if present. Run
with:

    uv run python scripts/manual_discovery_test.py

Note: chat_list_container/chat_list_item use a confirmed heuristic selector
(button:has-text(",")) and username/preview should scrape correctly, but
user_id/timestamp/unread are still TODO placeholders (see locators.py) and will
come back as None until those sub-elements are identified against the real DOM.
"""

from __future__ import annotations

import logging

from snap_auto.client import SnapAutoClient

logging.basicConfig(level=logging.INFO)


def main() -> None:
    with SnapAutoClient() as client:
        client.login(client.config.username, client.config.password)

        friends = client.get_fnd_list()
        print(f"Friends ({len(friends)}):", friends)

        sessions = client.get_all_chat_session()
        print(f"Chat sessions ({len(sessions)}):", sessions)

        if friends:
            print("get_username(0):", client.get_username(0))
            print("get_user_id(index=0):", client.get_user_id(index=0))
            print("get_user_id(name=...):", client.get_user_id(name=friends[0]["username"]))

        # Cache should short-circuit a second call; refresh=True forces a re-scrape.
        print("Cached fnd_list is same object:", client.get_fnd_list() is friends)
        client.get_fnd_list(refresh=True)


if __name__ == "__main__":
    main()
