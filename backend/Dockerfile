# ============================================================
# ISTS Backend — Multi-stage Docker Image
# Stage 1 (builder): install deps with uv into a venv
# Stage 2 (runtime): lean image with venv + app source
# Supports CMD override for worker/beat (no separate image needed)
# ============================================================

# ── Stage 1: builder ─────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install uv from the official distroless image (fastest Python package installer)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifest only — layer is cached until pyproject.toml changes
COPY pyproject.toml .

# Create an isolated venv and install all production dependencies
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache .

# ── Stage 2: runtime ─────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# libmagic1 — required by python-magic for file-type validation on uploads
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy the pre-built virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Activate the venv for all subsequent commands
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Copy application source
COPY alembic.ini .
COPY alembic ./alembic
COPY scripts ./scripts
COPY app ./app

# Create the local document storage directory (mounted as a volume in dev)
RUN mkdir -p /app/storage/standards

# Default command — overridden in docker-compose.yml per service
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
