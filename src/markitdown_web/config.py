from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

DEFAULT_MAX_FILES = 20
DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB per file
DEFAULT_MAX_TOTAL_BYTES = 200 * 1024 * 1024  # 200 MB per request
DEFAULT_MAX_MARKDOWN_CHARS = 2_000_000  # guard against zip/recursive bombs

_TRUE = ("1", "true", "yes", "on")


def _read_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{key} must be an integer, got {raw!r}")
    if value <= 0:
        raise ValueError(f"{key} must be greater than zero, got {value}")
    return value


def _read_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUE


@dataclass(frozen=True, kw_only=True)
class Settings:
    """Runtime limits for the web UI.

    Everything is overridable through environment variables so the defaults
    stay conservative without requiring a config file.
    """

    max_files: int = DEFAULT_MAX_FILES
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    max_markdown_chars: int = DEFAULT_MAX_MARKDOWN_CHARS
    enable_plugins: bool = False
    local_only: bool = True
    enable_api_docs: bool = True

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        return cls(
            max_files=_read_int(env, "MARKITDOWN_WEB_MAX_FILES", DEFAULT_MAX_FILES),
            max_file_bytes=_read_int(
                env, "MARKITDOWN_WEB_MAX_FILE_BYTES", DEFAULT_MAX_FILE_BYTES
            ),
            max_total_bytes=_read_int(
                env, "MARKITDOWN_WEB_MAX_TOTAL_BYTES", DEFAULT_MAX_TOTAL_BYTES
            ),
            max_markdown_chars=_read_int(
                env,
                "MARKITDOWN_WEB_MAX_MARKDOWN_CHARS",
                DEFAULT_MAX_MARKDOWN_CHARS,
            ),
            enable_plugins=_read_bool(env, "MARKITDOWN_WEB_ENABLE_PLUGINS", False),
            local_only=_read_bool(env, "MARKITDOWN_WEB_LOCAL_ONLY", True),
            enable_api_docs=_read_bool(env, "MARKITDOWN_WEB_API_DOCS", True),
        )
