# syntax=docker/dockerfile:1.7
#
# Multi-stage Dockerfile for ProcessArc — produces a single image that
# bundles the FastAPI backend + the built React frontend, serving both
# from a single port. Designed for self-hosted deployments.
#
# Build (multi-arch, via buildx):
#   docker buildx build --platform=linux/amd64,linux/arm64 \
#     -t ghcr.io/rlesovsky/processarc:dev --push .
#
# Run (single-arch, locally):
#   docker run --rm -p 8000:8000 \
#     -v processarc-data:/data \
#     -e ANTHROPIC_API_KEY=sk-ant-... \
#     ghcr.io/rlesovsky/processarc:latest
#
# Then open http://localhost:8000

# ─── Stage 1: build the React frontend ──────────────────────────────────────
FROM --platform=$BUILDPLATFORM node:20-alpine AS frontend
WORKDIR /src/frontend

# Copy lockfiles first for layer-cache friendliness — re-installing
# happens only when deps change, not on every source edit.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build
# Output is /src/frontend/dist (copied into stage 2 below).

# ─── Stage 2: runtime image ─────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Layered metadata follows OCI conventions; populated with build args
# by the GitHub Actions workflow (.github/workflows/build-docker.yml).
ARG VERSION=dev
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="ProcessArc" \
      org.opencontainers.image.description="UFP wood-treatment project automation tool" \
      org.opencontainers.image.source="https://github.com/rlesovsky/ProcessArc" \
      org.opencontainers.image.licenses="UNLICENSED" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.created="$BUILD_DATE"

# Python runtime hygiene:
#  - PYTHONDONTWRITEBYTECODE: no .pyc clutter in the image / volume
#  - PYTHONUNBUFFERED: log lines hit stdout immediately so `docker logs`
#    is useful while a request is in flight
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PROCESSARC_DATA_DIR=/data \
    PORT=8000

# System deps. python-docx + openpyxl are pure-Python; the only thing
# the slim image needs that it doesn't already have is the libxml2 set
# pulled in transitively by lxml (which python-docx depends on).
# Keeping the package list tight to minimize image size.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        tini \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for cache friendliness — invalidates only
# when requirements.txt changes, not when backend source changes.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip \
 && pip install -r /app/backend/requirements.txt

# Copy backend source + bring the built frontend in from stage 1.
COPY backend/ /app/backend/
COPY --from=frontend /src/frontend/dist /app/frontend/dist

# Persistent data lives here — .env, projects/, templates/, logs/.
# Volume-mount this to keep state across container restarts.
VOLUME ["/data"]

# Run as a non-root user. Anything in /data needs to be writable by
# this user when the volume is bind-mounted from the host — see
# docs/docker.md for the chown trick if you hit permission errors.
RUN useradd --create-home --uid 1000 processarc \
 && mkdir -p /data \
 && chown -R processarc:processarc /data
USER processarc

EXPOSE 8000

# Healthcheck hits the same /health endpoint the desktop launcher uses.
# Curl is not installed in slim — use python instead.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, os; \
urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health', timeout=3)" \
    || exit 1

# tini reaps zombies and forwards signals to uvicorn so `docker stop`
# does a clean shutdown instead of a 10-second SIGKILL wait.
ENTRYPOINT ["/usr/bin/tini", "--"]

# Run uvicorn directly (no desktop launcher — no browser to open in a
# headless container, and we want PID 1 to be uvicorn so Docker
# signals land correctly).
CMD ["sh", "-c", "uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
