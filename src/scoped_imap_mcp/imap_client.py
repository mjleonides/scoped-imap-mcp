"""Read-only, folder-scoped IMAP access.

This module deliberately exposes a small subset of IMAP: selecting an allowed
folder read-only, searching by UID, and fetching message headers without
setting the ``\\Seen`` flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from email import policy
from email.message import Message
from email.parser import BytesParser
import imaplib
import ssl
from types import TracebackType
from typing import Literal

import html2text

from .config import Settings


class IMAPClientError(RuntimeError):
    """Raised when an IMAP operation cannot be completed safely."""


@dataclass(frozen=True)
class MessageMetadata:
    """The non-body fields available from a read-only message fetch."""

    uid: str
    subject: str | None
    sender: str | None
    date: str | None
    message_id: str | None


@dataclass(frozen=True)
class MessageBody:
    """The text representation of a read-only message body fetch."""

    uid: str
    body: str


def build_search_criteria(
    *,
    query: str | None = None,
    sender: str | None = None,
    since_date: date | None = None,
    before_date: date | None = None,
) -> tuple[str, ...]:
    """Build safe IMAP SEARCH criteria from supported filters.

    Text values are always quoted and cannot contain control characters, so
    callers cannot inject additional IMAP search terms.
    """
    criteria: list[str] = []
    if since_date is not None:
        criteria.extend(("SINCE", _format_imap_date(since_date)))
    if before_date is not None:
        criteria.extend(("BEFORE", _format_imap_date(before_date)))
    if sender is not None:
        criteria.extend(("FROM", _quote_search_value(sender)))
    if query is not None:
        criteria.extend(("TEXT", _quote_search_value(query)))
    return tuple(criteria or ["ALL"])


def _format_imap_date(value: date) -> str:
    return value.strftime("%d-%b-%Y")


def _quote_search_value(value: str) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("IMAP search values cannot contain control characters")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def extract_message_body(message_bytes: bytes, max_chars: int) -> str:
    """Return a bounded Markdown-friendly body from an RFC 5322 message.

    Plain text is preferred over HTML. Attachments are never exposed as body
    content, including text files attached to an otherwise multipart message.
    """
    if max_chars <= 0:
        raise ValueError("maximum body length must be greater than zero")

    message = BytesParser(policy=policy.default).parsebytes(message_bytes)
    plain_text: str | None = None
    html: str | None = None
    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type()
        content = _decode_text_part(part)
        if not content:
            continue
        if content_type == "text/plain" and plain_text is None:
            plain_text = content
        elif content_type == "text/html" and html is None:
            html = content

    body = plain_text if plain_text is not None else html2text.html2text(html or "")
    return body[:max_chars]


def _decode_text_part(part: Message) -> str:
    """Decode a text MIME part without allowing malformed charsets to fail a read."""
    if part.get_content_maintype() != "text":
        return ""
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    try:
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


class ScopedIMAPClient:
    """A context-managed, read-only IMAP client constrained by ``Settings``."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: imaplib.IMAP4 | None = None

    def __enter__(self) -> "ScopedIMAPClient":
        try:
            self._connection = self._connect()
            self._require_ok(self._connection.login(
                self._settings.imap_user, self._settings.imap_password
            ), "authenticate")
        except Exception:
            self._logout()
            raise
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        self._logout()
        return False

    def search(
        self,
        folder: str,
        *,
        query: str | None = None,
        sender: str | None = None,
        since_date: date | None = None,
        before_date: date | None = None,
    ) -> tuple[str, ...]:
        """Return matching stable UIDs from an explicitly permitted folder."""
        connection = self._require_connection()
        self._select_readonly(folder)
        criteria = build_search_criteria(
            query=query,
            sender=sender,
            since_date=since_date,
            before_date=before_date,
        )
        status, data = connection.uid("SEARCH", None, *criteria)
        self._require_ok((status, data), "search")
        if not data or not data[0]:
            return ()
        return tuple(data[0].decode("ascii").split())

    def fetch_metadata(
        self, folder: str, uids: tuple[str, ...] | list[str]
    ) -> tuple[MessageMetadata, ...]:
        """Fetch selected message headers without marking messages as read."""
        connection = self._require_connection()
        self._select_readonly(folder)
        return tuple(self._fetch_one_metadata(connection, uid) for uid in uids)

    def fetch_body(self, folder: str, uid: str) -> MessageBody:
        """Fetch one message body without setting its ``\\Seen`` flag."""
        connection = self._require_connection()
        self._select_readonly(folder)
        self._validate_uid(uid)
        status, data = connection.uid("FETCH", uid, "(BODY.PEEK[])")
        self._require_ok((status, data), "fetch message body")
        message_bytes = next(
            (item[1] for item in data if isinstance(item, tuple) and len(item) > 1),
            None,
        )
        if not isinstance(message_bytes, bytes):
            raise IMAPClientError("IMAP returned no message body")
        return MessageBody(
            uid=uid,
            body=extract_message_body(message_bytes, self._settings.max_body_chars),
        )

    def _connect(self) -> imaplib.IMAP4:
        context = ssl.create_default_context()
        if self._settings.imap_ssl:
            return imaplib.IMAP4_SSL(
                self._settings.imap_host,
                self._settings.resolved_port,
                ssl_context=context,
                timeout=self._settings.imap_timeout_seconds,
            )

        connection = imaplib.IMAP4(
            self._settings.imap_host,
            self._settings.resolved_port,
            timeout=self._settings.imap_timeout_seconds,
        )
        if self._settings.imap_starttls:
            self._require_ok(connection.starttls(ssl_context=context), "start TLS")
        return connection

    def _select_readonly(self, folder: str) -> None:
        # Enforce scope before emitting any protocol command for this folder.
        allowed_folder = self._settings.validate_folder_access(folder)
        self._require_ok(
            self._require_connection().select(allowed_folder, readonly=True), "open folder"
        )

    def _fetch_one_metadata(
        self, connection: imaplib.IMAP4, uid: str
    ) -> MessageMetadata:
        self._validate_uid(uid)
        status, data = connection.uid(
            "FETCH",
            uid,
            "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE MESSAGE-ID)])",
        )
        self._require_ok((status, data), "fetch message metadata")
        header_bytes = next(
            (item[1] for item in data if isinstance(item, tuple) and len(item) > 1),
            None,
        )
        if not isinstance(header_bytes, bytes):
            raise IMAPClientError("IMAP returned no message headers")
        message = BytesParser(policy=policy.default).parsebytes(header_bytes)
        return MessageMetadata(
            uid=uid,
            subject=message.get("Subject"),
            sender=message.get("From"),
            date=message.get("Date"),
            message_id=message.get("Message-ID"),
        )

    @staticmethod
    def _validate_uid(uid: str) -> None:
        if not uid.isascii() or not uid.isdecimal() or not uid:
            raise ValueError("message UID must be a non-empty decimal string")

    def _require_connection(self) -> imaplib.IMAP4:
        if self._connection is None:
            raise IMAPClientError("IMAP client must be used as a context manager")
        return self._connection

    @staticmethod
    def _require_ok(
        response: tuple[str, list[object]], operation: str
    ) -> None:
        status, _ = response
        if status != "OK":
            raise IMAPClientError(f"Unable to {operation} with the IMAP server")

    def _logout(self) -> None:
        if self._connection is None:
            return
        connection, self._connection = self._connection, None
        try:
            connection.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
