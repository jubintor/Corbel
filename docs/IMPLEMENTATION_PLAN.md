# Corbel — Phased Implementation Roadmap

## 1. Roadmap Strategy & Milestone Sequence

Corbel is built incrementally through a disciplined sequence of fourteen phases (Phase 0 through Phase 13). Each phase delivers a functional, tested vertical advancement that builds on previous verified components.

> [!IMPORTANT]
> This roadmap represents a structured development sequence, not an obligation to over-engineer speculative capabilities. Each phase must satisfy its acceptance criteria through automated testing and manual verification before downstream work commences.

```
Phase 0: Docs & Architecture Foundation  (CURRENT)
   ↓
Phase 1: Application Foundation & Dual Dev Environment
   ↓
Phase 2: Authentication, Authorization & Multi-Tenancy
   ↓
Phase 3: Data Intelligence & Profiling (P2P Ingestion)
   ↓
Phase 4: Ontology Engine & Semantic Discovery (P2P Mapping)
   ↓
Phase 5: Structured Querying & Early AI Gateway
   ↓
Phase 6: Process Intelligence & Event Mining (P2P Variant Rebuild)
   ↓
Phase 7: Adaptive Monitors & Exception Detection (P2P SLA Checks)
   ↓
Phase 8: Complete AI Infrastructure & Bounded State Machines
   ↓
Phase 9: Governed Investigation, Approvals & First Vertical Slice (P2P)
   ↓
Phase 10: Native Audit & Optional Arize Phoenix Observability
   ↓
Phase 11: Use-Case Architect
   ↓
Phase 12: Application Builder
   ↓
Phase 13: Extended Domain Demonstrations
```

---

## 2. Phase-by-Phase Specifications

### Phase 0 — Documentation and Architecture Foundation
- **Objective:** Establish the engineering foundation, product vision, architectural principles, domain model, decision log, and agent rules before writing application code.
- **Main Deliverables:**
  - `docs/VISION.md`: Product positioning, target personas, operating modes, and P2P reference flow.
  - `docs/ARCHITECTURE.md`: Modular monolith architecture, data flow, trust boundaries, dual dev modes, and AI infrastructure tiers.
  - `docs/DOMAIN_MODEL.md`: Conceptual entities, attributes, relationships, prompt lifecycle, and state invariants.
  - `docs/IMPLEMENTATION_PLAN.md`: Complete 14-phase delivery roadmap.
  - `docs/DECISIONS.md`: Initial architecture decision records (ADRs).
  - Root `AGENTS.md`: Mandatory instructions, coding rules, and guardrails for future AI agents.
- **Dependencies:** None.
- **Acceptance Criteria:**
  - All six foundational documents exist, are internally consistent, and adhere to authoritative tech stack guidelines.
  - No application code, container setups, or package installs exist in Phase 0.
- **Explicitly Excluded:**
  - Code generation, dependency installations, and container runs.

---

### Phase 1 — Application Foundation
- **Objective:** Stand up the core runnable modular monolith backend (FastAPI), frontend shell (React + TypeScript), database connection (PostgreSQL), dual local development modes (lightweight native and full Docker Compose), structured logging, and test harness.
- **Main Deliverables:**
  - Clean modular repository structure separating `src/corbel/` (backend) and `frontend/` (React SPA).
  - FastAPI application entrypoint with health-check endpoint (`/api/v1/health`) reporting system, database ping, and version status.
  - PostgreSQL database connection pool and schema migration harness (Alembic).
  - Dual development support:
    - **Default Lightweight Mode:** Dockerized PostgreSQL + Native Windows FastAPI & React/Vite.
    - **Full Integration Mode:** Docker Compose (`docker-compose.yml`) running all three services.
  - Strict environment configuration via `pydantic-settings` documented in `.env.example`.
  - Structured JSON logging with correlation IDs.
  - Automated test runners (`pytest` for backend, `Vitest` for frontend) with baseline smoke tests.
- **Dependencies:** Phase 0.
- **Acceptance Criteria:**
  - Backend runs cleanly natively against Dockerized PostgreSQL, returning `200 OK` from `/api/v1/health`.
  - `docker compose up` brings up the complete containerized stack without errors.
  - `pytest` executes and passes all baseline unit and health-check tests.
  - React application compiles with zero TypeScript errors under `strict: true`.
- **Explicitly Excluded:**
  - Authentication, tenant isolation, ontology discovery, process mining, AI agents, prompt management, Redis, Phoenix, durable task execution, or governed business actions. Phase 1 is strictly restricted to foundation plumbing and infrastructure setup.

---

### Phase 2 — Authentication, Authorization and Tenant Isolation
- **Objective:** Implement enterprise-grade user authentication, multi-tenant isolation, and deterministic role-based access control (RBAC).
- **Main Deliverables:**
  - Core domain models for `Organization`, `User`, and `Project`.
  - Secure password hashing (Argon2 / bcrypt) and JWT session handling.
  - Deterministic RBAC middleware enforcing roles (Admin, Analyst, Operator, Approver, Auditor).
  - Tenant context injection ensuring every database query is scoped to the active `tenant_id`.
  - API endpoints for user login, token refresh, and project switching.
  - Frontend authentication context, login view, and route guards.
- **Dependencies:** Phase 1.
- **Acceptance Criteria:**
  - Cross-tenant data access attempts are rejected with `403 Forbidden` and logged as security events.
  - Unauthenticated requests to protected endpoints return `401 Unauthorized`.
  - Deterministic permission checks pass 100% of negative and positive test scenarios.
- **Explicitly Excluded:**
  - SSO/SAML integration (deferred to enterprise adapter phase), multi-factor hardware keys, or biometric auth.

---

### Phase 3 — Data Intelligence
- **Objective:** Enable connecting, importing, profiling, and cataloging enterprise data from relational databases and flat files, focusing on Procure-to-Pay (P2P) source datasets.
- **Main Deliverables:**
  - `Data Source` connection management (PostgreSQL, MySQL, SQLite, and file uploads).
  - File parser and upload handler supporting CSV, JSON, and Excel XLSX.
  - Schema profiling engine computing column types, null ratios, cardinality, and basic value distributions.
  - `Dataset` catalog with searchable metadata and statistical summaries.
  - Support for baseline P2P datasets: `suppliers`, `purchase_orders`, `goods_receipts`, `invoices`.
  - Frontend Data Workspace: Source configuration forms, upload wizards, and profiling result views.
  - **Durable Worker Mechanism Evaluation:** Architectural evaluation of PostgreSQL-backed task queue mechanisms (custom task state table with `SELECT ... FOR UPDATE SKIP LOCKED` vs. lightweight async task runner) for long-running batch ingestion and profiling tasks, establishing the design foundation without authorizing the full investigation state machine engine before Phases 7–9.
- **Dependencies:** Phase 2.
- **Acceptance Criteria:**
  - User can upload multi-table P2P CSV datasets or connect a read-only database and view accurate column profiles and distributions within seconds.
  - Untrusted file inputs are strictly sanitized against path traversal or malicious payloads.
- **Explicitly Excluded:**
  - Distributed streaming connectors (Kafka, Flink), write-back mutations to source databases, or premature implementation of the multi-step AI investigation execution engine.

---

### Phase 4 — Ontology Engine and Semantic Discovery
- **Objective:** Construct the semantic layer that transforms raw tabular datasets into typed Business Objects, Properties, and Relationships, supporting P2P entity mapping.
- **Main Deliverables:**
  - Ontology domain models (`BusinessObject`, `Property`, `Relationship`) stored in PostgreSQL.
  - Semantic auto-discovery service inferring candidate entities (`Supplier`, `PurchaseOrder`, `GoodsReceipt`, `Invoice`) and foreign-key relationships using deterministic schema profiling and heuristics by default, with optional minimal Early AI Gateway assistance for terminology mappings.
  - Human validation interface for reviewing, confirming, or adjusting uncertain candidate ontology mappings.
  - Validation engine checking object invariants, required properties, and referential integrity.
  - Interactive frontend Ontology Graph Explorer and schema mapping editor.
- **Dependencies:** Phase 3.
- **Acceptance Criteria:**
  - P2P raw tables are successfully mapped into validated business objects connected by typed relationships (`Supplier` -> *issues* -> `PurchaseOrder` -> *received_as* -> `GoodsReceipt` -> *billed_in* -> `Invoice`).
  - Graph traversal queries return semantically joined object records deterministically.
- **Explicitly Excluded:**
  - Dedicated graph database engines (e.g., Neo4j); ontology mappings reside entirely in relational PostgreSQL tables. Full agent frameworks or complex AI infrastructure.

---

### Phase 5 — Structured Querying & Early AI Gateway
- **Objective:** Provide a reliable, validated semantic querying layer allowing users to query business objects using natural language and structured filters.
- **Main Deliverables:**
  - **Early AI Capability:** Minimal provider-neutral model gateway routing queries to hosted LLM providers (Anthropic, OpenAI).
  - Strict Pydantic output validation: Model parses natural language questions into strongly typed query ASTs (projections, filters, joins, limits).
  - Basic token accounting and latency logging for each query generation.
  - SQL safety sandbox: Deterministic query compiler translating query ASTs into parameterized, read-only SQL (`SELECT` only, no DDL/DML, row limits, statement timeouts).
  - Frontend Query Console with tabular results, export to CSV, and visual query plan inspector.
- **Dependencies:** Phase 4.
- **Acceptance Criteria:**
  - Natural language queries (e.g., "Show all invoices from Supplier X exceeding \$10,000 where goods were delivered late") compile into validated, read-only SQL.
  - Malformed or unsafe outputs are rejected deterministically before database query generation.
- **Explicitly Excluded:**
  - Complex multi-agent reasoning, autonomous tool execution, or general-purpose agent frameworks.

---

### Phase 6 — Process Intelligence
- **Objective:** Reconstruct end-to-end operational processes from event logs to analyze variants, throughput times, rework loops, and bottlenecks in the P2P lifecycle.
- **Main Deliverables:**
  - Event log ingestion and mapping (`Process`, `ProcessEvent`) defining Case ID, Activity, Timestamp, and Resource.
  - Process mining algorithm reconstructing directly-follows graphs (DFG) and process variants for P2P (e.g., PO Issued → Delivery → Invoicing → 3-Way Match → Payment).
  - Deterministic performance calculation engine measuring cycle times, stage durations, and bottleneck paths.
  - Frontend Process Visualizer rendering interactive process flow diagrams and variant distribution curves.
- **Dependencies:** Phase 4, Phase 5.
- **Acceptance Criteria:**
  - P2P event logs correctly render process variant graphs with accurate stage transitions, bottleneck highlights, and cycle-time calculations.
- **Explicitly Excluded:**
  - Real-time distributed stream processing or complex petri-net conformance checking algorithms.

---

### Phase 7 — Adaptive Monitors
- **Objective:** Implement continuous and scheduled operational monitors that detect anomalies, SLA breaches, and rule violations in procurement operations.
- **Main Deliverables:**
  - Monitor scheduler executing periodic rule checks against process events and business object states.
  - Deterministic rule evaluation engine testing `BusinessRule` expressions (e.g., price variance > 0.5%, delivery delay > 5 days).
  - `Finding` emission and lifecycle tracking (`OPEN`, `INVESTIGATING`, `RECOMMENDED`, `RESOLVED`, `DISMISSED`).
  - Frontend Monitor Center displaying active monitors, trigger histories, and the prioritized exception queue.
- **Dependencies:** Phase 6.
- **Acceptance Criteria:**
  - When a P2P transaction violates an operational rule (e.g., invoice price exceeds PO price), a `Finding` is generated with full context data and displayed in the exception queue.
- **Explicitly Excluded:**
  - Autonomous unapproved mutations or email spam dispatching.

---

### Phase 8 — Complete AI Infrastructure & Bounded State Machines
- **Objective:** Build the enterprise AI engineering backbone: reusable model gateway, bounded execution state machines, tool registry, prompt lifecycle management, granular cost attribution, multi-level caching, and evaluation framework.
- **Main Deliverables:**
  - **Reusable Model Gateway:** Provider adapters for hosted models (Anthropic, OpenAI) with standardized error handling and retry policies. (Local inference deferred as optional future capability).
  - **Task-Specific Bounded State Machines:** Replaces unconstrained agent loops with deterministic finite state machines (e.g., Data Discovery, Process Investigation, Rule Generation) with step limits and timeouts.
  - **Validated Tool Registry:** Typed Python functions with Pydantic parameter schemas, read-only constraints, and deterministic input validation.
  - **Prompt Management & Lifecycle Store:** Versioned prompt definitions with lifecycle states (`DRAFT` → `TEST` → `EVALUATE` → `APPROVE` → `DEPLOY` → `MONITOR` → `RETIRE`) and instant rollback (restoring the active deployment reference to a previously approved immutable prompt version; historical prompt versions are never modified in place).
  - **Granular Cost Attribution:** Tracks spend across Tenant, Project, Use Case, Workflow, Agent, Model, Execution ID, Prompt Version, Input/Output/Cached Tokens, Latency, and Task Outcome (Cost per Successful Task).
  - **Multi-Level Caching Architecture:** Provider-native prompt caching; Redis exact and semantic caching documented and deferred until justified.
  - **Evaluation & Regression Framework:** Versioned evaluation datasets, prompt regression tests, structured output validation, and grounding metrics.
- **Dependencies:** Phase 2, Phase 5, Phase 7.
- **Acceptance Criteria:**
  - State machines reliably execute multi-step workflows, validate tool arguments via Pydantic, enforce iteration limits, and record full cost records per invocation.
  - Prompt updates follow the formal approval lifecycle, and rollback restores the active deployment reference to a prior immutable version without modifying history.
- **Explicitly Excluded:**
  - Mandatory local model inference (hosted APIs used as initial deployment strategy; local inference deferred as future optional capability). Unbounded autonomous agent loops.

---

### Phase 9 — Governed Investigation, Approvals & First Vertical Slice (P2P)
- **Objective:** Connect operational findings to AI root-cause investigations, structured recommendations, human approval gates, and deterministic execution—delivering the complete, demonstrable **Procure-to-Pay (P2P)** vertical slice.
- **Main Deliverables:**
  - **Automated P2P Investigation Workflow:** State machine retrieves event context, correlates PO/Invoice records, separates verified facts from hypotheses, and deterministically calculates financial blast radius.
  - **Recommendation Engine:** Generates structured proposals (e.g., "Request Supplier Credit Memo", "Hold Discrepant Invoice") with confidence scores and risk ratings.
  - **Human Approval Portal:** Presents decision-makers with finding summaries, verified transactional facts, hypotheses, canonicalized proposed payload, and one-click approve/reject actions.
  - **Deterministic Action Dispatcher:** Executes approved actions against a controlled simulated enterprise environment (`SimulatedTargetAdapter`) with persisted idempotency keys and append-only audit logging.
- **Dependencies:** Phase 7, Phase 8.
- **Acceptance Criteria (P2P Vertical Slice Acceptance Test):**
  1. Ingest synthetic P2P dataset containing intentional anomalies (price variance, delivery delay).
  2. Profiler and ontology engine discover and map entities (`Supplier`, `PO`, `Invoice`).
  3. Process intelligence reconstructs process variants and flags delay bottlenecks.
  4. Adaptive monitor detects price discrepancy finding.
  5. Investigation state machine isolates the variance, confirms verified facts, and presents a hypothesis.
  6. Financial impact is calculated deterministically.
  7. Corrective recommendation is generated.
  8. Human operator reviews and approves the action via the UI, computing canonicalized `approved_payload_hash`.
  9. Action executes against simulated target adapter; outgoing payload hash matches approval; append-only audit record is logged.
  10. Rejection path verified: operator rejection halts execution and records rationale.
- **Explicitly Excluded:**
  - Direct execution without explicit human approval. Real live ERP mutations during demonstration.

---

### Phase 10 — Native Audit & Optional Arize Phoenix Observability
- **Objective:** Implement comprehensive platform compliance audit logging and integrate optional, independent AI observability via Arize Phoenix.
- **Main Deliverables:**
  - **Corbel Native Audit Store:** Append-only PostgreSQL audit log recording business events, approval decisions, policy checks, canonicalized execution payloads, and ROI metrics, protected by application-level and database-role privilege restrictions (revoking runtime `UPDATE`, `DELETE`, `TRUNCATE`).
  - **Optional Arize Phoenix Integration:** Telemetry hooks exporting LLM spans, traces, prompt inputs, and token latencies to an independently deployable Phoenix instance.
  - Fault-tolerant observability: Corbel operates seamlessly if Phoenix is offline or disabled.
  - Operational ROI reporting: Measuring MTTR progression and cost-per-successful-task benchmarks.
- **Dependencies:** Phase 9.
- **Acceptance Criteria:**
  - Compliance auditor can export a complete, append-only audit trail with canonical payload hash verification for any executed P2P action.
  - With Phoenix enabled, LLM spans and traces are visible in the Phoenix UI. With Phoenix disabled, Corbel functions with zero errors.
- **Explicitly Excluded:**
  - Mandatory Phoenix container in the local development environment; Phoenix remains an optional telemetry sink. Treating Phoenix as Corbel's authoritative business audit store.

---

### Phase 11 — Use-Case Architect
- **Objective:** Provide an interactive business tool that translates unstructured operational problem statements into structured, executable Corbel blueprints.
- **Main Deliverables:**
  - Guided blueprinting interview workflow capturing business objectives, source systems, entities, and SLA requirements.
  - Automated blueprint generator synthesizing proposed ontology mappings, monitor rules, and action definitions.
  - One-click blueprint deployment provisioning platform components into a target Project.
- **Dependencies:** Phase 9, Phase 10.
- **Acceptance Criteria:**
  - A user can enter a plain-text operational description (e.g., "Monitor stalled purchase orders across SAP and Warehouse DB") and receive a validated, deployable Corbel project configuration.
- **Explicitly Excluded:**
  - Automatic deployment without explicit human review of the generated blueprint.

---

### Phase 12 — Application Builder
- **Objective:** Enable rapid creation of governed, business-facing mini-applications, operator consoles, and approval portals from ontology definitions.
- **Main Deliverables:**
  - Low-code UI specification format (declarative JSON/Pydantic schemas describing layouts, forms, and tables).
  - Dynamic UI Renderer in React interpreting specifications into interactive, theme-consistent interfaces.
  - Parameterized action form bindings linking UI inputs to governed Action schemas.
- **Dependencies:** Phase 11.
- **Acceptance Criteria:**
  - A custom operational app (e.g., "P2P Invoice Discrepancy Resolution Portal") can be generated from an ontology specification and used by operators with zero bespoke frontend code written.
- **Explicitly Excluded:**
  - Arbitrary custom JavaScript execution in the browser; all UI behaviors are driven by declarative schemas.

---

### Phase 13 — Extended Domain Demonstrations
- **Objective:** Deliver extensible, production-pattern vertical reference implementations proving Corbel's capabilities in additional enterprise domains.
- **Main Deliverables:**
  - **Domain 1: Order-to-Cash (O2C):** Detecting credit check delays, pricing discrepancies, and delivery bottlenecks.
  - **Domain 2: Supply Chain Logistics:** Tracking in-transit delays, customs clearance hold-ups, and inventory stock-outs.
  - **Domain 3: IT Incident Remediation:** Correlating alerts, assessing incident blast radius, and guiding governed remediation actions.
  - Synthetic data generators producing realistic, high-volume event streams for each demonstration.
- **Dependencies:** Phase 12.
- **Acceptance Criteria:**
  - Each domain demonstration spins up with synthetic data, executes monitors, surfaces findings, and guides governed human-in-the-loop resolution.
- **Explicitly Excluded:**
  - Connecting to live proprietary customer ERP production environments during demonstrations.
