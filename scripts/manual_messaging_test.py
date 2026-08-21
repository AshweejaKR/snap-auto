"""Send one explicitly configured test message and read the visible thread.

This script has a real side effect. It exits unless every safety flag/value below
is present in ``.env`` or the process environment:

    SNAP_RUN_LIVE_SEND_TEST=1
    SNAP_LIVE_RECIPIENT=<exact Snapchat username>
    SNAP_LIVE_MESSAGE=<test message>

Run headed against a dedicated test account:

    SNAP_HEADLESS=false uv run python scripts/manual_messaging_test.py
"""

from __future__ import annotations

import os

from snap_auto import SnapAutoClient


def main() -> None:
    if os.environ.get("SNAP_RUN_LIVE_SEND_TEST") != "1":
        raise SystemExit("Refusing to send: set SNAP_RUN_LIVE_SEND_TEST=1 explicitly.")

    recipient = os.environ.get("SNAP_LIVE_RECIPIENT", "").strip()
    message = os.environ.get("SNAP_LIVE_MESSAGE", "").strip()
    if not recipient or not message:
        raise SystemExit("SNAP_LIVE_RECIPIENT and SNAP_LIVE_MESSAGE are required.")

    with SnapAutoClient() as client:
        client.login()
        user_id = client.get_user_id(name=recipient)
        confirmed = client.send_msg(user_id, message)
        print("send confirmed:", confirmed)
        print("visible messages:", client.read_msg(user_id))


if __name__ == "__main__":
    main()
