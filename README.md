# scoped-imap-mcp

A read-only Model Context Protocol server that exposes only explicitly allowed
IMAP folders. It provides `list_allowed_folders`, `search_messages`, and
`read_message` tools over stdio. Searches return metadata only; reads extract
plain text where available, convert HTML-only messages to Markdown, ignore
attachments, and limit the body to `IMAP_MAX_BODY_CHARS` (50,000 by default).

## Configuration

Copy `.env.example` to `.env`, set the required account settings, and name one
or more accessible folders in `IMAP_ALLOWED_FOLDERS`. Folder names are matched
exactly after leading and trailing whitespace is removed. An empty list,
duplicate names, and empty list entries are rejected at startup.

The settings loader reads `.env` by default. Environment variables override
values in that file. To load a different file, set `IMAP_ENV_FILE` in the
process environment, for example `IMAP_ENV_FILE=/run/secrets/imap.env`.

SSL/TLS is enabled by default and uses port 993 when `IMAP_PORT` is unset.
For a STARTTLS setup, set `IMAP_SSL=false` and `IMAP_STARTTLS=true`; port 143
is selected when unset. Plaintext IMAP is rejected unless both SSL and STARTTLS
are disabled and `IMAP_ALLOW_INSECURE=true` is explicitly configured.

## Docker Compose

Create the local `.env` file, then run:

```sh
docker compose up --build
```

Compose passes that file to the container with `env_file`; it is not included
in the image. The container runs as an unprivileged user with a read-only
filesystem.

## Development

Install the package and test dependencies with `uv`:

```sh
uv sync --group dev
uv run pytest
```

The console entry point and module entry point both validate configuration:

```sh
uv run scoped-imap-mcp
uv run python -m scoped_imap_mcp
```

When more than one folder is allowed, `search_messages` and `read_message`
require a `folder` argument. With exactly one allowed folder, that folder is
used by default. Search dates use `YYYY-MM-DD`, and `max_results` is limited to
1 through 100.
