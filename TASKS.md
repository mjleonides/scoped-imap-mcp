# Project Tasks

## Completed

- [x] Create modern Python packaging with a `src/` layout and console entry point.
- [x] Add module execution support with `python -m scoped_imap_mcp`.
- [x] Add `.env`-backed settings with environment-variable overrides.
- [x] Support selecting a settings file through `IMAP_ENV_FILE`.
- [x] Require a non-empty `IMAP_ALLOWED_FOLDERS` whitelist.
- [x] Normalize folder names and reject empty or duplicate whitelist entries.
- [x] Enforce exact folder access validation before any IMAP operation.
- [x] Default to SSL/TLS and reject plaintext IMAP without `IMAP_ALLOW_INSECURE=true`.
- [x] Add `.env.example`, Dockerfile, Docker Compose scaffold, and configuration documentation.
- [x] Add configuration and security tests.
- [x] Verify 12 tests pass and Python sources compile.

## Pending

- [x] Migrate to MCP 2.x (`MCPServer`), add MCP tool-registration and protocol
  tests, then revalidate the Docker image and Compose startup.
- [x] Implement the scoped, read-only IMAP client.
- [x] Build IMAP search queries from MCP tool arguments.
- [x] Fetch message metadata without mutation-capable IMAP commands.
- [x] Implement MIME extraction, HTML-to-Markdown conversion, and body truncation.
- [x] Register MCP tools for searching, reading, and listing allowed folders.
- [ ] Validate the documented `uv` workflow.
- [x] Build and validate the Docker image and Compose configuration.
- [ ] Test against Proton Mail Bridge or another target IMAP service.
- [ ] Expand operational and client-integration documentation.

## Verification Notes

- `pytest`: 26 tests passed using Python 3.14.7 after the MCP 2.x migration.
- Docker image and Compose startup were validated with a non-secret temporary
  configuration using MCP 2.3.0.
- `uv` and Docker were unavailable in the development environment, so their workflows remain unverified.
