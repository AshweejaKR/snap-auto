from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = "https://www.snapchat.com/web"


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false, got {value!r}.")


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.environ.get(name)
    value = default if raw is None else int(raw)
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.environ.get(name)
    value = default if raw is None else float(raw)
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


@dataclass(frozen=True)
class Config:
    username: str = ""
    password: str = ""
    headless: bool = True
    base_url: str = DEFAULT_BASE_URL
    storage_state_path: Path = Path(".auth/storage_state.json")
    artifacts_path: Path = Path(".snap-auto-artifacts")
    capture_failure_artifacts: bool = True
    default_timeout_ms: int = 15_000
    navigation_timeout_ms: int = 45_000
    action_retries: int = 3
    retry_base_delay_seconds: float = 0.5
    action_delay_min_seconds: float = 0.15
    action_delay_max_seconds: float = 0.45
    rate_limit_cooldown_seconds: int = 60
    max_chat_scrolls: int = 40

    def __post_init__(self) -> None:
        if not self.base_url.startswith("https://"):
            raise ValueError("base_url must be an https:// URL.")
        if self.default_timeout_ms <= 0 or self.navigation_timeout_ms <= 0:
            raise ValueError("Timeouts must be greater than zero.")
        if self.action_retries < 1:
            raise ValueError("action_retries must be at least 1.")
        if self.action_delay_max_seconds < self.action_delay_min_seconds:
            raise ValueError(
                "action_delay_max_seconds must be greater than or equal to "
                "action_delay_min_seconds."
            )

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            username=os.environ.get("SNAP_USERNAME", "").strip(),
            password=os.environ.get("SNAP_PASSWORD", ""),
            headless=_env_bool("SNAP_HEADLESS", True),
            base_url=os.environ.get("SNAP_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            storage_state_path=Path(
                os.environ.get("SNAP_STORAGE_STATE_PATH", ".auth/storage_state.json")
            ),
            artifacts_path=Path(
                os.environ.get("SNAP_ARTIFACTS_PATH", ".snap-auto-artifacts")
            ),
            capture_failure_artifacts=_env_bool("SNAP_CAPTURE_FAILURE_ARTIFACTS", True),
            default_timeout_ms=_env_int("SNAP_DEFAULT_TIMEOUT_MS", 15_000, minimum=1),
            navigation_timeout_ms=_env_int(
                "SNAP_NAVIGATION_TIMEOUT_MS", 45_000, minimum=1
            ),
            action_retries=_env_int("SNAP_ACTION_RETRIES", 3, minimum=1),
            retry_base_delay_seconds=_env_float("SNAP_RETRY_BASE_DELAY_SECONDS", 0.5),
            action_delay_min_seconds=_env_float("SNAP_ACTION_DELAY_MIN_SECONDS", 0.15),
            action_delay_max_seconds=_env_float("SNAP_ACTION_DELAY_MAX_SECONDS", 0.45),
            rate_limit_cooldown_seconds=_env_int(
                "SNAP_RATE_LIMIT_COOLDOWN_SECONDS", 60
            ),
            max_chat_scrolls=_env_int("SNAP_MAX_CHAT_SCROLLS", 40, minimum=1),
        )

    def resolve_credentials(
        self, username: str | None, password: str | None
    ) -> tuple[str, str]:
        resolved_username = (
            username if username is not None else self.username
        ).strip()
        resolved_password = password if password is not None else self.password
        if not resolved_username or not resolved_password:
            raise ValueError(
                "Snapchat credentials are required. Pass them to login() or set "
                "SNAP_USERNAME and SNAP_PASSWORD (see .env.example)."
            )
        return resolved_username, resolved_password
