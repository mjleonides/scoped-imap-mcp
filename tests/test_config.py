from pathlib import Path

import pytest
from pydantic import ValidationError

from scoped_imap_mcp.config import FolderAccessError, Settings, load_settings


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "imap_host": "mail.example.test",
        "imap_user": "user@example.test",
        "imap_password": "secret",
        "imap_allowed_folders": "Labels/Amazon",
    }
    values.update(overrides)
    return Settings(**values)


def test_single_folder_mode_normalizes_whitespace() -> None:
    config = settings(imap_allowed_folders="  Labels/Amazon  ")

    assert config.allowed_folders == ("Labels/Amazon",)
    assert config.single_folder_mode is True
    assert config.default_folder == "Labels/Amazon"


def test_multiple_folders_enable_multi_folder_mode() -> None:
    config = settings(imap_allowed_folders="Receipts, Labels/Amazon")

    assert config.allowed_folders == ("Receipts", "Labels/Amazon")
    assert config.multi_folder_mode is True
    with pytest.raises(ValueError, match="default folder"):
        _ = config.default_folder


@pytest.mark.parametrize("folders", ["", "Receipts,", "Receipts, ,Newsletters"])
def test_empty_folder_entries_are_rejected(folders: str) -> None:
    with pytest.raises(ValidationError, match="without empty entries"):
        settings(imap_allowed_folders=folders)


def test_duplicate_folders_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate folders"):
        settings(imap_allowed_folders="Receipts, Receipts")


def test_unlisted_inbox_is_rejected_before_imap_access() -> None:
    config = settings(imap_allowed_folders="Labels/Amazon")

    with pytest.raises(FolderAccessError, match="not permitted"):
        config.validate_folder_access("INBOX")


def test_folder_names_must_match_exactly() -> None:
    config = settings(imap_allowed_folders="Labels/Amazon")

    assert config.validate_folder_access(" Labels/Amazon ") == "Labels/Amazon"
    with pytest.raises(FolderAccessError):
        config.validate_folder_access("Labels/Amazon/Archive")


def test_plaintext_imap_requires_explicit_override() -> None:
    with pytest.raises(ValidationError, match="IMAP_ALLOW_INSECURE"):
        settings(imap_ssl=False, imap_starttls=False)

    config = settings(imap_ssl=False, imap_allow_insecure=True)
    assert config.resolved_port == 143


def test_ssl_and_starttls_are_mutually_exclusive() -> None:
    with pytest.raises(ValidationError, match="cannot both be enabled"):
        settings(imap_starttls=True)


def test_default_ports_follow_transport_mode() -> None:
    assert settings().resolved_port == 993
    assert settings(imap_ssl=False, imap_starttls=True).resolved_port == 143


def test_environment_overrides_selected_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / "imap.env"
    env_file.write_text(
        "\n".join(
            [
                "IMAP_HOST=from-file.example.test",
                "IMAP_USER=user@example.test",
                "IMAP_PASSWORD=secret",
                "IMAP_ALLOWED_FOLDERS=Receipts",
            ]
        )
    )
    monkeypatch.setenv("IMAP_HOST", "from-environment.example.test")

    config = load_settings(env_file)

    assert config.imap_host == "from-environment.example.test"
