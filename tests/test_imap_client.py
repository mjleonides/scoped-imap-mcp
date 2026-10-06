from datetime import date

import pytest

from scoped_imap_mcp.config import FolderAccessError, Settings
from scoped_imap_mcp.imap_client import (
    IMAPClientError,
    ScopedIMAPClient,
    build_search_criteria,
    extract_message_body,
)


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "imap_host": "mail.example.test",
        "imap_user": "user@example.test",
        "imap_password": "secret",
        "imap_allowed_folders": "Receipts",
        "mcp_bearer_token": "token",
    }
    values.update(overrides)
    return Settings(**values)


class FakeIMAP:
    def __init__(self) -> None:
        self.commands: list[tuple[object, ...]] = []
        self.login_response = ("OK", [b"Logged in"])
        self.select_response = ("OK", [b"1"])
        self.search_response = ("OK", [b"101 102"])
        self.fetch_response = (
            "OK",
            [
                (
                    b"101 (BODY[HEADER.FIELDS] {92}",
                    b"Subject: Receipt\r\nFrom: Shop <orders@example.test>\r\n"
                    b"Date: Thu, 01 Feb 2024 10:00:00 +0000\r\n"
                    b"Message-ID: <receipt@example.test>\r\n\r\n",
                ),
                b")",
            ],
        )

    def login(self, user: str, password: str) -> tuple[str, list[bytes]]:
        self.commands.append(("LOGIN", user, password))
        return self.login_response

    def starttls(self, *, ssl_context: object) -> tuple[str, list[bytes]]:
        self.commands.append(("STARTTLS", ssl_context))
        return "OK", [b"TLS active"]

    def select(self, folder: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        self.commands.append(("SELECT", folder, readonly))
        return self.select_response

    def uid(self, command: str, *args: object) -> tuple[str, list[object]]:
        self.commands.append(("UID", command, *args))
        if command == "SEARCH":
            return self.search_response
        if command == "FETCH":
            return self.fetch_response
        raise AssertionError(f"unexpected UID command: {command}")

    def logout(self) -> tuple[str, list[bytes]]:
        self.commands.append(("LOGOUT",))
        return "BYE", [b"Logged out"]


def install_ssl_connection(monkeypatch: pytest.MonkeyPatch, fake: FakeIMAP) -> list[object]:
    constructor_calls: list[object] = []

    def construct(*args: object, **kwargs: object) -> FakeIMAP:
        constructor_calls.append((args, kwargs))
        return fake

    monkeypatch.setattr("scoped_imap_mcp.imap_client.imaplib.IMAP4_SSL", construct)
    return constructor_calls


def test_search_uses_readonly_select_and_uid_search_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeIMAP()
    constructor_calls = install_ssl_connection(monkeypatch, fake)

    with ScopedIMAPClient(settings()) as client:
        uids = client.search(
            "Receipts",
            query="order 123",
            sender="orders@example.test",
            since_date=date(2024, 1, 1),
            before_date=date(2024, 2, 1),
        )

    assert uids == ("101", "102")
    assert constructor_calls[0][0] == ("mail.example.test", 993)
    assert fake.commands == [
        ("LOGIN", "user@example.test", "secret"),
        ("SELECT", "Receipts", True),
        (
            "UID",
            "SEARCH",
            None,
            "SINCE",
            "01-Jan-2024",
            "BEFORE",
            "01-Feb-2024",
            "FROM",
            '"orders@example.test"',
            "TEXT",
            '"order 123"',
        ),
        ("LOGOUT",),
    ]
    assert all(command[0] != "EXAMINE" for command in fake.commands)


def test_unlisted_folder_is_rejected_without_an_imap_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeIMAP()
    install_ssl_connection(monkeypatch, fake)

    with ScopedIMAPClient(settings()) as client:
        with pytest.raises(FolderAccessError):
            client.search("INBOX")

    assert fake.commands == [
        ("LOGIN", "user@example.test", "secret"),
        ("LOGOUT",),
    ]


def test_fetch_metadata_uses_body_peek_and_parses_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeIMAP()
    install_ssl_connection(monkeypatch, fake)

    with ScopedIMAPClient(settings()) as client:
        metadata = client.fetch_metadata("Receipts", ["101"])

    assert metadata[0].uid == "101"
    assert metadata[0].subject == "Receipt"
    assert metadata[0].sender == "Shop <orders@example.test>"
    assert metadata[0].message_id == "<receipt@example.test>"
    assert (
        "UID",
        "FETCH",
        "101",
        "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE MESSAGE-ID)])",
    ) in fake.commands


def test_starttls_is_upgraded_before_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeIMAP()
    constructor_calls: list[object] = []

    def construct(*args: object, **kwargs: object) -> FakeIMAP:
        constructor_calls.append((args, kwargs))
        return fake

    monkeypatch.setattr("scoped_imap_mcp.imap_client.imaplib.IMAP4", construct)

    with ScopedIMAPClient(settings(imap_ssl=False, imap_starttls=True)):
        pass

    assert constructor_calls[0][0] == ("mail.example.test", 143)
    assert [command[0] for command in fake.commands] == ["STARTTLS", "LOGIN", "LOGOUT"]


def test_criteria_quote_values_and_reject_control_characters() -> None:
    assert build_search_criteria(query='a "quoted" \\ value') == (
        "TEXT",
        '"a \\"quoted\\" \\\\ value"',
    )
    with pytest.raises(ValueError, match="control characters"):
        build_search_criteria(query="safe\r\nALL")


def test_non_ok_responses_raise_sanitized_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeIMAP()
    fake.search_response = ("NO", [b"sensitive server response"])
    install_ssl_connection(monkeypatch, fake)

    with ScopedIMAPClient(settings()) as client:
        with pytest.raises(IMAPClientError, match="Unable to search") as error:
            client.search("Receipts")

    assert "sensitive" not in str(error.value)


def test_invalid_uid_is_rejected_before_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeIMAP()
    install_ssl_connection(monkeypatch, fake)

    with ScopedIMAPClient(settings()) as client:
        with pytest.raises(ValueError, match="UID"):
            client.fetch_metadata("Receipts", ["101 SEARCH ALL"])

    assert not any(command[:2] == ("UID", "FETCH") for command in fake.commands)


def test_extract_message_body_prefers_plain_text_and_ignores_attachments() -> None:
    message = b"""MIME-Version: 1.0\r
Content-Type: multipart/mixed; boundary=outer\r
\r
--outer\r
Content-Type: multipart/alternative; boundary=inner\r
\r
--inner\r
Content-Type: text/plain; charset=utf-8\r
\r
Plain body\r
--inner\r
Content-Type: text/html; charset=utf-8\r
\r
<p>HTML body</p>\r
--inner--\r
--outer\r
Content-Type: text/plain; charset=utf-8\r
Content-Disposition: attachment; filename=secret.txt\r
\r
Do not expose\r
--outer--\r
"""

    assert extract_message_body(message, 50_000) == "Plain body"


def test_extract_message_body_converts_html_and_truncates() -> None:
    message = b"""Content-Type: text/html; charset=utf-8\r
\r
<h1>Receipt</h1><p>Order <strong>123</strong></p>"""

    body = extract_message_body(message, 12)

    assert body == "# Receipt\n\nO"


def test_fetch_body_uses_body_peek_and_applies_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeIMAP()
    fake.fetch_response = (
        "OK",
        [(b"101 (BODY[] {24}", b"Content-Type: text/plain\r\n\r\nThis is a body"), b")"],
    )
    install_ssl_connection(monkeypatch, fake)

    with ScopedIMAPClient(settings(max_body_chars=4)) as client:
        message = client.fetch_body("Receipts", "101")

    assert message.uid == "101"
    assert message.body == "This"
    assert ("UID", "FETCH", "101", "(BODY.PEEK[])") in fake.commands
