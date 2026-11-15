# Corbel — AI Agent Guidelines & Engineering Standards

> [!IMPORTANT]
> **MANDATORY INSTRUCTION FOR ALL AI CODING AGENTS:**
> You are operating on the **Corbel** codebase. Before creating, modifying, or refactoring any code or configuration, you **MUST** read this document in its entirety, inspect existing workspace files, and review the relevant documentation in `docs/`. Never guess architectural intent or introduce unapproved technologies.

---

## 1. Product Vision & Operational Context

**Corbel** is an Enterprise AI and Operational Intelligence Platform.
Its core mission:
> **Discover business context. Understand operations. Build intelligent solutions. Learn from failures. Execute with human approval.**

Corbel connects enterprise data, discovers business context, understands operational processes, identifies exceptions and recurring failures, investigates their causes, quantifies their impact, and recommends governed business actions.

Corbel operates in two complementary modes:
- **Governed Intelligence:** Explicit ontology, deterministic rules, multi-party approvals, immutable audit logs.
- **Adaptive Intelligence:** Semantic discovery, continuous process monitoring, exception investigation, AI-generated recommendations with mandatory human approval gates.

Corbel is **NOT** a generic chatbot, not a generic multi-agent framework, and not an ERP replacement.

### The Initial Reference Vertical Slice: Procure-to-Pay (P2P)
To validate the platform end-to-end without building speculative horizontal layers, Corbel standardizes on **Procure-to-Pay (P2P)** as its first reference demonstration:
- Ingesting supplier, purchase order, delivery receipt, and invoice datasets.
- Profiling schemas and inferring candidate business entities.
- Reconstructing process event variants (PO → Goods Receipt → Invoice → 3-Way Match → Payment).
- Detecting price variances and delivery delays deterministically.
- Investigating root causes using AI while strictly separating **verified transactional facts** from **causal hypotheses**.
- Calculating financial impact deterministically and requiring human approval before action execution.

---

## 2. Authoritative Technology Stack

You must adhere strictly to the authoritative technology stack. Do not introduce alternatives without explicit user sign-off recorded in `docs/DECISIONS.md`.

- **Frontend:** React (latest stable), TypeScript (`strict: true`), Vite, Tailwind CSS / clean component library.
- **Backend:** Python 3.11+, FastAPI, Pydantic v2 (for all validation, request/response models, and tool schemas).
- **Database:** PostgreSQL (16+). `pgvector` is **deferred** until a concrete retrieval requirement exists.
- **Infrastructure & Local Dev Modes:**
  - **Default Lightweight Mode:** PostgreSQL running in Docker; FastAPI backend and React/Vite frontend running natively on the Windows host.
  - **Full Containerized Mode:** PostgreSQL, backend, and frontend running together via Docker Compose (`docker-compose.yml`) for integration testing and CI.
- **Testing:** `pytest` (backend unit and integration tests), `Vitest` (frontend unit and component tests).
- **Linting & Formatting:** `ruff` and `mypy` for Python; `eslint` and `prettier` for TypeScript.
- **AI Tooling & Orchestration:**
  - Python-first, provider-neutral model gateway targeting **hosted AI APIs** (Anthropic Claude, OpenAI GPT-4o).
  - Bounded, task-specific execution state machines (no unconstrained ReAct loops).
  - **Local inference is deferred:** Hosted AI APIs (Anthropic Claude, OpenAI GPT-4o) serve as the authoritative initial inference deployment strategy; local model fallback is an optional future capability, not an initial requirement.
  - **Arize Phoenix** is an optional, independent AI telemetry sink in Phase 10; Corbel maintains its own primary audit store in PostgreSQL and must function 100% if Phoenix is offline.

### Explicitly Deferred or Prohibited Technologies
- **ASP.NET Core is DEFERRED:** Do NOT introduce C# or ASP.NET Core into the backend. Python is the authoritative backend.
- **No Premature Distributed Infrastructure:** Do NOT introduce Redis, Kafka, RabbitMQ, Celery, Kubernetes, microservices, or dedicated graph databases (Neo4j) unless a concrete, verified requirement is documented and approved in `docs/DECISIONS.md`.
- **Relational-First Ontology:** Use PostgreSQL relational tables + JSONB for ontologies, not a standalone graph database.
- **No Mandatory Vector Databases:** Do NOT add pgvector extensions or vector stores prematurely.

---

## 3. Documentation Hierarchy & Source of Truth

When seeking context, consult the documentation in this strict order:
1. `AGENTS.md` (This file): Operational rules, engineering standards, and prohibitions.
2. `docs/DECISIONS.md`: Authoritative Architecture Decision Records (ADRs).
3. `docs/ARCHITECTURE.md`: High-level system structure, modular boundaries, data flows, and trust layers.
4. `docs/VISION.md`: Business context, target personas, and capability scope.
5. `docs/DOMAIN_MODEL.md`: Conceptual entities, attributes, relationships, and lifecycle invariants.
6. `docs/IMPLEMENTATION_PLAN.md`: Phase sequence, milestones, acceptance criteria, and explicit exclusions.

### Requirement to Maintain Documentation
If your code changes modify an architectural boundary, introduce a new database table, alter an API contract, or add a configuration variable:
**You MUST update the corresponding documentation in `docs/` in the same commit or turn.**

---

## 4. Engineering Principles & Coding Conventions

### Modular Monolith Discipline
- All backend code lives in `src/corbel/`.
- Domain modules (e.g., `tenancy`, `data_intelligence`, `ontology`, `process_intelligence`, `monitors`, `governance`) must reside in dedicated directories under `src/corbel/domains/`.
- Cross-domain communication must occur through explicit service interfaces, never circular imports or direct cross-module table mutations.

### Python & Backend Standards
- **Strict Typing:** All function signatures must include full type hints (`def process_event(event: ProcessEventCreate) -> ProcessEventResponse:`).
- **Pydantic Everywhere:** Every incoming request, outgoing response, configuration object, and LLM tool parameter must be a validated Pydantic model.
- **Async by Default for I/O:** Use `async def` for FastAPI route handlers and database queries.
- **Exception Handling:** Never use bare `except:`. Catch explicit exceptions and return standardized HTTP error responses with descriptive detail.
- **Database Sessions:** Always use context-managed database sessions; guarantee transactional rollbacks on unhandled errors.

### Frontend & TypeScript Standards
- **Strict TypeScript:** No `any`. Use explicit interfaces, unions, and types matching backend Pydantic models.
- **Component Modularity:** Separate UI presentation components from data-fetching logic (use custom React Query hooks).
- **Error Boundaries:** Wrap major interactive views in React Error Boundaries to prevent whole-app crashes.

### Database & SQL Conventions
- **Explicit Migrations:** Every schema change must be captured in an Alembic migration script. Never use automatic runtime table creation (`Base.metadata.create_all()`) in production code paths.
- **Tenant Isolation:** Every operational query MUST filter by `tenant_id` / `organization_id`. Never execute unbounded `SELECT *` queries.
- **Safety Sandbox:** Queries generated for user analytics must be strictly read-only (`SELECT` only).

---

## 5. Security & Trust Boundaries

1. **Deterministic Authorization (Zero LLM Trust):**
   - **NEVER** use an LLM or prompt to decide if a user is permitted to perform an action.
   - All authorization must be computed deterministically in backend Python code using verified JWT claims and RBAC/ABAC policies.
2. **Untrusted External Data:**
   - Treat all uploaded files (CSV, Excel, JSON), external database records, and webhook payloads as untrusted data.
   - Strictly validate and sanitize file paths, file sizes, and MIME types. Prevent path traversal attacks.
3. **No Hardcoded Secrets:**
   - Never embed API keys, database passwords, or JWT secrets in source code.
   - All secrets must be loaded from environment variables using `pydantic-settings`.
4. **Mandatory Human-in-the-Loop for Consequential Actions:**
   - AI agents may inspect data, hypothesize causes, and recommend actions.
   - AI agents **CANNOT** directly execute mutations, API calls, or state updates without an approved `Approval` record signed off by an authorized human `User`.

---

## 6. AI Systems Engineering Rules

### 6.1. Phased AI Introduction
- **Phase 5 (Early AI Gateway):** Introduce minimal model gateway strictly for natural language query parsing into Pydantic models with basic token logging. No complex agent loops or tool registries.
- **Phase 8 (Complete AI Infrastructure):** Reusable model gateway, bounded state machines, tool registry, prompt lifecycle, granular cost attribution, multi-level caching, and evaluation framework.

### 6.2. Bounded Task-Specific State Machines (No Generic ReAct Loops)
- Never deploy unconstrained ReAct loops that iterate indefinitely.
- Build explicit, bounded state machines for specific tasks:
  - *Data Discovery:* `Inspect` → `Profile` → `Infer` → `Validate` → `Correct if uncertain` → `Save`.
  - *Process Investigation:* `Detect` → `Retrieve` → `Correlate` → `Investigate` → `Verify` → `Explain`.
  - *Rule Generation:* `Observe` → `Identify pattern` → `Propose` → `Test` → `Validate` → `Human approve` → `Activate`.
- **AI Reasoning vs. State Machine Control:** Within an active analytical state, LLMs may dynamically select among permitted read-only investigative steps or sub-queries. However, the deterministic backend state machine strictly enforces legal state transitions, parameter validation via Pydantic schemas, scoped tool permissions, token/cost budgets, configurable timeouts, checkpointing, and termination.
- Every workflow execution must enforce:
  - Maximum iteration limits (e.g., 5-8 steps).
  - Explicit token and dollar budgets.
  - Configurable timeouts tailored to the workflow category (interactive vs. long-running) rather than arbitrary universal limits.
  - Scoped read-only tool permissions.
  - Durable checkpointing for resume-on-failure.
- **Durable Background Execution:** Long-running workflows (profiling, event reconstruction, monitor sweeps, multi-step investigations) must use PostgreSQL-backed durable execution with persisted state, atomic transitions, retries, and idempotency keys. Redis and external message brokers remain deferred.
- **Fact vs. Hypothesis Separation:** Investigations must strictly separate verified database facts from model-generated hypotheses. Hypotheses must never be presented to users as established facts.
- **Zero Self-Granted Permissions:** An AI workflow can never modify its own permissions or bypass human approval gates.

### 6.3. AI Economics & Prompt Governance
- **Prompt Lifecycle:** Prompts are version-controlled assets following `DRAFT` → `TEST` → `EVALUATE` → `APPROVE` → `DEPLOY` → `MONITOR` → `RETIRE` with instant rollback support.
- **Granular Cost Attribution:** Every model call must record Tenant, Project, Use Case, Workflow, Agent, Model, Input/Output/Cached Tokens, Latency, and Task Outcome (enabling **Cost per Successful Task** reporting).
- **Multi-Level Caching:** Provider-native prompt caching is default. Redis exact and semantic caching are **optional and deferred**. Semantic caching must respect tenant isolation, authorization scopes, and data freshness, and may never be used for consequential business actions.

---

## 7. Prohibited Shortcuts & "Don'ts"

- **DO NOT** create placeholder mock implementations that pretend to be complete (e.g., `# TODO: implement real logic later`, returning static fake data where real logic was requested).
- **DO NOT** fabricate test results or claim tests passed when they were not executed.
- **DO NOT** claim unverified ROI percentages without empirical benchmark evidence.
- **DO NOT** install npm or pip packages without verifying their necessity and checking for lighter standard alternatives.
- **DO NOT** skip error handling or input validation to make code shorter.
- **DO NOT** introduce microservices, message queues (Kafka, RabbitMQ), or caches (Redis) without an explicit architectural decision record.
- **DO NOT** alter the 14-phase sequence established in `docs/IMPLEMENTATION_PLAN.md`.

---

## 8. Agent Workflow Protocol

Whenever tasked with an implementation step:
1. **Inspect First:** Check the file tree, read existing implementations, and understand the domain boundaries before editing.
2. **Consult ADRs:** Check `docs/DECISIONS.md` to ensure your approach aligns with established decisions.
3. **Implement Cleanly:** Write typed, modular, documented code adhering to conventions above.
4. **Verify & Test:** Run automated tests, linting, and type checking. Never report success without verification.
5. **Update Docs:** If models, endpoints, or environment variables changed, update the relevant files in `docs/`.
