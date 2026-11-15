# Corbel — Enterprise AI & Operational Intelligence Platform

> **Discover business context. Understand operations. Build intelligent solutions. Learn from failures. Execute with human approval.**

Corbel is a modular monolith platform connecting enterprise data, discovering operational processes, identifying business exceptions and recurring failures, investigating their causes, quantifying financial impact, and recommending governed business actions with mandatory human-in-the-loop approval.

---

## Authoritative Technology Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (asyncio + asyncpg / psycopg), Alembic.
- **Frontend:** React 19, TypeScript (`strict: true`), Vite, Tailwind CSS v4.
- **Database:** PostgreSQL 16+.
- **Testing:** `pytest` (backend unit and integration tests), `Vitest` (frontend unit and component tests).

---

## Repository Structure

```
Corbel2/
├── alembic/                      # Database migrations
│   ├── versions/                 # Versioned migration scripts
│   │   └── 0001_initial_foundation.py
│   └── env.py                    # Alembic migration environment
├── docker/                       # Container definitions
│   ├── backend.Dockerfile        # Python/FastAPI container definition
│   ├── frontend.Dockerfile       # Node.js build + Nginx multi-stage container
│   └── nginx.conf                # Nginx reverse proxy configuration
├── docs/                         # Authoritative architecture documentation
│   ├── ARCHITECTURE.md           # Modular monolith architecture & trust boundaries
│   ├── DECISIONS.md              # Architecture Decision Records (ADR-001 - ADR-020)
│   ├── DOMAIN_MODEL.md           # Conceptual domain models & lifecycle invariants
│   ├── IMPLEMENTATION_PLAN.md    # 14-phase delivery sequence (Phase 0 - 13)
│   └── VISION.md                 # Product positioning & operational context
├── frontend/                     # React + TypeScript single-page application
│   ├── src/
│   │   ├── components/           # UI presentation components
│   │   │   ├── DualModeInfo.tsx  # Dual dev mode documentation card
│   │   │   ├── ErrorBoundary.tsx # React error boundary
│   │   │   ├── Header.tsx        # Top navbar & live connectivity pill
│   │   │   ├── RoadmapPreview.tsx# Phase delivery roadmap
│   │   │   └── StatusCard.tsx    # Live telemetry & DB ping display
│   │   ├── services/             # API client functions
│   │   ├── types/                # Strongly typed API models
│   │   ├── App.tsx               # Root application shell
│   │   ├── App.test.tsx          # Component automated tests
│   │   └── main.tsx              # Entry point
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── src/                          # Backend application source
│   └── corbel/
│       ├── api/                  # API routing layer
│       │   └── v1/
│       │       ├── endpoints/
│       │       │   └── health.py # /api/v1/health & /api/v1/health/live
│       │       └── api.py        # v1 router aggregator
│       ├── core/                 # Shared foundation infrastructure
│       │   ├── config.py         # Centralized settings (pydantic-settings)
│       │   ├── database.py       # Engine, session factory & health check
│       │   ├── exceptions.py     # Centralized exception handlers & ErrorResponse
│       │   ├── logging.py        # Structured JSON logging & correlation IDs
│       │   └── middleware.py     # Correlation ID & request timing middleware
│       └── main.py               # FastAPI application entrypoint
├── tests/                        # Backend automated test suite
│   ├── conftest.py               # Shared fixtures & test client
│   ├── test_config.py            # Settings & URL generation tests
│   ├── test_exceptions.py        # Error response model tests
│   ├── test_health.py            # Health endpoint & database ping tests
│   └── test_middleware.py        # Correlation ID tracing tests
├── .env.example                  # Environment configuration template
├── alembic.ini                   # Alembic migration configuration
├── docker-compose.yml            # Full containerized stack & isolated DB service
├── pyproject.toml                # Python package configuration
└── AGENTS.md                     # AI agent operational rules & standards
```

---

## Dual Development Environments

Corbel enforces two verified local development workflows:

### Mode A — Lightweight Local Development (Primary Everyday Mode)
- **PostgreSQL** runs in Docker on port `5432`.
- **FastAPI backend** runs natively on the host with hot reload on port `8000`.
- **React/Vite frontend** runs natively on the host with HMR on port `5173`.

#### Mode A Startup Commands:
```bash
# 1. Start PostgreSQL database container
docker compose up -d corbel-db

# 2. Run database migrations natively
alembic upgrade head

# 3. Start FastAPI backend (with reload)
uvicorn corbel.main:app --reload --host 127.0.0.1 --port 8000

# 4. Start React frontend (in frontend/ directory)
cd frontend
npm run dev
```

#### Mode A Shutdown:
```bash
# Stop PostgreSQL container
docker compose stop corbel-db
```

---

### Mode B — Full Containerized Integration Mode (CI / Pre-Merge)
- **PostgreSQL**, **FastAPI backend**, and **React/Nginx frontend** all build and run in Docker Compose on a shared network.
- Migrations run automatically on backend startup.
- Nginx proxies `/api/` calls directly to the backend.

#### Mode B Startup Commands:
```bash
# Build and start all three services in background
docker compose up --build -d

# View live logs
docker compose logs -f

# Check container status
docker compose ps
```

#### Mode B Access Points:
- Frontend UI: `http://localhost:5173`
- Backend API Docs: `http://localhost:8000/docs`
- Health Endpoint: `http://localhost:8000/api/v1/health` (or via frontend proxy: `http://localhost:5173/api/v1/health`)

#### Mode B Shutdown:
```bash
# Stop and remove containers and network
docker compose down

# To clean volume data as well:
docker compose down -v
```

---

## Running Automated Tests

### Backend Tests (pytest)
```bash
# Run complete test suite
pytest -v

# Run with coverage
pytest --cov=corbel tests/
```

### Frontend Tests (Vitest)
```bash
cd frontend

# Run single pass
npm run test

# Run interactive watch mode
npm run test:watch

# Verify production build compilation
npm run build
```
