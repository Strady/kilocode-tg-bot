# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: resolve && install runtime dependencies into a venv with uv.
# Base is Ubuntu 24.04 (noble) — same release the host uses, so apt works.
# The official `python` image only ships Debian/Alpine variants (no Ubuntu),
# so Python is installed via apt here.
# kilocode-client comes from git, so git + build tools are required.
# ---------------------------------------------------------------------------
FROM ubuntu:24.04 AS builder
WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip git build-essential \
    && rm -rf /var/lib/apt/lists/*

# uv binary from the uv image (distroless, no shell — but we only need /uv).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV PATH="/usr/local/bin:$PATH"

COPY pyproject.toml uv.lock ./
COPY kilocode_tg_bot ./kilocode_tg_bot

# Install the project and its runtime deps (no dev extras) from the lockfile.
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2: slim runtime image. Copy only the venv and package source.
# ---------------------------------------------------------------------------
FROM ubuntu:24.04
WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

# uv sync creates a venv bound to the builder's python; block base is the same
# Ubuntu release across stages so the venv link is valid.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY kilocode_tg_bot ./kilocode_tg_bot

# State directory for the SQLite session store.
RUN mkdir -p /data
VOLUME ["/data"]

# Entry point is the packaged console script (sync wrapper over asyncio.run).
CMD ["kilocode-tg-bot"]