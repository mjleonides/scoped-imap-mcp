"""Environment-backed configuration and folder access controls."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FolderAccessError(PermissionError):
    """Raised when a request targets a folder outside the configured scope."""


class Settings(BaseSettings):
    """Settings for a single read-only IMAP account."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    imap_host: str
    imap_user: str
    imap_password: str
    imap_port: int | None = Field(default=None, gt=0, le=65535)
    imap_ssl: bool = True
    imap_starttls: bool = False
    imap_allow_insecure: bool = False
    imap_timeout_seconds: float = Field(default=30, gt=0)
    imap_allowed_folders: str
    max_body_chars: int = Field(default=50_000, gt=0)
    log_level: str = "INFO"

    @field_validator("imap_host", "imap_user", "imap_password")
    @classmethod
    def require_nonempty_connection_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("imap_allowed_folders")
    @classmethod
    def require_allowed_folders(cls, value: str) -> str:
        folders = value.split(",")
        if not value.strip() or any(not folder.strip() for folder in folders):
            raise ValueError("must be a comma-separated list without empty entries")

        normalized = [folder.strip() for folder in folders]
        if len(set(normalized)) != len(normalized):
            raise ValueError("must not contain duplicate folders")
        return ",".join(normalized)

    @model_validator(mode="after")
    def validate_transport_security(self) -> "Settings":
        if self.imap_ssl and self.imap_starttls:
            raise ValueError("IMAP_SSL and IMAP_STARTTLS cannot both be enabled")
        if not (self.imap_ssl or self.imap_starttls or self.imap_allow_insecure):
            raise ValueError(
                "plaintext IMAP requires IMAP_ALLOW_INSECURE=true"
            )
        return self

    @property
    def allowed_folders(self) -> tuple[str, ...]:
        """The canonical, explicitly permitted IMAP folder names."""
        return tuple(self.imap_allowed_folders.split(","))

    @property
    def single_folder_mode(self) -> bool:
        return len(self.allowed_folders) == 1

    @property
    def multi_folder_mode(self) -> bool:
        return not self.single_folder_mode

    @property
    def default_folder(self) -> str:
        """The only permitted folder in single-folder mode."""
        if not self.single_folder_mode:
            raise ValueError("a default folder is only defined in single-folder mode")
        return self.allowed_folders[0]

    @property
    def resolved_port(self) -> int:
        """Use conventional secure IMAP ports unless explicitly configured."""
        if self.imap_port is not None:
            return self.imap_port
        return 993 if self.imap_ssl else 143

    def validate_folder_access(self, target_folder: str) -> str:
        """Return a canonical folder or deny the request before IMAP is contacted."""
        requested_folder = target_folder.strip()
        if requested_folder in self.allowed_folders:
            return requested_folder
        raise FolderAccessError(
            f"Access to IMAP folder {target_folder!r} is not permitted"
        )


def load_settings(env_file: str | Path | None = None) -> Settings:
    """Load settings, optionally from the path named by ``IMAP_ENV_FILE``."""
    selected_env_file = env_file or os.environ.get("IMAP_ENV_FILE", ".env")
    return Settings(_env_file=selected_env_file)
