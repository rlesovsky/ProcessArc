# Running ProcessArc in Docker

ProcessArc ships as a multi-arch container image on GitHub Container
Registry. The same image runs the full app — FastAPI backend + built
React frontend — on linux/amd64 (Intel/AMD servers, most cloud VMs)
and linux/arm64 (Apple Silicon, Raspberry Pi 4/5, AWS Graviton, modern
Synology NAS).

Image: **`ghcr.io/rlesovsky/processarc`**

## Quick start (docker run)

```bash
docker run -d --name processarc \
  -p 8000:8000 \
  -v processarc-data:/data \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  --restart unless-stopped \
  ghcr.io/rlesovsky/processarc:latest
```

Open `http://localhost:8000`.

## Quick start (docker compose)

The repo ships a reference [`docker-compose.yml`](../docker-compose.yml).
Pull it next to a `.env` containing your API key:

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
```

Then:

```bash
docker compose up -d
```

## What lives where

| Path inside the container | Purpose | Persist? |
|---|---|---|
| `/data/.env` | Anthropic API key + model selection (writable from the UI) | Yes — volume |
| `/data/projects/` | Per-project working state and generated deliverables | Yes — volume |
| `/data/templates/` | Customer / vendor template workbooks read at runtime | Yes — volume |
| `/app/backend/` | App code (read-only at runtime) | No — baked into image |
| `/app/frontend/dist/` | Built React app served at `/` | No — baked into image |

The volume mount on `/data` is what makes state survive `docker rm` /
`docker pull` / image upgrades. Without it, the container is
read-mostly and any UI changes (saved API key, project files) are
lost when the container is removed.

## Environment variables

| Variable | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Your Claude API key. Required for any AI-assisted feature. The UI can also save it through "API key" → settings panel, which writes to `/data/.env`. |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Override the Claude model name. |
| `PORT` | `8000` | Port uvicorn binds to inside the container. Useful for cloud PaaS that injects a `$PORT` (Fly.io, Render, Railway). |
| `PROCESSARC_DATA_DIR` | `/data` | Where `.env` / `projects/` / `templates/` live. Don't change unless you want to mount the volume elsewhere. |

## Upgrading

```bash
docker compose pull && docker compose up -d
# or, without compose:
docker pull ghcr.io/rlesovsky/processarc:latest
docker stop processarc && docker rm processarc
# re-run the original `docker run` command — the volume keeps your data
```

The image is pinned by tag, so:
- `:latest` follows the most recent release tag (`vX.Y.Z`)
- `:edge` follows `main` (unstable, useful for trying changes early)
- `:vX.Y.Z` pins to a specific release
- `:vX.Y` / `:vX` pin to a minor / major line and roll forward inside it

## Production notes

### Reverse proxy

For anything beyond `localhost`, put it behind a reverse proxy that
terminates TLS — Caddy, nginx, Traefik. The container speaks plain
HTTP and doesn't manage certs. Example Caddy snippet:

```
processarc.example.com {
  reverse_proxy localhost:8000
}
```

### Resource limits

The container is light — ~200 MB RAM idle, peaks during xlsx parsing
and Claude calls. A `mem_limit: 1g` in compose is comfortable headroom.

### Permissions on bind mounts

If you swap the named volume for a host bind mount (e.g.
`-v /srv/processarc:/data`), the host directory must be writable by
UID 1000 (the `processarc` user inside the image). Either:

```bash
sudo chown -R 1000:1000 /srv/processarc
```

…or use a named volume (Docker handles ownership for you).

## Where the image is built

The image is built by
[`.github/workflows/build-docker.yml`](../.github/workflows/build-docker.yml)
on every push to `main` (publishes `:edge`) and every `v*` tag push
(publishes `:latest` + semver tags). The workflow runs on
`ubuntu-latest` and uses `docker/setup-qemu-action` to emit arm64
layers via emulation — slower than a native arm64 runner but free,
and the GitHub Actions cache makes second-and-later builds fast.

You can also build locally:

```bash
# Single-arch (your machine's native arch):
docker build -t processarc:dev .

# Multi-arch (requires buildx + qemu):
docker buildx create --use --name processarc-builder
docker buildx build --platform=linux/amd64,linux/arm64 -t processarc:dev .
# Add --push to upload to a registry; --load only works for one arch.
```

## Differences vs the Windows .exe build

| Aspect | Windows .exe | Docker image |
|---|---|---|
| Trigger model | Double-click, browser opens | `docker run`, no browser open |
| Data location | `%APPDATA%\ProcessArc\` | `/data` (volume mount) |
| Process model | Single-user desktop | Headless server, designed to be reverse-proxied |
| Logs | Rotating file in user-data dir | stdout (use `docker logs`) |
| Same backend code? | Yes | Yes |
| Same UI code? | Yes (built React `dist/`) | Yes (built React `dist/`) |

Both paths use the same `backend.api.main:app` and the same React
build — the only thing that differs is what wraps it.
