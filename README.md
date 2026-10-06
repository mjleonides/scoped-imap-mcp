# scoped-imap-mcp

A read-only Model Context Protocol server that exposes only explicitly allowed
IMAP folders. It provides `list_allowed_folders`, `search_messages`, and
`read_message` tools over authenticated Streamable HTTP. Searches return metadata only; reads extract
plain text where available, convert HTML-only messages to Markdown, ignore
attachments, and limit the body to `IMAP_MAX_BODY_CHARS` (50,000 by default).

## Configuration

Copy `.env.example` to `.env`, set the required account settings, and name one
or more accessible folders in `IMAP_ALLOWED_FOLDERS`. Folder names are matched
exactly after leading and trailing whitespace is removed. An empty list,
duplicate names, and empty list entries are rejected at startup.

Set `MCP_BEARER_TOKEN` to a long random secret before starting the server:

```sh
openssl rand -base64 32
```

The Streamable HTTP endpoint defaults to `http://<host>:8000/mcp`. Every
request must send `Authorization: Bearer <MCP_BEARER_TOKEN>`. `MCP_HOST`,
`MCP_PORT`, and `MCP_PATH` can override the default bind address, port, and
path. The token is required; the server refuses to start without it.

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
in the image. It publishes port 8000 to the host, runs as an unprivileged user,
and uses a read-only filesystem.

## Open WebUI

Create a Streamable HTTP MCP connection in Open WebUI, set its bearer token to
the value of `MCP_BEARER_TOKEN`, and use one of these URLs:

- `http://scoped-imap-mcp:8000/mcp` when Open WebUI is on the same Compose network.
- `http://host.docker.internal:8000/mcp` when Open WebUI runs in another Docker
  Compose stack on Docker Desktop.
- `http://<host-LAN-IP-or-DNS>:8000/mcp` from the LAN.

Use an HTTPS reverse proxy before exposing the LAN endpoint beyond a trusted
private network. A bearer token sent over plain HTTP can be intercepted.

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
