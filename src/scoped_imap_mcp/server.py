"""MCP server exposing read-only, folder-scoped IMAP tools."""

from __future__ import annotations

from datetime import date

from mcp.server import MCPServer

from .config import Settings, load_settings
from .imap_client import ScopedIMAPClient


def create_server(settings: Settings) -> MCPServer:
    """Create an MCP server bound to one validated IMAP configuration."""
    server = MCPServer("Scoped IMAP")

    @server.tool()
    def list_allowed_folders() -> list[str]:
        """List the only IMAP folders available through this server."""
        return list(settings.allowed_folders)

    @server.tool()
    def search_messages(
        folder: str | None = None,
        query: str | None = None,
        sender: str | None = None,
        since_date: str | None = None,
        before_date: str | None = None,
        max_results: int = 50,
    ) -> list[dict[str, str | None]]:
        """Search an allowed folder and return message metadata, newest UID first."""
        target_folder = _resolve_folder(settings, folder)
        if not 1 <= max_results <= 100:
            raise ValueError("max_results must be between 1 and 100")

        with ScopedIMAPClient(settings) as client:
            uids = client.search(
                target_folder,
                query=query,
                sender=sender,
                since_date=_parse_date(since_date, "since_date"),
                before_date=_parse_date(before_date, "before_date"),
            )
            metadata = client.fetch_metadata(target_folder, list(reversed(uids[-max_results:])))
        return [
            {
                "uid": message.uid,
                "subject": message.subject,
                "sender": message.sender,
                "date": message.date,
                "message_id": message.message_id,
            }
            for message in metadata
        ]

    @server.tool()
    def read_message(uid: str, folder: str | None = None) -> dict[str, str | None]:
        """Read metadata and a Markdown-friendly body from one allowed-folder UID."""
        target_folder = _resolve_folder(settings, folder)
        with ScopedIMAPClient(settings) as client:
            metadata = client.fetch_metadata(target_folder, [uid])[0]
            body = client.fetch_body(target_folder, uid)
        return {
            "uid": metadata.uid,
            "subject": metadata.subject,
            "sender": metadata.sender,
            "date": metadata.date,
            "message_id": metadata.message_id,
            "body": body.body,
        }

    return server


def _resolve_folder(settings: Settings, folder: str | None) -> str:
    if folder is None:
        if settings.single_folder_mode:
            return settings.default_folder
        raise ValueError("folder is required when multiple folders are allowed")
    return settings.validate_folder_access(folder)


def _parse_date(value: str | None, field_name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format") from error


def main() -> None:
    """Start the stdio MCP server after validating runtime configuration."""
    create_server(load_settings()).run(transport="stdio")
