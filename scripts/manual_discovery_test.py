"""Manual smoke test for Phase 2 (friends/chat discovery) against a real account.

Requires SNAP_USERNAME / SNAP_PASSWORD (and optionally SNAP_HEADLESS=false) set in
.env, and reuses a saved session from scripts/manual_login_test.py if present. Run
with:

    uv run python scripts/manual_discovery_test.py

The scan walks Snapchat Web's virtualized sidebar. ``user_id`` is the stable
conversation id when the DOM exposes ``title-<id>`` or ``/web/<id>``; legacy rows
fall back to the username.
"""

from __future__ import annotations

import logging

from snap_auto.client import SnapAutoClient

logging.basicConfig(level=logging.INFO)


def main() -> None:
    with SnapAutoClient() as client:
        client.login()

        friends = client.get_fnd_list()
        print(f"Friends ({len(friends)}):", friends)

        sessions = client.get_all_chat_session()
        print(f"Chat sessions ({len(sessions)}):", sessions)

        if friends:
            print("get_username(0):", client.get_username(0))
            print("get_user_id(index=0):", client.get_user_id(index=0))
            print(
                "get_user_id(name=...):",
                client.get_user_id(name=friends[0]["username"]),
            )

        # Cached calls return defensive copies; refresh=True forces a re-scrape.
        print("Cached fnd_list has same values:", client.get_fnd_list() == friends)
        client.get_fnd_list(refresh=True)


if __name__ == "__main__":
    main()
