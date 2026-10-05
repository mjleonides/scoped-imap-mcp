import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

from scoped_imap_mcp.config import Settings
from scoped_imap_mcp import server as server_module


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "imap_host": "mail.example.test",
        "imap_user": "user@example.test",
        "imap_password": "secret",
        "imap_allowed_folders": "Receipts",
    }
    values.update(overrides)
    return Settings(**values)


def test_server_registers_tool_schemas() -> None:
    tools = asyncio.run(server_module.create_server(settings()).list_tools())
    tools_by_name = {tool.name: tool for tool in tools}

    assert set(tools_by_name) == {
        "list_allowed_folders",
        "search_messages",
        "read_message",
    }
    assert tools_by_name["list_allowed_folders"].description
    assert set(tools_by_name["search_messages"].input_schema["properties"]) == {
        "folder",
        "query",
        "sender",
        "since_date",
        "before_date",
        "max_results",
    }
    assert tools_by_name["search_messages"].input_schema["properties"]["max_results"] == {
        "default": 50,
        "title": "Max Results",
        "type": "integer",
    }
    assert tools_by_name["read_message"].input_schema["required"] == ["uid"]


def test_list_allowed_folders_is_invocable_through_mcp() -> None:
    result = asyncio.run(
        server_module.create_server(settings()).call_tool("list_allowed_folders", {})
    )

    assert result.is_error is False
    assert result.structured_content == {"result": ["Receipts"]}


def test_search_uses_single_folder_default_through_mcp(
    monkeypatch: object,
) -> None:
    calls: list[object] = []

    class FakeIMAPClient:
        def __init__(self, configured_settings: Settings) -> None:
            assert configured_settings.allowed_folders == ("Receipts",)

        def __enter__(self) -> "FakeIMAPClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def search(self, folder: str, **kwargs: object) -> tuple[str, ...]:
            calls.append((folder, kwargs))
            return ("101",)

        def fetch_metadata(
            self, folder: str, uids: list[str]
        ) -> list[SimpleNamespace]:
            assert folder == "Receipts"
            assert uids == ["101"]
            return [
                SimpleNamespace(
                    uid="101",
                    subject="Receipt",
                    sender="Shop <orders@example.test>",
                    date="Thu, 01 Feb 2024 10:00:00 +0000",
                    message_id="<receipt@example.test>",
                )
            ]

    monkeypatch.setattr(server_module, "ScopedIMAPClient", FakeIMAPClient)
    result = asyncio.run(
        server_module.create_server(settings()).call_tool(
            "search_messages", {"query": "order 123"}
        )
    )

    assert result.is_error is False
    assert result.structured_content == {
        "result": [
            {
                "uid": "101",
                "subject": "Receipt",
                "sender": "Shop <orders@example.test>",
                "date": "Thu, 01 Feb 2024 10:00:00 +0000",
                "message_id": "<receipt@example.test>",
            }
        ]
    }
    assert calls == [
        (
            "Receipts",
            {
                "query": "order 123",
                "sender": None,
                "since_date": None,
                "before_date": None,
            },
        )
    ]


def test_main_loads_settings_before_starting_stdio(monkeypatch: object) -> None:
    configured_settings = settings()
    mcp_server = Mock()
    monkeypatch.setattr(server_module, "load_settings", lambda: configured_settings)
    monkeypatch.setattr(
        server_module,
        "create_server",
        lambda received_settings: mcp_server,
    )

    server_module.main()

    mcp_server.run.assert_called_once_with(transport="stdio")
