# ── Global build args (must be before first FROM) ──────────────────────────────
# Pin images by tag (not digest) so Docker resolves the correct architecture
# for multi-arch builds (amd64 + arm64).
ARG LITELLM_BUILD_IMAGE=cgr.dev/chainguard/wolfi-base:latest
ARG LITELLM_RUNTIME_IMAGE=cgr.dev/chainguard/wolfi-base:latest
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.7

# ── Build stage 0: headroom-ai wheel (native Linux build) ────────────────────
# Compiled natively so the Rust .so inside the wheel matches the Docker target.
# Python 3.12-slim has the libc/toolchain maturin needs; the wheel artifact
# (~20 MB) alone is passed to the lite-llm builder stage below.
FROM python:3.12-slim AS headroom-builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*
# Install latest stable Rust (Debian's rustc 1.85 is too old for headroom's deps)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
RUN pip install maturin
COPY better-headroom/ /build/
RUN maturin build --release --out /wheels && rm -rf /build

# ── Build stage 1: lite-llm builder ──────────────────────────────────────────
FROM $UV_IMAGE AS uvbin

FROM $LITELLM_BUILD_IMAGE AS builder

WORKDIR /app
USER root

COPY --from=uvbin /uv /usr/local/bin/uv
COPY --from=uvbin /uvx /usr/local/bin/uvx

RUN apk add --no-cache \
    bash \
    gcc \
    python3 \
    python3-dev \
    openssl \
    openssl-dev \
    nodejs \
    npm \
    libsndfile \
    coreutils

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

# Copy dependency metadata first for layer caching
COPY pyproject.toml uv.lock ./
COPY enterprise/pyproject.toml enterprise/
COPY litellm-proxy-extras/pyproject.toml litellm-proxy-extras/

# Pre-install headroom from the wheel built in stage 0 (native Linux, ~20 MB)
# so uv never tries to resolve the local path dependency from pyproject.toml.
COPY --from=headroom-builder /wheels/*.whl /tmp/headroom-wheels/
RUN uv venv "${UV_PROJECT_ENVIRONMENT}" && \
    uv pip install /tmp/headroom-wheels/*.whl && rm -rf /tmp/headroom-wheels

# Remove the local path dependency so uv resolves from the pre-installed wheel.
# (The path dep stays in pyproject.toml for local dev — only removed inside Docker.)
RUN sed -i '/headroom-ai = { path = "\.\.\/better-headroom" }/d' pyproject.toml \
    && sed -i '/\.\.\/better-headroom/d' pyproject.toml

# Install third-party dependencies (headroom-ai is already installed, uv skips it)
RUN uv sync --no-install-project --no-install-workspace --no-default-groups --no-editable \
    --extra proxy \
    --extra proxy-runtime \
    --extra extra_proxy \
    --extra semantic-router \
    --python python3

# Copy full source tree
COPY . .

# Build Admin UI before final sync
RUN sed -i 's/\r$//' docker/build_admin_ui.sh && chmod +x docker/build_admin_ui.sh && ./docker/build_admin_ui.sh

# Install project and workspace packages (headroom-ai already installed, uv skips it)
RUN uv sync --no-default-groups --no-editable \
    --extra proxy \
    --extra proxy-runtime \
    --extra extra_proxy \
    --extra semantic-router \
    --python python3

RUN prisma generate --schema=./schema.prisma

RUN sed -i 's/\r$//' docker/entrypoint.sh && chmod +x docker/entrypoint.sh && \
    sed -i 's/\r$//' docker/prod_entrypoint.sh && chmod +x docker/prod_entrypoint.sh

# Runtime stage
FROM $LITELLM_RUNTIME_IMAGE AS runtime

USER root

RUN apk add --no-cache bash openssl tzdata nodejs npm python3 libsndfile && \
    npm install -g npm@11.14.0 tar@7.5.11 glob@13.0.6 @isaacs/brace-expansion@5.0.1 brace-expansion@5.0.5 minimatch@10.2.4 diff@8.0.3 picomatch@4.0.4 && \
    GLOBAL="$(npm root -g)" && \
    for pkg in tar glob @isaacs/brace-expansion brace-expansion minimatch diff picomatch; do \
        name="${pkg##*/}"; \
        find "$GLOBAL/npm" -type d -name "$name" -path "*/node_modules/$pkg" | while read d; do \
            rm -rf "$d" && cp -rL "$GLOBAL/$pkg" "$d"; \
        done; \
    done && \
    npm cache clean --force && \
    { apk del --no-cache npm 2>/dev/null || true; }

WORKDIR /app
ENV PATH="/app/.venv/bin:${PATH}"

COPY --from=builder /app /app
# Prisma binaries live in $HOME/.cache (default prisma-python location),
# which is /root/.cache here. Copy only the Prisma subdirs — copying the
# whole /root/.cache drags in the uv build cache (~660 MB, includes a
# setuptools wheel that surfaces as a CVE finding even though it's not
# on the runtime sys.path).
COPY --from=builder /root/.cache/prisma /root/.cache/prisma
COPY --from=builder /root/.cache/prisma-python /root/.cache/prisma-python

RUN find /app/.venv -type f -path "*/tornado/test/*" -delete && \
    find /app/.venv -type d -path "*/tornado/test" -delete

EXPOSE 4000/tcp

ENTRYPOINT ["docker/prod_entrypoint.sh"]
CMD ["--port", "4000"]
