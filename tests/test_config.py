from __future__ import annotations

from pathlib import Path

import pytest

from snap_auto.config import DEFAULT_BASE_URL, Config

ENV_NAMES = (
    "SNAP_USERNAME",
    "SNAP_PASSWORD",
    "SNAP_HEADLESS",
    "SNAP_BASE_URL",
    "SNAP_STORAGE_STATE_PATH",
    "SNAP_ARTIFACTS_PATH",
    "SNAP_CAPTURE_FAILURE_ARTIFACTS",
    "SNAP_DEFAULT_TIMEOUT_MS",
    "SNAP_NAVIGATION_TIMEOUT_MS",
    "SNAP_ACTION_RETRIES",
    "SNAP_RETRY_BASE_DELAY_SECONDS",
    "SNAP_ACTION_DELAY_MIN_SECONDS",
    "SNAP_ACTION_DELAY_MAX_SECONDS",
    "SNAP_RATE_LIMIT_COOLDOWN_SECONDS",
    "SNAP_MAX_CHAT_SCROLLS",
)


@pytest.fixture(autouse=True)
def clear_snap_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_from_env_has_safe_defaults_without_credentials() -> None:
    config = Config.from_env()
    assert config.username == ""
    assert config.password == ""
    assert config.headless is True
    assert config.base_url == DEFAULT_BASE_URL


def test_from_env_parses_all_reliability_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state_path = tmp_path / "state.json"
    artifacts_path = tmp_path / "artifacts"
    values = {
        "SNAP_USERNAME": " alice ",
        "SNAP_PASSWORD": "secret",
        "SNAP_HEADLESS": "no",
        "SNAP_BASE_URL": "https://web.snapchat.com/",
        "SNAP_STORAGE_STATE_PATH": str(state_path),
        "SNAP_ARTIFACTS_PATH": str(artifacts_path),
        "SNAP_CAPTURE_FAILURE_ARTIFACTS": "off",
        "SNAP_DEFAULT_TIMEOUT_MS": "1000",
        "SNAP_NAVIGATION_TIMEOUT_MS": "2000",
        "SNAP_ACTION_RETRIES": "2",
        "SNAP_RETRY_BASE_DELAY_SECONDS": "0.1",
        "SNAP_ACTION_DELAY_MIN_SECONDS": "0.2",
        "SNAP_ACTION_DELAY_MAX_SECONDS": "0.3",
        "SNAP_RATE_LIMIT_COOLDOWN_SECONDS": "12",
        "SNAP_MAX_CHAT_SCROLLS": "5",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    config = Config.from_env()
    assert config.username == "alice"
    assert config.password == "secret"
    assert config.headless is False
    assert config.base_url == "https://web.snapchat.com"
    assert config.storage_state_path == state_path
    assert config.artifacts_path == artifacts_path
    assert config.capture_failure_artifacts is False
    assert config.default_timeout_ms == 1000
    assert config.navigation_timeout_ms == 2000
    assert config.action_retries == 2
    assert config.retry_base_delay_seconds == 0.1
    assert config.action_delay_min_seconds == 0.2
    assert config.action_delay_max_seconds == 0.3
    assert config.rate_limit_cooldown_seconds == 12
    assert config.max_chat_scrolls == 5


def test_invalid_boolean_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNAP_HEADLESS", "sometimes")
    with pytest.raises(ValueError, match="SNAP_HEADLESS must be true or false"):
        Config.from_env()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_url": "http://example.com"},
        {"default_timeout_ms": 0},
        {"action_retries": 0},
        {"action_delay_min_seconds": 2, "action_delay_max_seconds": 1},
    ],
)
def test_invalid_config_is_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        Config(**kwargs)


def test_credentials_can_come_from_config_or_call() -> None:
    config = Config(username="config-user", password="config-pass")
    assert config.resolve_credentials(None, None) == ("config-user", "config-pass")
    assert config.resolve_credentials("direct-user", "direct-pass") == (
        "direct-user",
        "direct-pass",
    )


def test_missing_credentials_are_rejected_only_when_login_needs_them() -> None:
    with pytest.raises(ValueError, match="credentials are required"):
        Config().resolve_credentials(None, None)
