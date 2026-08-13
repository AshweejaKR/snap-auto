from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    username: str
    password: str
    headless: bool = True
    storage_state_path: Path = Path(".auth/storage_state.json")

    @classmethod
    def from_env(cls) -> "Config":
        username = os.environ.get("SNAP_USERNAME")
        password = os.environ.get("SNAP_PASSWORD")
        if not username or not password:
            raise ValueError(
                "SNAP_USERNAME and SNAP_PASSWORD must be set (see .env.example)."
            )
        headless = os.environ.get("SNAP_HEADLESS", "true").strip().lower() != "false"
        storage_state_path = Path(
            os.environ.get("SNAP_STORAGE_STATE_PATH", ".auth/storage_state.json")
        )
        return cls(
            username=username,
            password=password,
            headless=headless,
            storage_state_path=storage_state_path,
        )
