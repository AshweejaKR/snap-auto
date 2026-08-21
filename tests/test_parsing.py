from __future__ import annotations

import json
from pathlib import Path

import pytest

from snap_auto.parsing import (
    conversation_id_from,
    infer_message_read_state,
    infer_unread_state,
    normalize_text,
    parse_chat_row_text,
    parse_message_snapshot,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dom_snapshots.json"


@pytest.fixture(scope="module")
def dom_snapshots() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_normalize_text_collapses_whitespace() -> None:
    assert normalize_text("  Alice\n\tExample  ") == "Alice Example"
    assert normalize_text(None) == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("alice , New Snap", ("alice", "New Snap")),
        ("alice,Received", ("alice", "Received")),
        ("alice", ("alice", "")),
    ],
)
def test_parse_chat_row_text(raw: str, expected: tuple[str, str]) -> None:
    assert parse_chat_row_text(raw) == expected


def test_chat_snapshot_fixture(dom_snapshots: dict) -> None:
    for row in dom_snapshots["chat_rows"]:
        parsed_id = conversation_id_from(
            aria_labelledby=row["aria_labelledby"],
            title_element_id=row["title_element_id"],
            href=row["href"],
        )
        unread = infer_unread_state(
            aria_label=row["aria_label"],
            class_name=row["class_name"],
            status=row["status"],
        )
        assert parsed_id == row["expected_id"]
        assert unread == row["expected_unread"]


def test_conversation_id_falls_back_to_href() -> None:
    assert (
        conversation_id_from(href="https://www.snapchat.com/web/chat%2D123")
        == "chat-123"
    )
    assert conversation_id_from(href="/discover") is None


@pytest.mark.parametrize(
    ("marker", "expected"),
    [("Seen", True), ("Opened 1m", True), ("Delivered", False), ("", None)],
)
def test_infer_message_read_state(marker: str, expected: bool | None) -> None:
    assert infer_message_read_state(marker) is expected


def test_message_snapshot_fixture(dom_snapshots: dict) -> None:
    for message in dom_snapshots["messages"]:
        actual = parse_message_snapshot(
            raw_text=message["raw_text"],
            sender=message["sender"],
            text_candidates=message["text_candidates"],
            timestamp=message["timestamp"],
            marker_text=message["marker_text"],
            has_media=message["has_media"],
        )
        assert actual == message["expected"]


def test_media_only_message_gets_stable_placeholder() -> None:
    assert parse_message_snapshot(
        raw_text="",
        sender="Alice",
        text_candidates=[],
        timestamp=None,
        marker_text=None,
        has_media=True,
    ) == {"sender": "Alice", "text": "[Media]", "timestamp": None, "read": None}


def test_control_only_message_is_ignored() -> None:
    assert (
        parse_message_snapshot(
            raw_text="Close Chat",
            sender=None,
            text_candidates=[],
            timestamp=None,
            marker_text=None,
            has_media=False,
        )
        is None
    )
