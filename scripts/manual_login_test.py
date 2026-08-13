"""Manual smoke test for Phase 1 (login / verify_login / logout) against a real account.

Requires SNAP_USERNAME / SNAP_PASSWORD (and optionally SNAP_HEADLESS=false) set in
.env. Run with:

    uv run python scripts/manual_login_test.py
"""

from __future__ import annotations

import logging

from snap_auto.client import SnapAutoClient

logging.basicConfig(level=logging.INFO)


def main() -> None:
    with SnapAutoClient() as client:
        client.login(client.config.username, client.config.password)
        print("verify_login:", client.verify_login())

        client.logout()
        print("verify_login after logout:", client.verify_login())


if __name__ == "__main__":
    main()
