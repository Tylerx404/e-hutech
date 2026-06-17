# syntax=docker/dockerfile:1.6
#
# Optimized multi-stage Dockerfile for GitHub Actions builds
# Key optimizations:
# - No gcc (all dependencies provide manylinux wheels)
# - BuildKit cache mount for pip (works great with cache-from: type=gha)
# - Aggressive stripping of build artifacts for smaller runtime image
# - Non-root user for security
# - Requirements copied early for excellent layer caching
# - .dockerignore keeps build context tiny (~1-2 KB)

FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

COPY requirements.txt .

# Use persistent pip cache across builds.
# Combined with docker/build-push-action cache-from: type=gha this makes
# repeated builds on GitHub Actions extremely fast when requirements don't change.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-compile --target=/install -r requirements.txt \
        --root-user-action=ignore

# Remove pip, setuptools, wheel, .pyc and __pycache__ from the installation
# directory to keep the final image small.
RUN find /install -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true \
    && find /install -type f -name '*.pyc' -delete \
    && find /install -maxdepth 1 -type d \( -name 'pip' -o -name 'pip-*' -o -name 'setuptools' -o -name 'setuptools-*' -o -name 'wheel' -o -name 'wheel-*' -o -name 'pkg_resources' \) -exec rm -rf {} + 2>/dev/null || true

FROM python:3.12-slim-bookworm AS runtime

# Version is passed from GitHub Actions release workflow
ARG APP_VERSION=dev

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONPATH=/install \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Ho_Chi_Minh \
    APP_VERSION=${APP_VERSION}

LABEL org.opencontainers.image.version="${APP_VERSION}"

WORKDIR /app

# Create a non-root user and prepare /data for SQLite (when used)
RUN groupadd --system --gid 1001 appuser \
    && useradd --system --uid 1001 --gid appuser --home-dir /app --shell /usr/sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

# Copy already-stripped dependencies from builder stage
COPY --from=builder /install /install

# Copy application source (filtered by .dockerignore)
COPY --chown=appuser:appuser . .

# Final cleanup of any .pyc files that might have been created during COPY
RUN find /app -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true \
    && find /app -type f -name '*.pyc' -delete 2>/dev/null || true \
    && chown -R appuser:appuser /app

USER appuser

VOLUME ["/data"]

# Lightweight healthcheck (fast-failing import is better than always-success)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import sys, aiohttp; sys.exit(0)" || exit 1

CMD ["python", "bot.py"]
