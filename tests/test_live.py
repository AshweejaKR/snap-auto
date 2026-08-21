"""Explicitly opt-in smoke tests for a dedicated Snapchat test account."""

from __future__ import annotations

import os

import pytest

from snap_auto import SnapAutoClient

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("SNAP_RUN_LIVE_TESTS") != "1",
        reason="set SNAP_RUN_LIVE_TESTS=1 to access a real Snapchat test account",
    ),
]


def test_live_login_and_discovery() -> None:
    with SnapAutoClient() as client:
        assert client.login()
        assert client.verify_login()
        assert isinstance(client.get_all_chat_session(refresh=True), list)
        assert isinstance(client.get_fnd_list(), list)


@pytest.mark.live_send
def test_live_send_and_read() -> None:
    if os.environ.get("SNAP_RUN_LIVE_SEND_TEST") != "1":
        pytest.skip("set SNAP_RUN_LIVE_SEND_TEST=1 to permit one test message")

    recipient = os.environ.get("SNAP_LIVE_RECIPIENT", "").strip()
    message = os.environ.get("SNAP_LIVE_MESSAGE", "").strip()
    if not recipient or not message:
        pytest.skip("SNAP_LIVE_RECIPIENT and SNAP_LIVE_MESSAGE are both required")

    with SnapAutoClient() as client:
        assert client.login()
        user_id = client.get_user_id(name=recipient)
        assert client.send_msg(user_id, message)
        assert any(item.get("text") == message for item in client.read_msg(user_id))
