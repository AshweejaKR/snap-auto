"""Pure parsing helpers for snapshots extracted from Snapchat Web's DOM.

Keeping these functions independent from Playwright makes the brittle part of the
client easy to unit-test against saved DOM snapshots.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

_WHITESPACE_RE = re.compile(r"\s+")
_TITLE_ID_RE = re.compile(r"(?:^|\s)title-([A-Za-z0-9_-]+)(?:\s|$)")
_DATE_DIVIDER_RE = re.compile(
    r"^(?:today|yesterday|sun(?:day)?|mon(?:day)?|tue(?:sday)?|"
    r"wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)(?:\s+\d{1,2})?(?:,?\s+\d{4})?$",
    re.IGNORECASE,
)
_UNREAD_RE = re.compile(r"\b(?:unread|new snap|new chat|new message)\b", re.IGNORECASE)
_READ_RE = re.compile(r"\b(?:seen|opened|read)\b", re.IGNORECASE)
_NOT_READ_RE = re.compile(r"\b(?:sent|delivered|pending)\b", re.IGNORECASE)


def normalize_text(value: object | None) -> str:
    """Collapse whitespace and coerce a DOM value to a clean string."""

    return _WHITESPACE_RE.sub(" ", str(value or "")).strip()


def parse_chat_row_text(text: str) -> tuple[str, str]:
    """Split the legacy accessible row text ``username , status``.

    Newer Snapchat Web builds expose dedicated ``title-*``/``status-*`` nodes,
    but this remains a useful fallback for the DOM shape already verified in the
    repository's Phase 2 live test.
    """

    normalized = normalize_text(text)
    username, separator, status = normalized.partition(" , ")
    if separator:
        return username.strip(), status.strip()

    # Some accessibility trees collapse spaces around the comma.
    username, separator, status = normalized.partition(",")
    if separator:
        return username.strip(), status.strip()
    return normalized, ""


def conversation_id_from(
    *,
    aria_labelledby: str | None = None,
    title_element_id: str | None = None,
    href: str | None = None,
) -> str | None:
    """Extract the stable conversation id exposed by Snapchat Web.

    Current chat rows label their title span ``title-<conversation-id>`` and
    conversation links use ``/web/<conversation-id>``. Either source is accepted
    so selector drift in one does not break id lookup.
    """

    for candidate in (title_element_id, aria_labelledby):
        match = _TITLE_ID_RE.search(normalize_text(candidate))
        if match:
            return match.group(1)

    if href:
        parts = [part for part in urlparse(href).path.split("/") if part]
        if len(parts) >= 2 and parts[-2].lower() == "web":
            return unquote(parts[-1]) or None
    return None


def infer_unread_state(
    *, aria_label: str | None, class_name: str | None, status: str | None
) -> bool | None:
    """Infer unread state only when the DOM provides useful evidence."""

    accessibility_evidence = normalize_text(f"{aria_label or ''} {class_name or ''}")
    normalized_status = normalize_text(status)
    if _UNREAD_RE.search(f"{accessibility_evidence} {normalized_status}"):
        return True
    if accessibility_evidence:
        return False
    return None


def infer_message_read_state(marker_text: str | None) -> bool | None:
    """Map delivery/read marker text to a tri-state value."""

    marker = normalize_text(marker_text)
    if not marker:
        return None
    if _READ_RE.search(marker):
        return True
    if _NOT_READ_RE.search(marker):
        return False
    return None


def parse_message_snapshot(
    *,
    raw_text: str | None,
    sender: str | None,
    text_candidates: list[str],
    timestamp: str | None,
    marker_text: str | None,
    has_media: bool,
) -> dict[str, object] | None:
    """Convert one rendered conversation ``li`` into the public message shape."""

    normalized_sender = normalize_text(sender)
    if normalized_sender.casefold() in {"me", "you"}:
        normalized_sender = "You"

    candidates = [normalize_text(value) for value in text_candidates]
    candidates = [value for value in candidates if value]
    text = candidates[-1] if candidates else ""

    normalized_raw = normalize_text(raw_text)
    normalized_timestamp = normalize_text(timestamp)
    if not text:
        text = normalized_raw
        for prefix in (normalized_sender, normalized_timestamp):
            if prefix and text.casefold().startswith(prefix.casefold()):
                text = text[len(prefix) :].strip()

    if not text and has_media:
        text = "[Media]"

    if not text:
        return None
    if not normalized_sender and _DATE_DIVIDER_RE.fullmatch(text):
        return None
    if text.casefold() in {"close chat", "reply", "drag & drop to upload"}:
        return None

    return {
        "sender": normalized_sender or None,
        "text": text,
        "timestamp": normalized_timestamp or None,
        "read": infer_message_read_state(marker_text),
    }
