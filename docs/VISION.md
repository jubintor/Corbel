# Corbel — Product Vision & Strategic Positioning

## 1. Executive Summary & Purpose

**Corbel** is an Enterprise AI and Operational Intelligence Platform designed to bridge the structural divide between enterprise operational data, business process reality, and governed business action.

Modern enterprises run on fragmented transactional systems—ERPs, CRMs, procurement engines, ticketing systems, legacy databases, and flat files. Despite massive investments in business intelligence (BI) dashboards and machine learning models, operational leaders still face:
1. **Operational Opacity:** Dashboards display aggregate historical metrics (what happened in the past), but fail to explain *why* operational bottlenecks occur across process handoffs.
2. **Context Fragmentation:** Data exists in technical silos (tables, columns, foreign keys) devoid of unified business semantic meaning (suppliers, purchase orders, shipments, invoices, payments).
3. **The "Last-Mile Action" Void:** Traditional analytics systems report exceptions, but cannot investigate root causes, quantify business impacts, recommend corrective actions, or safely execute those actions with enterprise-grade auditability.

**Corbel's Core Promise:**
> **Discover business context. Understand operations. Build intelligent solutions. Learn from failures. Execute with human approval.**

Corbel transforms raw transactional data into an active operational model of the business, continuously monitors process execution, identifies recurring exceptions, reasons over root causes using bounded state machines, and presents governed, verifiable action plans to human decision-makers.

---

## 2. Product Positioning: What Corbel Is and Is Not

To ensure architectural discipline and clear product boundaries, Corbel's scope is strictly defined against market categories:

| What Corbel Is | What Corbel Is NOT |
| :--- | :--- |
| **An Operational Intelligence Platform** combining semantic ontology, process discovery, and governed AI reasoning. | **Not a generic chatbot** or generic text-generation assistant with ad-hoc prompt chains. |
| **A Governed System of Action** where AI investigates and recommends, but deterministic rules and human approvals gate execution. | **Not a generic multi-agent framework** running unbounded or unconstrained autonomous loops. |
| **A Semantic Context & Intelligence Layer** operating over existing systems of record. | **Not an ERP, CRM, or WMS replacement.** Corbel reads and analyzes operational data from connected systems. Consequential write-back operations must pass through governed action definitions, deterministic policy validation, authenticated human approval where required, and dedicated target-system adapters. The initial P2P demonstration uses a simulated target-system adapter only; live ERP or financial-system mutations remain strictly outside early demonstration scope. |
| **A Pragmatic, Cohesive Modular Platform** focused on demonstrable operational ROI. | **Not a clone of Palantir Foundry, Celonis, or Retool.** It synthesizes key architectural ideas without their legacy baggage. |

### Architectural Inspirations

Corbel deliberately borrows proven paradigms from industry milestones while maintaining a modern, lightweight footprint:

- **Palantir Foundry:** Conceptual model of a business ontology—objects, properties, relationships, governed action types, and strict object-level security.
- **Celonis:** Process intelligence fundamentals—event log extraction, process graph reconstruction, variant analysis, throughput time calculation, bottleneck detection, and exception identification.
- **Retool:** Rapid, low-friction construction of business-facing interfaces, parameterized action forms, operational dashboards, and guided workflow queues.
- **NVIDIA Auto-Ontology:** Automated semantic discovery—inferring candidate business entities, column-to-property mapping, foreign key relationship discovery, and domain terminology alignment.
- **Modern AI Systems Engineering:** Provider-neutral model gateways, task-specific bounded execution state machines, structured schemas with Pydantic validation, explicit context engineering, evaluation harnesses, and strict token/cost attribution.

---

## 3. The Two Operating Modes

Enterprise operational environments vary dramatically in regulatory scrutiny, change tolerance, and data maturity. Corbel addresses this through two complementary operating modes:

```
+-----------------------------------------------------------------------------+
|                                CORBEL PLATFORM                              |
+-----------------------------------------------------------------------------+
|                                                                             |
|   +---------------------------------+   +-------------------------------+   |
|   |      GOVERNED INTELLIGENCE      |   |     ADAPTIVE INTELLIGENCE     |   |
|   |   (Audit-Intensive / Regulated) |   |    (Rapid Discovery / Speed)  |   |
|   +---------------------------------+   +-------------------------------+   |
|   | • Explicit, versioned ontology  |   | • Semantic auto-discovery     |   |
|   | • Deterministic business rules  |   | • Background process mining   |   |
|   | • Strict multi-party approvals  |   | • Anomaly & SLA monitors      |   |
|   | • Append-only audit records     |   | • AI root-cause investigation |   |
|   | • Formal change management      |   | • Action recommendations      |   |
|   | • Role-based action access      |   | • Human-gated activation      |   |
|   +---------------------------------+   +-------------------------------+   |
|                    \                                 /                      |
|                     \                               /                       |
|                      v                             v                        |
|            +-------------------------------------------------+              |
|            |    DETERMINISTIC EXECUTION & POLICY ENFORCER    |              |
|            +-------------------------------------------------+              |
+-----------------------------------------------------------------------------+
```

### 1. Governed Intelligence
Built for mission-critical, audit-heavy, and compliance-sensitive workflows (e.g., procurement disbursements, financial operations, healthcare administration, regulatory compliance):
- **Explicit Schema & Ontologies:** Every business object, property, and relationship is formally registered, typed, and version-controlled.
- **Traceable Process History:** Append-only audit records log who initiated an action, what evidence was presented to the user, what rules were evaluated, and the exact timestamp and canonicalized payload of execution, protected by database-role privilege boundaries (though not absolutely immutable against privileged database administrators).
- **Versioned Business Rules:** Business logic is implemented in deterministic code with explicit change logs, regression tests, and approval policies.
- **Multi-Level Approval Workflows:** Consequential actions require designated, authenticated human authorization before triggering external API mutations or database writes.

### 2. Adaptive Intelligence
Built for rapid operational discovery, hypothesis testing, and continuous process optimization:
- **Semantic Auto-Discovery:** Connects to raw data sources, profiles columns, infers candidate business entities, detects candidate relationships, and suggests terminology mappings. Adaptive discovery never silently modifies certified ontology definitions, active business rules, permissions, or action configurations.
- **Scheduled & Recurring Operational Monitoring:** Periodically observes event sequences, flags process deviations, detects SLA breaches, and surfaces unhandled exceptions on defined schedules.
- **AI-Assisted Investigation:** Spawns specialized analytical state machines to query correlated records, synthesize evidence, hypothesize root causes, and calculate operational blast radiuses while strictly distinguishing verified transactional facts from model hypotheses.
- **Governed Action Recommendation:** Proposes remedies with confidence scores and evidentiary backing. Adaptive AI cannot independently activate business rules or execute consequential actions; all consequential changes require explicit human review, deterministic policy validation, and authenticated approval.

**Guiding Rule:** Expose complexity and rigor when governance demands it; keep mechanics backgrounded and effortless when exploration and speed matter.

---

## 4. Target Users and Enterprise Value

Corbel delivers tangible value across distinct enterprise personas:

| Persona | Primary Needs & Pain Points | Corbel Solution | Target Operational Objective |
| :--- | :--- | :--- | :--- |
| **VP / Operations Executive** | Lack of visibility across end-to-end value streams; silent process failures eroding margins. | Unified operational dashboard, macro bottleneck visualization, cost-of-failure quantification. | Enable measurable working capital optimization and systemic reduction in SLA penalties (hypotheses to be validated through production benchmarks). |
| **Process Owner / Business Analyst** | Relies on engineering tickets to extract data or run ad-hoc process mining queries. | Intuitive semantic query builder, interactive process graph explorer, automated root-cause insights. | Accelerate operational analysis cycles from weeks to minutes via direct self-service exploration. |
| **Operations Specialist / Frontline Agent** | Juggling 5-10 disparate systems to resolve a single operational exception; manual data re-entry. | Guided exception queue, context-rich investigation summaries, one-click pre-validated actions. | Target significant reduction in mean time to resolution (MTTR) for customer and order exceptions. |
| **Compliance, Risk & Audit Officer** | Black-box AI risk; lack of audit trails for automated workflows; regulatory non-compliance exposure. | Append-only action audit records with database privilege controls, human-in-the-loop gating, transparent rule evaluation, deterministic guardrails. | Prevent unauthorized autonomous mutations through deterministic controls; establish an auditable, defensible operational compliance posture. |
| **IT & Platform Engineering Lead** | Burden of building bespoke internal tools and brittle integration pipelines for business teams. | Extensible modular platform, standardized REST APIs, Pydantic schemas, containerized local dev. | Lower engineering backlog, standardized security boundaries, reduced reliance on unmanaged ad-hoc scripts. |

*(Note: Specific ROI and efficiency figures are operational objectives and hypotheses to be validated through production benchmarks rather than unsubstantiated claims.)*

---

## 5. Core Platform Capabilities

Corbel's lifecycle spans ten core capabilities:

1. **Data Intelligence:** Ingests, profiles, cleanses, and characterizes data from transactional databases and structured flat files (CSV, JSON, Excel).
2. **Ontology Engine:** Maps technical schemas into living business objects (e.g., `Supplier`, `PurchaseOrder`, `Invoice`) connected by typed relationships and real-world constraints.
3. **Structured Querying:** Translates natural language and semantic queries into safe, validated, read-only SQL queries against the underlying relational store.
4. **Process Intelligence:** Extracts event logs from transactional audit trails, reconstructs process variant graphs, detects rework loops, and highlights performance bottlenecks.
5. **Adaptive Monitors:** Automated observers that run on schedule or recurring intervals to detect business anomalies, rule violations, SLA expirations, and unexpected metric shifts.
6. **AI Infrastructure:** Enterprise AI engineering backbone providing provider-neutral model access, task-specific bounded state machines, structured tool execution, context engineering, prompt lifecycle management, and token/cost attribution.
7. **Governed Investigation & Execution:** Multi-step analytical workflows that isolate exception root causes, synthesize evidence, present human approval cards, and execute pre-configured actions via target-system adapters.
8. **Use-Case Architect:** An interactive workflow translating unstructured business problem statements into formal, executable operational blueprints.
9. **Application Builder:** Low-code/governed UI generation engine producing typed forms, decision queues, and status boards from ontology definitions.
10. **Extended Domain Demonstrations:** Pre-packaged vertical templates demonstrating immediate operational value across core business processes.

---

## 6. The First Demonstrable Vertical Slice: Procure-to-Pay (P2P)

To avoid building speculative horizontal layers without end-to-end validation, Corbel's initial validation target is the **Procure-to-Pay (P2P)** operational lifecycle.

The end-to-end P2P reference flow establishes the following 14 capabilities:
1. **Import** supplier, purchase order, delivery receipt, and invoice datasets from files or databases.
2. **Profile** unfamiliar schemas, missing values, column types, and data quality distributions.
3. **Discover** candidate business entities (`Supplier`, `PurchaseOrder`, `GoodsReceipt`, `Invoice`) and relationships.
4. **Validate** ontology mappings via human review for uncertain entity links.
5. **Reconstruct** procurement process events and variants (e.g., PO Issued → Goods Received → Invoice Received → 3-Way Match → Payment Cleared).
6. **Calculate** delays, stage cycle times, and exceptions deterministically (e.g., delivery delays, price variances).
7. **Identify** affected suppliers, orders, and invoices experiencing exceptions.
8. **Investigate** supporting records using task-specific AI analytical state machines.
9. **Distinguish** verified transactional facts from AI-generated causal hypotheses.
10. **Quantify** financial and operational impact using deterministic arithmetic calculations.
11. **Generate** structured corrective recommendations (e.g., re-routing orders, requesting credit memos).
12. **Require** explicit human approval before any consequential external action is dispatched.
13. **Demonstrate** safe execution against a controlled simulated enterprise target (`SimulatedTargetAdapter`).
14. **Preserve** an append-only audit trail of evidence, recommendations, approval sign-offs, and execution results with database-role privilege restrictions.

This vertical slice serves as the concrete reference benchmark against which all platform components are tested and validated.
