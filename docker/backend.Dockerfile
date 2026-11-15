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

# Copy build definition, source code and migrations
COPY pyproject.toml .
COPY src src
COPY alembic.ini .
COPY alembic alembic

# Install package and dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[dev]"

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

EXPOSE 8000

# Entrypoint runs Alembic migrations then starts Uvicorn
CMD ["sh", "-c", "alembic upgrade head && uvicorn corbel.main:app --host 0.0.0.0 --port 8000"]
