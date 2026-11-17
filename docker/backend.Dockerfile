# ==============================================================================
# Corbel Backend — Dockerfile (Python 3.11+ / FastAPI)
# ==============================================================================

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for compiling or network health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy build definition, lockfile, source code and migrations
COPY pyproject.toml uv.lock ./
COPY src src
COPY alembic.ini .
COPY alembic alembic

# Install package and dependencies deterministically using uv and uv.lock (P1-LIM-007)
RUN pip install --no-cache-dir uv && \
    uv pip install --system -e ".[dev]"

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

EXPOSE 8000

# Entrypoint runs Uvicorn server (migrations are decoupled to deployment step, P1-LIM-011)
CMD ["uvicorn", "corbel.main:app", "--host", "0.0.0.0", "--port", "8000"]
