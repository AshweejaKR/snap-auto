from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from playwright.sync_api import Error as PlaywrightError

from snap_auto.client import SnapAutoClient
from snap_auto.config import Config
from snap_auto.exceptions import RateLimitedError, UserNotFoundError


class MinimalPage:
    def __init__(self, url: str = "https://www.snapchat.com/web") -> None:
        self.url = url
        self.waits: list[int] = []

    def is_closed(self) -> bool:
        return False

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


class FakeCollection:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def count(self) -> int:
        return len(self.values)

    def nth(self, index: int) -> object:
        return self.values[index]


def make_client(**config_overrides: object) -> SnapAutoClient:
    defaults: dict[str, object] = {
        "capture_failure_artifacts": False,
        "retry_base_delay_seconds": 0.0,
        "action_delay_min_seconds": 0.0,
        "action_delay_max_seconds": 0.0,
    }
    defaults.update(config_overrides)
    return SnapAutoClient(Config(**defaults))


def test_client_can_be_constructed_without_credentials() -> None:
    client = make_client()
    assert client.config.username == ""
    assert client.config.password == ""


def test_login_requires_credentials_only_after_client_is_started() -> None:
    client = make_client()
    client._page = MinimalPage()  # type: ignore[assignment]
    with pytest.raises(ValueError, match="credentials are required"):
        client.login()


def test_friend_projection_is_cached_with_defensive_copies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client()
    calls = 0

    def sessions(refresh: bool = False) -> list[dict]:
        nonlocal calls
        calls += 1
        return [
            {
                "username": "Alice",
                "user_id": "conversation-1",
                "preview": None,
                "timestamp": None,
                "unread": None,
            }
        ]

    monkeypatch.setattr(client, "get_all_chat_session", sessions)
    first = client.get_fnd_list()
    first[0]["username"] = "mutated"
    second = client.get_fnd_list()

    assert calls == 1
    assert second == [{"username": "Alice", "user_id": "conversation-1"}]


def test_chat_cache_returns_defensive_copy() -> None:
    client = make_client()
    client._chat_session_cache = [
        {
            "username": "Alice",
            "user_id": "c1",
            "preview": "Received",
            "timestamp": None,
            "unread": None,
        }
    ]
    first = client.get_all_chat_session()
    first[0]["preview"] = "changed"
    assert client.get_all_chat_session()[0]["preview"] == "Received"


def test_get_user_id_supports_case_insensitive_name_and_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client()
    friends = [
        {"username": "Alice Example", "user_id": "c1"},
        {"username": "legacy", "user_id": None},
    ]
    monkeypatch.setattr(client, "get_fnd_list", lambda refresh=False: friends)

    assert client.get_user_id(name="alice example") == "c1"
    assert client.get_user_id(index=1) == "legacy"
    assert client.get_username(0) == "Alice Example"


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"name": "Alice", "index": 0}],
)
def test_get_user_id_requires_exactly_one_lookup(kwargs: dict) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        make_client().get_user_id(**kwargs)


def test_missing_friend_and_bad_index_raise_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client()
    monkeypatch.setattr(client, "get_fnd_list", lambda refresh=False: [])
    with pytest.raises(UserNotFoundError, match="No friend found"):
        client.get_user_id(name="missing")
    with pytest.raises(UserNotFoundError, match="No friend at index"):
        client.get_username(0)


def test_virtualized_chat_scan_deduplicates_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(max_chat_scrolls=5)
    client._page = MinimalPage()  # type: ignore[assignment]
    alice = {"username": "Alice", "user_id": "c1"}
    bob = {"username": "Bob", "user_id": "c2"}
    carol = {"username": "Carol", "user_id": "c3"}
    snapshots = iter([[alice, bob], [bob, carol], [carol]])
    down_calls = 0

    monkeypatch.setattr(client, "_clear_chat_search", lambda: None)
    monkeypatch.setattr(client, "_click_if_present", lambda _selectors: None)
    monkeypatch.setattr(client, "_snapshot_visible_chats", lambda: next(snapshots, []))

    def scroll(direction: str) -> dict[str, bool]:
        nonlocal down_calls
        if direction == "top":
            return {"moved": True, "at_bottom": False}
        down_calls += 1
        return {"moved": True, "at_bottom": down_calls >= 3}

    monkeypatch.setattr(client, "_scroll_chat_list", scroll)
    sessions = client._collect_chat_sessions()
    assert [session["user_id"] for session in sessions] == ["c1", "c2", "c3"]


def test_idempotent_action_retries_then_succeeds() -> None:
    client = make_client(action_retries=3)
    attempts = 0

    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PlaywrightError("transient")
        return "ok"

    assert client._run_with_retries("flaky", flaky) == "ok"
    assert attempts == 3


def test_retry_exhaustion_raises_last_error() -> None:
    client = make_client(action_retries=2)
    attempts = 0

    def always_fails() -> None:
        nonlocal attempts
        attempts += 1
        raise PlaywrightError(f"failure-{attempts}")

    with pytest.raises(PlaywrightError, match="failure-2"):
        client._run_with_retries("always-fails", always_fails)
    assert attempts == 2


def test_http_429_is_reported_without_query_string() -> None:
    client = make_client(rate_limit_cooldown_seconds=60)
    response = SimpleNamespace(
        status=429,
        url="https://www.snapchat.com/api/messages?token=private",
    )
    client._on_response(response)  # type: ignore[arg-type]

    with pytest.raises(RateLimitedError, match="/api/messages") as error:
        client._raise_if_rate_limited()
    assert "token=private" not in str(error.value)


def test_expired_rate_limit_window_is_cleared() -> None:
    client = make_client(rate_limit_cooldown_seconds=1)
    client._rate_limited_at = time.monotonic() - 2
    client._rate_limited_url = "https://www.snapchat.com/api"
    client._raise_if_rate_limited()
    assert client._rate_limited_at is None


def test_send_message_submits_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client()
    client._page = MinimalPage()  # type: ignore[assignment]
    composer = object()
    send_button = object()
    clicks: list[object] = []
    filled: list[str] = []
    confirmation: list[tuple[int, str]] = []

    monkeypatch.setattr(client, "_ensure_authenticated", lambda: None)
    monkeypatch.setattr(client, "_raise_if_rate_limited", lambda: None)
    monkeypatch.setattr(client, "_open_conversation", lambda _user_id: None)
    monkeypatch.setattr(client, "_wait_for_locator", lambda *args, **kwargs: composer)
    monkeypatch.setattr(client, "_message_bubbles", lambda: FakeCollection([1, 2]))
    monkeypatch.setattr(
        client, "_set_composer_text", lambda _c, text: filled.append(text)
    )
    monkeypatch.setattr(client, "_first_matching", lambda *args, **kwargs: send_button)
    monkeypatch.setattr(client, "_safe_click", lambda control: clicks.append(control))

    def confirm(_composer: object, *, bubbles_before: int, expected_text: str) -> bool:
        confirmation.append((bubbles_before, expected_text))
        return True

    monkeypatch.setattr(client, "_confirm_message_sent", confirm)

    assert client.send_msg("c1", "hello") is True
    assert filled == ["hello"]
    assert clicks == [send_button]
    assert confirmation == [(2, "hello")]


def test_send_message_uses_enter_when_button_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client()
    client._page = MinimalPage()  # type: ignore[assignment]
    presses: list[str] = []
    composer = SimpleNamespace(press=lambda key: presses.append(key))

    monkeypatch.setattr(client, "_ensure_authenticated", lambda: None)
    monkeypatch.setattr(client, "_raise_if_rate_limited", lambda: None)
    monkeypatch.setattr(client, "_open_conversation", lambda _user_id: None)
    monkeypatch.setattr(client, "_wait_for_locator", lambda *args, **kwargs: composer)
    monkeypatch.setattr(client, "_message_bubbles", lambda: FakeCollection([]))
    monkeypatch.setattr(client, "_set_composer_text", lambda *_args: None)
    monkeypatch.setattr(client, "_first_matching", lambda *args, **kwargs: None)
    monkeypatch.setattr(client, "_polite_delay", lambda: None)
    monkeypatch.setattr(client, "_confirm_message_sent", lambda *args, **kwargs: True)

    assert client.send_msg("c1", "hello") is True
    assert presses == ["Enter"]


def test_empty_message_is_rejected_before_browser_action() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        make_client().send_msg("c1", "   ")


def test_read_message_filters_non_message_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client()
    client._page = MinimalPage()  # type: ignore[assignment]
    bubble_one = object()
    bubble_two = object()
    expected = {"sender": "Alice", "text": "hello", "timestamp": None, "read": None}

    monkeypatch.setattr(client, "_ensure_authenticated", lambda: None)
    monkeypatch.setattr(client, "_open_conversation", lambda _user_id: None)
    monkeypatch.setattr(
        client, "_message_bubbles", lambda: FakeCollection([bubble_one, bubble_two])
    )
    monkeypatch.setattr(
        client,
        "_parse_message_bubble",
        lambda bubble: expected if bubble is bubble_one else None,
    )

    assert client.read_msg("c1") == [expected]


class DiagnosticPage(MinimalPage):
    def screenshot(self, *, path: str, full_page: bool) -> None:
        assert full_page is True
        Path(path).write_bytes(b"png")

    def content(self) -> str:
        return "<html><body>fixture</body></html>"


def test_failure_diagnostics_are_private_and_sanitize_url(tmp_path: Path) -> None:
    client = make_client(
        capture_failure_artifacts=True,
        artifacts_path=tmp_path / "artifacts",
    )
    client._page = DiagnosticPage("https://www.snapchat.com/web/c1?secret=query-value")  # type: ignore[assignment]

    paths = client._capture_diagnostics("selector failure", ValueError("boom"))
    assert set(paths) == {"screenshot", "html", "metadata"}
    metadata = json.loads(Path(paths["metadata"]).read_text(encoding="utf-8"))
    assert metadata["url"] == "https://www.snapchat.com/web/c1"
    assert "query-value" not in json.dumps(metadata)
    assert Path(paths["html"]).read_text(encoding="utf-8").startswith("<html>")


class StorageContext:
    def __init__(self) -> None:
        self.indexed_db: bool | None = None
        self.cleared = False

    def storage_state(self, *, path: str, indexed_db: bool) -> None:
        self.indexed_db = indexed_db
        Path(path).write_text("{}", encoding="utf-8")

    def clear_cookies(self) -> None:
        self.cleared = True


class StoragePage(MinimalPage):
    def __init__(self) -> None:
        super().__init__()
        self.storage_cleared = False

    def evaluate(self, _expression: str) -> None:
        self.storage_cleared = True


def test_storage_state_includes_indexed_db(tmp_path: Path) -> None:
    state_path = tmp_path / "auth" / "state.json"
    client = make_client(storage_state_path=state_path)
    context = StorageContext()
    client._context = context  # type: ignore[assignment]
    client._save_storage_state()
    assert context.indexed_db is True
    assert state_path.read_text(encoding="utf-8") == "{}"


def test_clear_local_session_removes_state_and_caches(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text("{}", encoding="utf-8")
    client = make_client(storage_state_path=state_path)
    context = StorageContext()
    page = StoragePage()
    client._context = context  # type: ignore[assignment]
    client._page = page  # type: ignore[assignment]
    client._authenticated = True
    client._fnd_list_cache = [{"username": "Alice"}]
    client._chat_session_cache = [{"username": "Alice"}]

    client._clear_local_session()
    assert context.cleared is True
    assert page.storage_cleared is True
    assert not state_path.exists()
    assert client._authenticated is False
    assert client._fnd_list_cache is None
    assert client._chat_session_cache is None
