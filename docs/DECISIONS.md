# Corbel — Architecture Decision Records (ADR)

> [!IMPORTANT]
> **Architectural Decisions vs. Implementation Phasing:**
> This document records established, authoritative architectural decisions for the target Corbel platform. Documenting a decision or design pattern in an ADR does **not** authorize its implementation during Phase 1. All engineering work must strictly follow the authoritative 14-phase sequence (Phase 0 through Phase 13) defined in `docs/IMPLEMENTATION_PLAN.md`. Phase 1 remains strictly restricted to establishing the application foundation (FastAPI, React + TypeScript, PostgreSQL, Alembic, configuration, health checks, logging, foundation tests, and dual local development modes).

---

## Index of Decisions

- [ADR-001: Python + FastAPI as Primary Backend](#adr-001-python--fastapi-as-primary-backend)
- [ADR-002: React + TypeScript as Frontend Architecture & OpenAPI Contract Generation](#adr-002-react--typescript-as-frontend-architecture--openapi-contract-generation)
- [ADR-003: PostgreSQL as Primary Database](#adr-003-postgresql-as-primary-database)
- [ADR-004: Dual Local Development Modes (Lightweight Native & Docker Compose)](#adr-004-dual-local-development-modes-lightweight-native--docker-compose)
- [ADR-005: Modular Monolith Architecture & AI/Domain Service Boundaries](#adr-005-modular-monolith-architecture--aidomain-service-boundaries)
- [ADR-006: Relational Representation for Business Ontology](#adr-006-relational-representation-for-business-ontology)
- [ADR-007: Deferring ASP.NET Core to Future Enterprise Integrations](#adr-007-deferring-aspnet-core-to-future-enterprise-integrations)
- [ADR-008: Deferring pgvector until Concrete Retrieval Requirement](#adr-008-deferring-pgvector-until-concrete-retrieval-requirement)
- [ADR-009: Deterministic Controls for Security, Calculations, and Permissions](#adr-009-deterministic-controls-for-security-calculations-and-permissions)
- [ADR-010: Provider-Neutral Hosted AI Architecture & Deferral of Local Inference](#adr-010-provider-neutral-hosted-ai-architecture--deferral-of-local-inference)
- [ADR-011: Mandatory Human Approval for Consequential Business Actions](#adr-011-mandatory-human-approval-for-consequential-business-actions)
- [ADR-012: Procure-to-Pay (P2P) as Initial Demonstrable Vertical Slice & Simulated Target Adapter](#adr-012-procure-to-pay-p2p-as-initial-demonstrable-vertical-slice--simulated-target-adapter)
- [ADR-013: Phased AI Gateway Timing & Scope (Phase 4/5 Early Gateway vs. Phase 8 Complete Infrastructure)](#adr-013-phased-ai-gateway-timing--scope-phase-45-early-gateway-vs-phase-8-complete-infrastructure)
- [ADR-014: Task-Specific Bounded State Machines, Durable Task Lifecycle & Cancellation](#adr-014-task-specific-bounded-state-machines-durable-task-lifecycle--cancellation)
- [ADR-015: AI Economics, Prompt Lifecycle Governance & Multi-Tier Caching](#adr-015-ai-economics-prompt-lifecycle-governance--multi-tier-caching)
- [ADR-016: Optional & Independent Arize Phoenix AI Observability Platform](#adr-016-optional--independent-arize-phoenix-ai-observability-platform)
- [ADR-017: PostgreSQL-Backed Durable Background Execution for Long-Running Workflows](#adr-017-postgresql-backed-durable-background-execution-for-long-running-workflows)
- [ADR-018: Alembic for Database Schema Migrations](#adr-018-alembic-for-database-schema-migrations)
- [ADR-019: Multi-Layered AI Security, Prompt Injection Defense & Untrusted Content Handling](#adr-019-multi-layered-ai-security-prompt-injection-defense--untrusted-content-handling)
- [ADR-020: Append-Only Audit Records and Audit Log Integrity](#adr-020-append-only-audit-records-and-audit-log-integrity)
- [ADR-021: Use-Case Architect Bounded Discovery, Structured Specifications & Governance](#adr-021-use-case-architect-bounded-discovery-structured-specifications--governance)
- [Architectural Backlog & Open Questions](#architectural-backlog--open-questions)

---

### ADR-001: Python + FastAPI as Primary Backend
- **Status:** Accepted
- **Context:** An enterprise AI and operational intelligence platform requires robust data processing, native integration with machine learning/AI tooling, asynchronous API handling, and strict input/output contract enforcement.
- **Decision:** Build the primary backend using **Python 3.11+** and **FastAPI**, leveraging **Pydantic v2** for data modeling, validation, and serialization.
- **Reason:** Python is the native ecosystem for AI orchestration, context manipulation, process mining libraries, and data science tooling. FastAPI provides high-performance asynchronous request handling, native OpenAPI documentation generation, and seamless integration with Pydantic schemas.
- **Consequences:**
  - *Positive:* Unified ecosystem for both standard REST endpoints and AI workflows; strong runtime typing and validation via Pydantic; rapid development velocity.
  - *Negative:* Python's asynchronous I/O (`async`/`await`) handles concurrent network and database I/O efficiently, but does not eliminate CPU-bound execution constraints imposed by the Python Global Interpreter Lock (GIL). For compute-intensive workloads (such as heavy process mining graph reconstructions or large-scale data profiling), separate worker processes, process pools (`ProcessPoolExecutor`), or dedicated background execution workers must be utilized to prevent event-loop starvation.
  - *Neutral:* Requires adherence to modern Python async/await patterns and strict linting/type-checking (ruff, mypy).

---

### ADR-002: React + TypeScript as Frontend Architecture & OpenAPI Contract Generation
- **Status:** Accepted
- **Context:** The platform requires an interactive, component-driven user interface capable of rendering complex visualizations (ontology graphs, process mining flows, approval queues, and dynamic low-code mini-applications).
- **Decision:** Use **React** with **TypeScript** in strict mode (`strict: true`) as the web frontend foundation. Establish **OpenAPI-generated TypeScript API contracts** (via automated code generation from FastAPI's OpenAPI JSON specification) as the preferred approach for client-server communication.
- **Reason:** React possesses the most mature component ecosystem, battle-tested visualization libraries, and extensive community support. While TypeScript provides client-side compile-time type safety, it does not automatically synchronize frontend types with backend Pydantic models across the network. Generating TypeScript client contracts directly from the backend OpenAPI schema guarantees contract parity and prevents silent drift.
- **Consequences:**
  - *Positive:* High frontend reliability, reusable component architecture, automated compile-time synchronization between frontend and backend models.
  - *Negative:* Requires an automated codegen step in the frontend build pipeline; build step overhead (Vite/Node tooling).
  - *Neutral:* Standard modern enterprise SPA pattern.

---

### ADR-003: PostgreSQL as Primary Database
- **Status:** Accepted
- **Context:** Corbel manages multi-tenant accounts, relational business ontologies, operational process event logs, audit records, and state machine transitions that demand ACID consistency, referential integrity, and robust JSON querying.
- **Decision:** Use **PostgreSQL** as the unified primary database. Avoid treating a specific major version as a permanent architectural invariant; pin the supported version in implementation configurations (e.g., Dockerfiles, Compose manifests, and environment specifications).
- **Reason:** PostgreSQL is the gold standard for relational reliability, supports complex multi-table joins, provides high-performance JSONB indexing for semi-structured payloads, has mature connection pooling, and offers rich future extensibility (e.g., pgvector).
- **Consequences:**
  - *Positive:* Single reliable data store for all metadata, audit trails, and transactional records; eliminates distributed multi-database synchronization overhead.
  - *Negative:* Scaling write-heavy event logs requires careful indexing and partition management at high volumes.
  - *Neutral:* Standard SQL tooling and migrations (Alembic) apply universally.

---

### ADR-004: Dual Local Development Modes (Lightweight Native & Docker Compose)
- **Status:** Accepted
- **Context:** Forcing developers to run all services (PostgreSQL, FastAPI backend, React frontend) inside Docker containers during daily coding adds significant overhead (container rebuild lag, debugger attachment complexity, slow file watchers on Windows). Conversely, running everything bare-metal without containerization causes environment drift.
- **Decision:** Support **two distinct development modes**:
  1. **Default Lightweight Mode:** Run PostgreSQL in a Docker container; run FastAPI and React/Vite natively on the host workstation configured via `.env`.
  2. **Full Containerized Mode:** Run all three services via `docker-compose.yml` for clean integration testing and CI environments.
- **Reason:** Provides the fastest inner-loop development experience while achieving environment reproducibility through pinned package dependencies (lockfiles), pinned container base images, and centralized `.env` configuration.
- **Consequences:**
  - *Positive:* Instant hot-reload and native IDE debugging for backend and frontend; zero container rebuild delays during feature coding; predictable integration testing via Compose.
  - *Negative:* Developers must install Python 3.11 and Node.js locally alongside Docker Desktop for lightweight mode.
  - *Neutral:* Both modes share identical `.env` configuration conventions.

---

### ADR-005: Modular Monolith Architecture & AI/Domain Service Boundaries
- **Status:** Accepted
- **Context:** Early-stage enterprise systems often suffer catastrophic architectural failures when prematurely decomposed into microservices (network latency, distributed transaction failures, deployment complexity). Furthermore, integrating AI workflows without strict boundaries risks allowing probabilistic models to compromise domain business logic and database persistence.
- **Decision:** Build Corbel as a cohesive **Modular Monolith** within a single backend application codebase. Enforce domain boundaries through explicit internal Python service interfaces, package-level encapsulation, and automated architecture tests (e.g., import-linter). 
  
  Establish an explicit, one-directional interaction model governing Domain Application Services and AI Infrastructure:

  ```text
  Domain Application Service
            |
            v
  Approved AI Workflow
            |
            v
  Structured, Validated Result
            |
            v
  Domain Application Service
            |
            v
  Deterministic Policy Validation
            |
            v
  Human Approval (when required)
            |
            v
  Domain Persistence or Execution
  ```

- **Domain vs. AI Boundary Invariants:**
  1. *Service-Initiated Invocation:* Domain application services (e.g., `InvestigationService`, `MonitorService`) determine when an AI workflow is required and invoke it via an explicit interface.
  2. *Scoped Context & Permitted Tools:* AI workflows receive strictly scoped context and an explicitly restricted set of permitted tools passed by the domain service.
  3. *Pydantic-Validated Outputs:* AI workflows return structured results validated against strict Pydantic schemas.
  4. *Domain Ownership of Business Logic & State:* Domain application services validate and process returned results against business rules. Domain services retain exclusive ownership of business logic, domain entities, and database persistence.
  5. *Zero Direct Persistence by AI:* AI infrastructure and models cannot directly mutate domain database records or manage database transactions.
  6. *Zero Privilege Escalation:* AI workflows cannot grant themselves permissions, alter tool allowlists, or bypass authorization, policy enforcement, or human approval requirements.
  7. *No Unnecessary Microservices:* This boundary is implemented strictly within the modular monolith; no new service or microservice is introduced to govern it.
- **Reason:** Balances the productivity and transactional consistency of an in-process modular monolith with strict encapsulation, ensuring probabilistic AI reasoning never corrupts deterministic business domain state.
- **Consequences:**
  - *Positive:* Simplified deployment; transactional consistency; in-process execution speed; clean architectural isolation between business logic and AI reasoning.
  - *Negative:* Requires strict dependency discipline and linting to prevent cross-domain coupling.
  - *Neutral:* Domain services reside in `src/corbel/domains/`; AI workflows reside in `src/corbel/ai/`.

---

### ADR-006: Relational Representation for Business Ontology
- **Status:** Accepted
- **Context:** Business ontologies define objects, properties, and relationships. Teams frequently jump to dedicated graph databases (e.g., Neo4j) to represent ontologies, incurring significant infrastructure complexity.
- **Decision:** Represent business objects, properties, and relationships using a **relational schema in PostgreSQL**, supplemented with JSONB for flexible property definitions.
- **Reason:** In early and mid-stage enterprise deployments, the volume of ontology metadata is easily handled by relational joins and recursive Common Table Expressions (CTEs). PostgreSQL JSONB provides schema flexibility without managing a second database engine.
- **Consequences:**
  - *Positive:* No secondary graph database to deploy, back up, secure, or synchronize; transactional consistency between ontology definitions and application state.
  - *Negative:* Extremely deep multi-hop graph traversals (>10 hops) may be slower than native graph engines, though rarely required for operational business objects.
  - *Neutral:* Can evaluate dedicated graph storage in Phase 13 if enterprise scale demands it.

---

### ADR-007: Deferring ASP.NET Core to Future Enterprise Integrations
- **Status:** Deferred
- **Context:** Earlier discussions or specification notes contemplated ASP.NET Core. However, the authoritative decision establishes Python as the primary backend language for Corbel.
- **Decision:** **Explicitly defer ASP.NET Core**. It is not part of the initial backend or platform architecture.
- **Reason:** Maintaining dual backend stacks (Python + .NET) in early phases doubles architectural surface area, splits engineering effort, and adds zero value to core operational intelligence and AI capabilities. ASP.NET Core may only be revisited in later phases as an optional external integration adapter if an enterprise customer requires native Windows/Active Directory or specialized Microsoft COM/Dynamics connectivity.
- **Consequences:**
  - *Positive:* Unified Python-first engineering velocity; reduced cognitive load; coherent single-process backend.
  - *Negative:* None for core product delivery.
  - *Neutral:* Documented as deferred rather than silently erased.

---

### ADR-008: Deferring pgvector until Concrete Retrieval Requirement
- **Status:** Deferred
- **Context:** Many modern AI architectures install vector databases or vector extensions immediately, even before semantic search or RAG use cases exist, creating unused database extension overhead.
- **Decision:** **Defer `pgvector`** installation and schema usage until a concrete retrieval requirement (such as unstructured document chunk retrieval or semantic finding clustering) is actively implemented.
- **Reason:** Structured querying, ontology mapping, process mining, and rule-based monitoring do not require vector similarity search. Introducing vector dependencies prematurely complicates migrations and local Docker setup without delivering immediate value.
- **Consequences:**
  - *Positive:* Lean database initialization; faster migrations; lower container resource footprint.
  - *Negative:* None; PostgreSQL supports adding `CREATE EXTENSION vector;` whenever the concrete need arises in Phase 8/9.
  - *Neutral:* Clear milestone for introduction established.

---

### ADR-009: Deterministic Controls for Security, Calculations, and Permissions
- **Status:** Accepted
- **Context:** Generative AI models are probabilistic and prone to hallucination, prompt injection, and nondeterministic reasoning. Entrusting security, authorization, or mathematical calculations to an LLM creates catastrophic enterprise risk.
- **Decision:** All permissions (RBAC/ABAC), financial calculations, metric aggregations, policy validations, and execution gates must be written in **deterministic code (Python / SQL)**.
- **Reason:** Enterprise governance demands reproducible, auditable, and mathematically sound operations. While deterministic backend authorization does not stop prompt injection at the LLM reasoning level, it guarantees that model-generated text or injected instructions cannot grant permissions, bypass authorization filters, or execute unauthorized mutations. Consequential operations are strictly validated and authorized by deterministic backend policy enforcers.
- **Consequences:**
  - *Positive:* Prevents privilege escalation via prompt injection; guaranteed mathematical accuracy; audit compliance defensibility.
  - *Negative:* Requires strict validation schemas and policy rules in code rather than relying on natural language prompts.
  - *Neutral:* Foundation of Corbel's Governed Intelligence mode.

---

### ADR-010: Provider-Neutral Hosted AI Architecture & Deferral of Local Inference
- **Status:** Accepted
- **Context:** Tightly coupling an enterprise application to a single proprietary LLM provider creates vendor lock-in. Conversely, requiring local model inference adds heavy operational dependencies and specialized hardware prerequisites for early-stage development and deployment.
- **Decision:** Implement a **Provider-Neutral Model Gateway** targeting hosted AI APIs (e.g., Anthropic Claude, OpenAI GPT-4o). **Defer local model fallback** (e.g., Ollama, vLLM) as an optional future capability.
- **Reason:** Hosted APIs provide reliable high-tier reasoning, structured outputs, and tool calling without local infrastructure complexity. The abstract gateway architecture guarantees that local inference can be added in the future through dedicated adapters without refactoring core domain logic, though adapter implementation, testing, and hardware configuration will be required at that time.
- **Consequences:**
  - *Positive:* Unblocks high-quality AI features on standard workstations; eliminates local GPU setup friction; provider-agnostic code contracts.
  - *Negative:* Development and testing of AI features require network connectivity and hosted API keys.
  - *Neutral:* Centralized configuration in `src/corbel/ai/gateway/`.

---

### ADR-011: Mandatory Human Approval for Consequential Business Actions
- **Status:** Accepted
- **Context:** Fully autonomous AI agents that mutate production enterprise systems (e.g., executing vendor payments, modifying customer credit limits, canceling purchase orders) introduce unacceptable operational blast radius.
- **Decision:** Every **consequential business action** recommended by an AI investigation requires **explicit, authenticated human approval** through a dedicated approval gate before execution. Read-only analytical queries and non-consequential operations (such as drafting summaries or profiling data) do not require approval gates. Backend risk classification and policy enforcement are authoritative in determining whether an action requires human approval.
- **Reason:** Balances the speed of automated investigation with enterprise risk mitigation. Prevents erroneous or hallucinated action payloads from mutating external systems of record while avoiding approval fatigue on safe, read-only analytical operations.
- **Consequences:**
  - *Positive:* Enterprise trust; full accountability; defensible compliance; provides human feedback loops that improve future AI recommendations.
  - *Negative:* Requires human operator availability to complete consequential workflows; introduces latency into final execution.
  - *Neutral:* Core differentiator of Corbel over unconstrained autonomous agent toys.

---

### ADR-012: Procure-to-Pay (P2P) as Initial Demonstrable Vertical Slice & Simulated Target Adapter
- **Status:** Accepted
- **Context:** Building broad horizontal layers without validating them on a concrete business domain leads to abstract, unverified code. Furthermore, executing actions against live enterprise production systems during initial validation creates unacceptable operational risk.
- **Decision:** Standardize on **Procure-to-Pay (P2P)** as the initial reference use case for validating the platform from Phase 3 through Phase 9. For initial demonstration and validation, all governed actions must execute through a **Simulated Target-System Adapter**, **never** against real live ERP, financial, or production systems.

  The initial governed execution lifecycle is strictly defined as:

  ```text
  AI Investigation
         |
         v
  Deterministic Impact Calculation
         |
         v
  Structured Recommendation
         |
         v
  Authenticated Human Approval
         |
         v
  Simulated Target-System Adapter
         |
         v
  Execution Result
         |
         v
  Audit Record
  ```

- **Requirements for the Simulated P2P Demonstration:**
  1. *Synthetic P2P Datasets:* Ingest synthetic supplier master data, purchase orders, goods delivery receipts, and invoices containing known anomalies (e.g., delivery delays vs. contractual SLAs, invoice price/quantity discrepancies vs. POs).
  2. *Simulated Target Actions:* Implement simulated operations mimicking enterprise systems:
     - *Hold Invoice:* Simulates placing an ERP payment hold flag on a discrepant invoice.
     - *Request Credit Memo:* Simulates dispatching a vendor discrepancy claim.
     - *Flag Supplier for Review:* Simulates placing a procurement review hold on a supplier profile.
  3. *Equivalent Governance Rigor:* The simulated adapter must enforce identical approval workflows, policy checks, parameter schemas, and idempotency validations as a live integration.
  4. *Audit Logging:* Action execution results, status payloads, and simulated target responses must be recorded in the authoritative append-only audit store.
  5. *Abstract Adapter Interface:* The adapter must implement an abstract `TargetSystemAdapter` interface, ensuring production ERP/API connectors (SAP, NetSuite, Dynamics) can be plugged in during later phases without altering the core governed execution workflow.
  6. *No Real ERP Mutations in Initial Demonstration:* Live external mutations remain explicitly prohibited during Phase 9 validation.
- **Reason:** Provides a concrete, risk-free enterprise benchmark exercising every layer of the platform—from data intelligence to human approval and controlled dispatch—without threatening live operational systems.
- **Consequences:**
  - *Positive:* Complete end-to-end verification of platform governance and UI workflows; zero production blast radius; clear contract for future production adapters.
  - *Negative:* Requires maintaining synthetic P2P datasets and mock adapter responses.
  - *Neutral:* Extensible to other domains (e.g., Order-to-Cash) in Phase 13.

---

### ADR-013: Phased AI Gateway Timing & Scope (Phase 4/5 Early Gateway vs. Phase 8 Complete Infrastructure)
- **Status:** Accepted
- **Context:** Natural language querying (Phase 5) requires LLM query compilation, and semantic ontology discovery (Phase 4) may optionally utilize LLMs for candidate entity inference. However, implementing the full agent framework prematurely creates complex circular dependencies.
- **Decision:** Introduce the **Early Model Gateway** strictly when the first LLM-dependent capability requires it:
  - *Phase 4 (Ontology Discovery):* By default, Phase 4 utilizes deterministic schema profiling and foreign-key heuristics for candidate entity discovery. If semantic terminology mapping or LLM-assisted relationship inference is enabled, it consumes the minimal Early AI Gateway.
  - *Phase 5 (Structured Querying):* The Early AI Gateway is mandatory for compiling natural language business questions into structured, validated Pydantic query ASTs.
  - *Phase 8 (Complete AI Infrastructure):* Delivers the comprehensive enterprise AI engineering suite: bounded state machines, tool registry, prompt lifecycle governance, granular cost attribution, multi-level caching, and evaluation framework.
- **Reason:** Avoids premature introduction of complex agent state machines, tool registries, or multi-agent loops before basic model communication and structured output validation are solid.
- **Consequences:**
  - *Positive:* Resolves the roadmap dependency deadlock cleanly; enables rapid progress on structured querying without building full agent infrastructure early.
  - *Negative:* Early gateway will be refactored/expanded when Phase 8 is reached.
  - *Neutral:* Core Pydantic validation patterns remain consistent across both phases.

---

### ADR-014: Task-Specific Bounded State Machines, Durable Task Lifecycle & Cancellation
- **Status:** Accepted
- **Context:** Generic, unconstrained ReAct agent loops can spin out of control, loop indefinitely, call inappropriate tools, or produce nondeterministic execution traces that are unacceptable in enterprise operational workflows. Furthermore, in long-running enterprise workflows, in-memory AI reasoning states must be cleanly decoupled from durable task execution and cancellation management.
- **Decision:** Architect all AI agent workflows as **task-specific, finite state machines** with deterministic transition rules, hard iteration caps, configurable timeouts, scoped tool permissions, and worker supervision.

  Explicitly distinguish between:
  - **AI Workflow State:** In-memory analytical reasoning transitions (e.g., `Inspect` → `Retrieve` → `Investigate` → `Verify` → `Explain`).
  - **Durable Background Task Execution State:** Persisted job status, worker leases, checkpoints, and execution lifecycle managed in PostgreSQL.

  Durable background tasks adhere to the following explicit state lifecycle:

  ```text
  PENDING
     |
     v
  RUNNING
     |
     +------> COMPLETED
     |
     +------> FAILED
     |
     +------> CANCELLED
  ```

- **Cancellation & Graceful Shutdown Rules:**
  1. *Persisted Cancellation Requests:* Task cancellation is an explicit, persisted state request, not an uncontrolled process kill or unhandled exception.
  2. *Checkpoint Boundary Checks:* Worker loops check for cancellation requests at safe execution boundaries (between state machine steps or sub-task checkpoints).
  3. *Clean Halting:* When cancellation is detected, long-running workflows stop without corrupting persisted state, transition the task to `CANCELLED`, and safely release worker leases.
  4. *Audit Retention:* Completed intermediate operations remain completed, valid, and fully auditable.
  5. *Accurate Status Reporting:* Unfinished tasks are **never** silently marked as completed during worker shutdown or cancellation.
  6. *Supervisor Recovery:* Graceful worker shutdown allows active jobs to reach their next checkpoint or safely release leases so that another worker can recover them.
- **Reason:** Provides bounded, supervised execution with controlled recovery and explicit lifecycle states over both analytical reasoning depth and background task execution, enhancing audit defensibility and operational resilience without claiming that state machines alone prevent every failure mode.
- **Consequences:**
  - *Positive:* Complete task transparency; predictable worker behavior during cancellation and deploys; Reduces the risk of runaway loops and corrupted background jobs through bounded execution, checkpointing, cancellation, and worker supervision.
  - *Negative:* Requires explicit checkpointing logic in task handlers and state machines.
  - *Neutral:* Closely coupled with ADR-017 mechanics.

---

### ADR-015: AI Economics, Prompt Lifecycle Governance & Multi-Tier Caching
- **Status:** Accepted
- **Context:** Enterprise AI deployments require strict cost accounting, reproducible prompts, and latency optimization without leaking tenant data or serving stale information for consequential business decisions.
- **Decision:** Implement a comprehensive AI economics and governance framework:
  1. **Prompt Management & Lifecycle:** Assign globally unique `prompt_id`s and immutable semantic version tags. Enforce formal lifecycle stages (`DRAFT` → `TEST` → `EVALUATE` → `APPROVE` → `DEPLOY` → `MONITOR` → `RETIRE`). Supports rollback by restoring the active deployment reference to a previously approved immutable prompt version. Existing prompt versions are never modified in place.
  2. **Evaluation & Regression Framework:** Maintain versioned evaluation datasets to run automated regression tests measuring structured-output schema compliance, retrieval quality, grounding, tool selection/execution accuracy, and business correctness.
  3. **Granular Cost Attribution:** Record input tokens, output tokens, cached input tokens, execution latency, and task outcome (`SUCCESS`, `FAILURE`, `ESCALATED`) per invocation, attributed across Tenant, Project, Use Case, Workflow, Agent, Model, Prompt Version, and Execution ID. Calculate and report **Cost per Successful Task**.
  4. **Multi-Tier Caching Architecture:**
     - *Level 1 (Provider-Native Prompt Caching):* Leveraged where supported by the underlying model provider and where prompt structure (static system instructions, repeated ontology schemas) makes it computationally and economically beneficial.
     - *Level 2 (Redis Exact-Response Caching):* Optional and deferred until high-volume identical queries justify external cache infrastructure.
     - *Level 3 (Redis Semantic Caching):* Optional and deferred until a measured analytical use case justifies it.
  5. **Caching Governance Invariants:**
     - Incorporate version hashes of underlying schemas, business rules, prompt versions, and policy revisions into cache keys.
     - Enforce tenant isolation and user authorization checks *before* returning cached content.
     - Apply explicit TTL and freshness policies with event-driven invalidation hooks on dataset updates.
     - **Never** use cached responses to authorize consequential actions or validate authoritative financial values.
- **Reason:** Gives enterprise finance and compliance leaders transparency into AI spend and operational return on investment while reducing the risk of unauthorized cache data exposure through tenant-aware cache keys, authorization checks before returning cached content, and explicit invalidation and freshness controls.
- **Consequences:**
  - *Positive:* Audit-defensible prompt history; precise budget tracking; reduced risk of unauthorized cache data exposure through tenant isolation, authorization checks, and cache invalidation controls.
  - *Negative:* Additional logging and metadata persistence overhead on each LLM invocation.
  - *Neutral:* Data stored in standard PostgreSQL relational tables.

---

### ADR-016: Optional & Independent Arize Phoenix AI Observability Platform
- **Status:** Accepted
- **Context:** Deep LLM observability (trace spans, prompt debugging, tool execution latency, model evaluation) is valuable for AI engineering, but embedding a third-party observability platform into core application logic creates brittle dependencies and vendor lock-in.
- **Decision:** Support **Arize Phoenix as an optional, independently deployable AI observability, debugging, and evaluation platform in Phase 10**. Corbel maintains its own authoritative operational audit and cost attribution store in PostgreSQL; Phoenix serves purely as an external platform for LLM traces, spans, and model evaluations.
- **Reason:** Phoenix is complementary to Corbel's business process intelligence. Corbel must maintain full operational capability and business audit functionality independently even if Phoenix is offline, uninstalled, or disabled.
- **Consequences:**
  - *Positive:* Clean architectural separation; zero hard runtime dependencies; rich trace debugging and evaluation UI when enabled.
  - *Negative:* Requires mapping Corbel internal execution traces to OpenTelemetry/Phoenix span formats.
  - *Neutral:* Phoenix is not required in the baseline local development environment.

---

### ADR-017: PostgreSQL-Backed Durable Background Execution for Long-Running Workflows
- **Status:** Accepted
- **Context:** Operational intelligence workflows (data profiling, process mining event log reconstruction, continuous monitor sweeps, multi-step investigations) are inherently long-running and cannot run as ephemeral in-memory background threads. Introducing external distributed brokers (Kafka, RabbitMQ, Celery) or Redis prematurely adds significant operational complexity without demonstrated early-stage need.
- **Decision:** Implement **durable background workflow execution backed directly by PostgreSQL**, maintained strictly within the modular monolith and the same Python codebase (running in-process or as dedicated background worker processes, without introducing external microservices). Explicitly defer external message brokers (Kafka, RabbitMQ, Celery) and Redis.

  External queueing and message broker infrastructure should only be evaluated when measured throughput, database contention, latency requirements, multi-region worker distribution, or operational scale empirically justify it.

- **Requirements & Implementation Mechanics:**
  1. *Safe Concurrent Task Claiming:* Use PostgreSQL transactions and `SELECT ... FOR UPDATE SKIP LOCKED` to support safe concurrent task claiming by preventing multiple workers from claiming the same available task during the same claim cycle. It does not globally guarantee exactly-once execution across system failures; reliable execution and recovery depend on time-bounded worker leases, heartbeat monitoring, lease ownership validation, checkpoint recovery, idempotent operations, and bounded retries to handle worker crashes, stale workers, and ambiguous external outcomes.
  2. *Worker Leases & Heartbeat Monitoring:* Active workers claim jobs with time-bounded leases and maintain periodic heartbeats. Stale leases from crashed or abandoned workers expire automatically, allowing tasks to be safely reclaimed.
  3. *Checkpointing & Resumption:* Workflows persist intermediate state and step checkpoints. Recovered jobs resume from the last successfully persisted checkpoint rather than restarting from the beginning.
  4. **Idempotency Keys:** Logical task operations and external action dispatches must use persisted idempotency keys. Retries of the same logical operation reuse the original key. A new key is generated only for a genuinely new logical operation. Individual dispatch attempts may be tracked separately.
  5. *External Operation Safety (No Transactional Guarantees on Network Calls):* PostgreSQL transactions do **not** guarantee exactly-once execution of external network or API calls. External operations must use target-system idempotency support where available and status reconciliation or compensating mechanisms where necessary.
  6. *Bounded Retries & Error Classification:* Distinguish transient, retryable failures (database connection blips, external rate limits) with exponential backoff from permanent failures (schema validation errors, rule violations). Permanent failures transition immediately to an explicit terminal `FAILED` or dead-letter state.
  7. *Cancellation & Graceful Shutdown:* Tasks support cancellation requests, checked at safe execution boundaries. Long-running tasks transition to an explicit `CANCELLED` state and release leases cleanly. Worker shutdown (`SIGTERM`/`SIGINT`) stops accepting jobs, allows active jobs to reach safe checkpoints, and **never** silently marks unfinished tasks as completed.
  8. *Implementation Evaluation in Phase 3:* Mechanism evaluation (e.g., custom PostgreSQL task state table with polling/`LISTEN/NOTIFY` vs. lightweight Python async task runners) will occur in Phase 3, without implying the complete multi-step investigation task engine is built before Phase 7–9.
- **Reason:** PostgreSQL provides ACID transaction guarantees, crash resilience, and atomic state transitions without introducing secondary distributed queue infrastructure.
- **Consequences:**
  - *Positive:* Zero additional infrastructure; resilient execution across process restarts; unified relational debugging and auditing.
  - *Negative:* Workers must poll or use PostgreSQL `LISTEN/NOTIFY` for task dispatch; high database write volumes for high-frequency task updates.
  - *Neutral:* Implementation strategy evaluated in Phase 3.

---

### ADR-018: Alembic for Database Schema Migrations
- **Status:** Accepted
- **Context:** As Corbel evolves across its 14 implementation phases, relational schemas in PostgreSQL must change in a predictable, auditable, and reversible manner. Runtime automatic schema generation (`Base.metadata.create_all()`) is unacceptable in production environments as it cannot handle column alterations, data migrations, or rollbacks.
- **Decision:** Standardize on **Alembic** as the authoritative database migration framework for PostgreSQL.
- **Requirements:**
  1. All DDL changes must be captured in version-controlled migration scripts stored in `alembic/versions/`.
  2. Autogenerated migrations (`alembic revision --autogenerate`) must undergo mandatory manual engineering review prior to merging.
  3. Schema migrations must be tested bidirectionally (upgrade and downgrade) in CI pipelines.
  4. Migration scripts must define explicit rollback and disaster recovery procedures.
  5. Automatic runtime table creation is strictly prohibited in production and staging code paths.
- **Reason:** Provides transparent, repeatable schema evolution, prevents data loss, and ensures strict parity across development, testing, and production databases.
- **Consequences:**
  - *Positive:* Full schema history in version control; safe, testable migrations; zero uncontrolled production schema drift.
  - *Negative:* Developers must generate and review migration files for every domain model change.
  - *Neutral:* Standard industry practice for Python/SQLAlchemy projects.

---

### ADR-019: Multi-Layered AI Security, Prompt Injection Defense & Untrusted Content Handling
- **Status:** Accepted
- **Context:** Integrating LLMs into enterprise operational intelligence exposes systems to indirect prompt injection from untrusted external business data (e.g., invoices, emails, customer notes), tool execution abuse, and unauthorized data leakage across tenant boundaries.
- **Decision:** Enforce a **multi-layered, deterministic security model** for all AI interactions:
  1. **Untrusted Content Demarcation:** Treat all imported files (CSV, Excel, JSON), external database records, and webhook payloads as untrusted data. Clearly demarcate system instructions from untrusted data payloads using structured formatting to mitigate indirect prompt injection.
  2. **Scoped Tool Allowlists:** Tools are strictly whitelisted per state machine phase. Investigation agents are restricted to read-only analytical tools with typed Pydantic parameter schemas; malformed tool inputs are rejected before execution.
  3. **Server-Side Authorization & Tenant Isolation:** Never trust an LLM to enforce access control. All queries and tool executions enforce tenant isolation (using `organization_id` as the primary tenant boundary and `project_id` as workspace scope) and RBAC/ABAC deterministically in Python/SQL.
  4. **Structured Output Validation:** All LLM outputs must be parsed into validated Pydantic models. Unstructured free-form text is never evaluated directly as code or SQL queries.
  5. **Secret & PII Redaction:** System prompts and tool inputs must redact sensitive credentials, tokens, and unnecessary personal data prior to external model transmission.
  6. **Network Egress Restrictions:** The model gateway restricts external outbound requests strictly to configured model provider endpoints.
  7. **Deterministic Execution Limits:** Enforce maximum step counts, token budgets, and configurable timeouts to prevent resource exhaustion attacks.
  8. **Mandatory Human Approval Gate:** AI agents cannot execute consequential mutations directly; all external mutations require signed-off human approvals.
- **Reason:** Generative models are inherently non-deterministic. A defense-in-depth security model ensures that even if an LLM is deceived by an adversarial prompt injection in untrusted business data, the deterministic backend prevents privilege escalation, cross-tenant data access, and unauthorized mutations.
- **Consequences:**
  - *Positive:* Enterprise-grade defense against prompt injection, data exfiltration, and unauthorized actions; auditable security posture.
  - *Negative:* Additional sanitization, parameter validation, and redaction logic required in AI pipelines.
  - *Neutral:* Implemented within the AI gateway and domain service boundary.

---

### ADR-020: Append-Only Audit Records and Audit Log Integrity
- **Status:** Accepted
- **Context:** Corbel requires trustworthy, defensible business audit records for operational investigations, policy evaluations, human approvals, consequential actions, and regulatory traceability. While PostgreSQL provides robust transactional persistence, relational tables are not inherently immutable against updates or deletions.
- **Decision:** Use **PostgreSQL as Corbel's authoritative business audit store**, enforcing audit log integrity and sensitive data protection through architectural, application, and database controls:
  1. **Append-Only Design:** The audit schema is strictly append-only. Audit records are created via insert operations only.
  2. **No Application-Level Mutation APIs:** The application backend, domain services, and repository layers must not expose any update, delete, or overwrite operations for existing audit records.
  3. **Strict Database Privilege Restrictions & Role Separation:**
     - The application runtime database role must not own audit tables.
     - Grant the runtime role only the required `INSERT` and `SELECT` privileges on audit tables.
     - Explicitly revoke `UPDATE`, `DELETE`, and `TRUNCATE` privileges from the runtime role.
     - Restrict table ownership, schema ownership, migration credentials, and database-owner privileges strictly to trusted administrative and migration roles.
     - Application runtime credentials must not have permission to alter audit table definitions (`ALTER TABLE`) or remove audit tables (`DROP TABLE`).
     - Schema evolutions must occur strictly through the controlled Alembic migration process using separate, restricted migration credentials.
     - *Scope Limitation:* These controls provide application-level and database-role-level protection, not absolute immutability against privileged database administrators or infrastructure owners. Future tamper-evident archival and external verification may strengthen audit integrity.
  4. **Comprehensive Event Coverage:** All administrative changes, policy updates, monitor rule evaluations, human approvals, and consequential business operations must produce corresponding audit records.
  5. **Contextual Event Attributes & Sensitive Data Protection:**
     - Each audit event must capture sufficient evidence to establish: who performed the operation (actor ID and type), what operation occurred (action type), when it occurred (timestamp UTC), which entity and tenant were affected (entity type/ID, tenant/project ID), which approval, task, workflow, or execution it relates to, and what outcome occurred.
     - *Credentials & Secrets Exclusion:* Never store passwords, API keys, access tokens, secrets, or authentication credentials in audit records.
     - *PII & Confidentiality Hygiene:* Redact or exclude unnecessary personally identifiable information (PII) and confidential business data.
     - *No Indiscriminate Dumps:* Do not indiscriminately persist complete raw prompts, full model context, massive imported documents, or unrestricted request/response payloads. Where complete payload retention is unnecessary, store structured summaries, relevant identifiers, approved field subsets, hashes, or secure references to separately controlled records.
     - *Access Control & Retention:* Apply strict access controls and retention policies to sensitive audit metadata and referenced evidence.
     - *Preserving the Exact-Approved-Payload Invariant:* Redaction must not destroy the evidence needed to establish the exact action payload that was approved and executed. The approved payload is deterministically canonicalized before computing a cryptographic hash (SHA-256) of that canonicalized payload, which is retained alongside the separately protected payload or execution record to prove canonicalized payload integrity without exposing sensitive source data unnecessarily. A cryptographic hash provides a digest for integrity and equality verification of the canonicalized payload; it does not independently establish approver identity, authority, authorization, or the correctness of the approval process, which are guaranteed by deterministic authentication, authorization, approval-state validation, and audit controls.
  6. **Traceable Association:** Audit records must be linked to their corresponding workflow execution, investigation finding, recommendation, approval ID, or action idempotency key where applicable.
  7. **Future Archival Enhancements:** External archival (e.g., write-once cloud object storage dumps) and tamper-evident cryptographic verification (e.g., hash chains) may be evaluated as future enhancements without introducing blockchain or unnecessary cryptographic infrastructure today.
- **Reason:** Enterprise investigations, legal compliance, and operational governance demand reliable, immutable historical records of what occurred, who initiated or approved it, what data was presented, and the exact outcome of every action, while rigorously safeguarding enterprise secrets, customer PII, and sensitive operational payloads.
- **Consequences:**
  - *Positive:* High audit defensibility and operational accountability; clear separation between active operational state and immutable historical evidence; satisfies enterprise data protection, privacy, and compliance requirements.
  - *Negative:* Requires disciplined database privilege configuration and migration role management; requires ongoing sanitization and hashing discipline in audit event dispatchers.
  - *Neutral:* PostgreSQL remains the authoritative audit store; no blockchain or complex external ledger dependencies are introduced.

---

### ADR-021: Use-Case Architect Bounded Discovery, Structured Specifications & Governance
- **Status:** Accepted
- **Context:** Translating unstructured business problem statements into technical platform configurations requires structured requirements gathering, technical justification, architectural evaluation, and governance. A generic unconstrained chat prompt risks open-ended interrogation, non-deterministic hallucinations, premature coupling to RAG or agents, and lack of versioned specifications.
- **Decision:** Implement the **Use-Case Architect** as a governed, tenant-isolated capability adhering to:
  1. **Bounded Discovery Dialogue:** Multi-turn conversational interaction with maximum 1-3 targeted clarifying questions per turn, avoiding lengthy questionnaires and allowing incomplete drafts to be saved at any stage.
  2. **Fact vs. Assumption Separation:** Extracted requirements must strictly separate verified user-confirmed constraints from unverified AI assumptions.
  3. **Justified Pattern Selection & Non-Forced AI:** Architecture recommendations must evaluate deterministic rules, SQL/relational querying, keyword search, document RAG, and bounded agentic workflows, choosing the simplest reliable pattern. Deterministic business logic (e.g., price variance math) is enforced over LLM approximations. Alternatives considered must be documented with explicit rejection rationale.
  4. **Strict Schema-Validated Specification Objects:** Main output is a validated, version-controlled Pydantic schema (`UseCaseSpecification`) containing 22+ structured fields rather than free-form prose.
  5. **Formal Approval Gates & Append-Only Versioning:** Revisions increment immutable version numbers (`(use_case_id, version)` unique constraint). Formal approval requires `PROJECT_LEAD` or `ORG_ADMIN` role and records the approving user and timestamp. All lifecycle events (`USE_CASE_CREATED`, `USE_CASE_DISCOVERY_TURN`, `SPECIFICATION_GENERATED`, `SPECIFICATION_APPROVED`) emit immutable Phase 10 audit logs.
- **Consequences:**
  - *Positive:* Provides a reliable bridge from operational problem statements to executable Corbel configurations; guarantees architectural discipline and prevents AI over-engineering; complete auditability of all design decisions.
  - *Negative:* Requires maintaining structured schemas and version comparison diff logic across frontend and backend.
  - *Neutral:* Reuses existing Phase 8 AI Gateway, Phase 9 P2P vertical slice, and Phase 10 native audit store without introducing new infrastructure.

---

## Architectural Backlog & Open Questions

The following technical questions remain open for evaluation during their respective roadmap phases:

| ID | Topic | Current Hypothesis / Options | Target Phase |
| :--- | :--- | :--- | :--- |
| **Q-001** | **Dialect Support for External Connectors** | Use SQLAlchemy / DuckDB read-only connection pooling for external data sources vs. lightweight native drivers. | Phase 3 |
| **Q-002** | **Interactive Graph Visualization Library** | Evaluate React Flow vs. Cytoscape.js for frontend process variant and ontology rendering. | Phase 4 / Phase 6 |
| **Q-003** | **Durable Background Worker Mechanism** | Evaluate custom PostgreSQL task state table with polling / `LISTEN/NOTIFY` vs. lightweight Python async task runners before considering external infrastructure. | Phase 3 |
