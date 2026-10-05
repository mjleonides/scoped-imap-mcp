Here is a structured implementation plan designed for development with **OpenCode**. It organizes the project into clean, incremental phases with strict security boundaries, minimal dependencies, and clear verification steps.

---

# `scoped-imap-mcp` Implementation Plan

## Phase 1: Project Setup & Modern Packaging

- **Objective:** Establish the Python project structure using `pyproject.toml` so it can be executed natively via `uvx scoped-imap-mcp` or `python -m scoped_imap_mcp`.
- **Key Tasks:**
  1. Define dependencies:
     - `mcp>=1.0.0` (Official Python Model Context Protocol SDK)
     - `html2text` (Fast, lightweight HTML-to-Markdown conversion)
     - `pydantic-settings` (Type-safe environment variable parsing)
  2. Configure console script entry point: `scoped-imap-mcp = "scoped_imap_mcp.server:main"`.

---

## Phase 2: Configuration & Sandboxing Engine (`config.py`)

- **Objective:** Load environment variables and define the whitelist validation layer.
- **Key Tasks:**
  1. Parse standard IMAP settings (`IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASSWORD`, `IMAP_SSL`, `IMAP_STARTTLS`).
  2. Implement `IMAP_ALLOWED_FOLDERS` parsing:
     - Parse comma-separated strings (e.g., `"Labels/Amazon, Receipts, Newsletters"`).
     - If only **one** folder is provided, flag the mode as `SINGLE_FOLDER_MODE`.
     - If multiple folders are provided, flag as `MULTI_FOLDER_MODE`.
  3. Enforce validation helper: `validate_folder_access(target_folder: str) -> str` that raises an immediate security exception if a folder is not in the whitelist.

---

## Phase 3: Scoped IMAP Client (`imap_client.py`)

- **Objective:** Encapsulate IMAP operations with read-only guarantees and query building.
- **Key Tasks:**
  1. **Connection Lifecycle:**
     - Implement context-managed IMAP connection handling (`IMAP4` or `IMAP4_SSL`).
     - Always issue `EXAMINE` (or `SELECT ... readonly=True`) to guarantee zero-mutation / read-only access.
  2. **Query Builder:**
     - Translate friendly AI arguments (`query`, `sender`, `since_date`, `before_date`) into RFC 3501 IMAP search strings (e.g., `SINCE "01-Nov-2024" FROM "amazon.com" TEXT "34.19"`).
  3. **Metadata Fetcher:**
     - Fetch headers (`Subject`, `From`, `Date`, `Message-ID`) for search results without downloading full message payloads.

---

## Phase 4: Token-Optimized Cleaner & MIME Parser (`cleaner.py`)

- **Objective:** Convert multi-megabyte commercial receipt/newsletter emails into clean Markdown, cutting token usage by 90%+.
- **Key Tasks:**
  1. **MIME Extraction:**
     - Traverse multipart messages, prioritizing `text/plain` when available, falling back to `text/html`.
     - Handle character encodings (UTF-8, Latin-1, Quoted-Printable).
  2. **HTML Sanitization:**
     - Use `html2text` configured to ignore images, strip inline CSS/scripts, and retain clean tabular data (item lists, prices, order IDs).
  3. **Character Truncation Safeguard:**
     - Enforce `MAX_BODY_CHARS` limit with a visible `[Content truncated for token safety]` indicator.

---

## Phase 5: FastMCP Tool Server (`server.py`)

- **Objective:** Expose the MCP tools to AI clients over `stdio`.
- **Key Tasks:**
  1. Initialize `FastMCP("Scoped IMAP Sandbox")`.
  2. Register tools with dynamic schemas:
     - **`search_emails`**: Exposes search filters. In `SINGLE_FOLDER_MODE`, the `folder` argument is hidden entirely. In `MULTI_FOLDER_MODE`, `folder` is validated against the whitelist.
     - **`read_email`**: Retrieves and cleans the email matching `message_id`.
     - **`list_allowed_folders`**: Returns the list of permitted folders so the LLM knows what is accessible.

---

## Phase 6: Testing, Homelab Integration & Documentation

- **Objective:** Verify security isolation, test against Proton Mail Bridge, and document setup.
- **Key Tasks:**
  1. **Unit & Security Tests:**
     - Mock IMAP tests verifying that requesting `INBOX` throws a validation rejection when `IMAP_ALLOWED_FOLDERS="Labels/Amazon"`.
  2. **Proton Bridge Docker Recipe:**
     - Document `docker-compose.yml` for running headless Proton Bridge alongside Claude Desktop / AI clients.
  3. **README Documentation:**
     - Configuration matrix, `uvx` setup instructions, and Claude Desktop `claude_desktop_config.json` examples.

---

### Suggested Next Step

Would you like to start drafting the code for **Phase 1 & 2** (project structure and configuration/sandboxing engine), or would you prefer to adjust any part of this plan first?
