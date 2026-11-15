"""Domain service orchestrating structured query compilation, sandbox execution, and NLQ parsing."""

import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from corbel.ai.gateway import AIGateway
from corbel.ai.schemas import ModelRequest
from corbel.core.config import get_settings
from corbel.domains.data_intelligence.models import DatasetVersion
from corbel.domains.data_intelligence.parser import DatasetParser
from corbel.domains.ontology.models import BusinessObject, Relationship
from corbel.domains.query.compiler import QueryCompiler
from corbel.domains.query.exceptions import (
    EntityNotFoundQueryException,
    QueryExecutionException,
    QueryValidationException,
)
from corbel.domains.query.models import QueryExecution
from corbel.domains.query.schemas import (
    NaturalLanguageQueryRequest,
    NaturalLanguageQueryResponse,
    QueryableEntitySchema,
    QueryablePropertySchema,
    QueryExecutionAuditResponse,
    QuerySchemaResponse,
    StructuredQueryRequest,
    StructuredQueryResponse,
)
from corbel.domains.tenancy.models import ProjectRole
from corbel.domains.tenancy.service import TenancyService

logger = logging.getLogger(__name__)


@dataclass
class NLQCompilationEntry:
    """Server-side record of an authenticated NLQ compilation."""

    compilation_id: uuid.UUID
    org_id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    prompt: str
    token_count: int
    created_at: float
    ttl_seconds: float = 900.0  # 15 minutes


class NLQCompilationStore:
    """Thread-safe in-memory store for server-controlled NLQ compilation audit references."""

    def __init__(self) -> None:
        self._entries: dict[uuid.UUID, NLQCompilationEntry] = {}
        self._lock = threading.Lock()

    def store(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        prompt: str,
        token_count: int,
    ) -> str:
        comp_id = uuid.uuid4()
        entry = NLQCompilationEntry(
            compilation_id=comp_id,
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            prompt=prompt,
            token_count=token_count,
            created_at=time.time(),
        )
        with self._lock:
            now = time.time()
            expired = [k for k, v in self._entries.items() if now - v.created_at > v.ttl_seconds]
            for k in expired:
                self._entries.pop(k, None)
            self._entries[comp_id] = entry
        return str(comp_id)

    def consume(
        self,
        compilation_ref: str,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> NLQCompilationEntry | None:
        try:
            comp_id = uuid.UUID(compilation_ref.strip())
        except (ValueError, TypeError, AttributeError):
            return None

        with self._lock:
            entry = self._entries.get(comp_id)
            if entry is None:
                return None

            now = time.time()
            if now - entry.created_at > entry.ttl_seconds:
                self._entries.pop(comp_id, None)
                return None

            # Enforce authorization and scoping: org, project, and user MUST match
            if entry.org_id != org_id or entry.project_id != project_id or entry.user_id != user_id:
                return None

            # Single-use consumption: pop it so it cannot be reused
            return self._entries.pop(comp_id, None)

    def clear(self) -> None:
        """Clear all entries (primarily for test fixtures)."""
        with self._lock:
            self._entries.clear()


nlq_compilation_store = NLQCompilationStore()


class QueryService:
    """Service orchestrating semantic query compilation, execution, and early AI assistance."""

    def __init__(self, session: AsyncSession, ai_gateway: AIGateway | None = None) -> None:
        self.session = session
        self.tenancy_service = TenancyService(session)
        self.ai_gateway = ai_gateway or AIGateway()
        self.settings = get_settings()

    async def get_query_schema(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> QuerySchemaResponse:
        """Retrieve all queryable business objects, properties, and relationships for the project."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.VIEWER, ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        objects_stmt = (
            select(BusinessObject)
            .where(
                BusinessObject.project_id == project_id,
            )
            .options(selectinload(BusinessObject.properties))
            .order_by(BusinessObject.name)
        )
        objects = (await self.session.execute(objects_stmt)).scalars().all()

        rel_stmt = (
            select(Relationship)
            .where(Relationship.project_id == project_id)
            .options(
                selectinload(Relationship.source_object),
                selectinload(Relationship.target_object),
            )
        )
        relationships = (await self.session.execute(rel_stmt)).scalars().all()

        # Group relationships by source object ID
        rels_by_source: dict[uuid.UUID, list[str]] = {}
        for r in relationships:
            rels_by_source.setdefault(r.source_object_id, []).append(r.name)

        entities: list[QueryableEntitySchema] = []
        for obj in objects:
            props_schema: list[QueryablePropertySchema] = []
            for p in obj.properties:
                is_mapped = bool(
                    p.source_mapping_json and p.source_mapping_json.get("status") == "CONFIRMED"
                )
                source_col = (
                    p.source_mapping_json.get("column_name")
                    if (is_mapped and p.source_mapping_json)
                    else None
                )

                props_schema.append(
                    QueryablePropertySchema(
                        name=p.name,
                        display_name=p.display_name,
                        data_type=p.data_type,
                        is_primary_key=p.is_primary_key,
                        is_nullable=p.is_nullable,
                        is_mapped=is_mapped,
                        source_column=source_col,
                    )
                )

            entities.append(
                QueryableEntitySchema(
                    id=str(obj.id),
                    name=obj.name,
                    display_name=obj.display_name,
                    description=obj.description,
                    properties=props_schema,
                    available_relationships=rels_by_source.get(obj.id, []),
                )
            )

        return QuerySchemaResponse(project_id=str(project_id), entities=entities)

    async def execute_query(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        req: StructuredQueryRequest,
        is_nlq: bool = False,
        nlq_prompt: str | None = None,
        token_count: int | None = None,
    ) -> StructuredQueryResponse:
        """Compile and execute a StructuredQueryRequest against confirmed ontology datasets."""
        start_time = time.perf_counter()

        # Enforce tenant and project authorization
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.VIEWER, ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        # Resolve NLQ audit attribution from server-controlled store if reference provided
        if req.nlq_reference:
            entry = nlq_compilation_store.consume(
                compilation_ref=req.nlq_reference,
                org_id=org_id,
                project_id=project_id,
                user_id=user_id,
            )
            if entry is None:
                raise QueryValidationException("Invalid or expired NLQ compilation reference.")
            is_nlq = True
            nlq_prompt = entry.prompt
            token_count = entry.token_count

        # 1. Fetch Target Business Object and all Project Ontology context
        target_obj = await self._get_business_object_by_name(project_id, req.entity_name)
        if target_obj is None:
            raise EntityNotFoundQueryException(req.entity_name)

        rel_stmt = (
            select(Relationship)
            .where(Relationship.project_id == project_id)
            .options(
                selectinload(Relationship.source_object),
                selectinload(Relationship.target_object),
            )
        )
        relationships = (await self.session.execute(rel_stmt)).scalars().all()

        all_objects_stmt = (
            select(BusinessObject)
            .where(BusinessObject.project_id == project_id)
            .options(selectinload(BusinessObject.properties))
        )
        all_objects_list = (await self.session.execute(all_objects_stmt)).scalars().all()
        all_objects_map = {o.name.lower(): o for o in all_objects_list}

        # 2. Compile query using deterministic safety compiler
        compiler = QueryCompiler(
            target_object=target_obj,
            relationships=list(relationships),
            all_objects=all_objects_map,
        )
        compiled = compiler.compile(req)

        # 3. Setup in-memory SQLite sandbox database
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        try:
            # 4. Load dataset tables for primary entity and any joined entities
            loaded_tables: set[str] = set()
            await self._load_entity_into_sandbox(conn, target_obj, compiled.primary_table, org_id, project_id)
            loaded_tables.add(compiled.primary_table)

            for join_meta in compiled.joined_tables:
                j_table = join_meta["table"]
                if j_table not in loaded_tables:
                    joined_obj = join_meta["target_object"]
                    await self._load_entity_into_sandbox(conn, joined_obj, j_table, org_id, project_id)
                    loaded_tables.add(j_table)

            cursor = conn.cursor()

            # 5. Execute EXPLAIN QUERY PLAN
            explain_sql = f"EXPLAIN QUERY PLAN {compiled.sql}"
            try:
                explain_rows = cursor.execute(explain_sql, compiled.parameters).fetchall()
                query_plan = [
                    f"id={r[0]}, parent={r[1]}, notused={r[2]}, detail={r[3]}" for r in explain_rows
                ]
            except Exception:
                query_plan = ["Sandbox scan"]

            # 6. Execute Count Query for pagination total
            count_sql = f"SELECT COUNT(*) FROM ({compiled.sql.split('LIMIT')[0]}) AS _sub"
            # Extract parameters without LIMIT and OFFSET
            count_params = compiled.parameters[:-2]
            try:
                total_count = cursor.execute(count_sql, count_params).fetchone()[0]
            except Exception as err:
                raise QueryExecutionException(f"Failed to calculate query total count: {err}") from err

            # 7. Execute Main Parameterized Query
            exec_start = time.perf_counter()
            try:
                cursor.execute(compiled.sql, compiled.parameters)
                db_rows = cursor.fetchall()
            except Exception as err:
                raise QueryExecutionException(f"Query execution failed: {err}") from err

            execution_time_ms = (time.perf_counter() - exec_start) * 1000.0

            # Convert rows to dicts
            result_rows: list[dict[str, Any]] = []
            for r in db_rows:
                result_rows.append(dict(r))

            total_latency_ms = (time.perf_counter() - start_time) * 1000.0

            # 8. Audit Record Persistence
            audit = QueryExecution(
                id=uuid.uuid4(),
                project_id=project_id,
                user_id=user_id,
                business_object_id=target_obj.id,
                entity_name=target_obj.name,
                query_ast_json=req.model_dump(),
                compiled_sql=compiled.sql,
                parameters_json=compiled.parameters,
                row_count=len(result_rows),
                execution_time_ms=round(total_latency_ms, 2),
                is_nlq=is_nlq,
                nlq_prompt=nlq_prompt,
                token_count=token_count,
            )
            self.session.add(audit)
            await self.session.commit()

            return StructuredQueryResponse(
                entity_name=target_obj.name,
                columns=compiled.projected_columns,
                rows=result_rows,
                total_count=total_count,
                limit=req.limit,
                offset=req.offset,
                compiled_sql=compiled.sql,
                parameters=compiled.parameters,
                execution_time_ms=round(execution_time_ms, 2),
                query_plan=query_plan,
            )

        finally:
            conn.close()

    async def natural_language_query(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        req: NaturalLanguageQueryRequest,
    ) -> NaturalLanguageQueryResponse:
        """Use the Early AI Gateway to translate natural language into a validated StructuredQueryRequest."""
        # Enforce tenant and project authorization
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.VIEWER, ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        # 1. Retrieve project query schema for grounding
        schema_response = await self.get_query_schema(org_id, project_id, user_id)
        if not schema_response.entities:
            raise QueryValidationException("Project has no queryable business entities in its ontology.")

        # Prepare ontology metadata description
        entities_summary = []
        for ent in schema_response.entities:
            mapped_props = [
                f"{p.name} ({p.data_type}, mapped to '{p.source_column}')"
                for p in ent.properties
                if p.is_mapped
            ]
            entities_summary.append(
                f"- Entity '{ent.name}' (Display: '{ent.display_name}'): Mapped properties: {', '.join(mapped_props) if mapped_props else 'None'}. Relationships: {', '.join(ent.available_relationships) if ent.available_relationships else 'None'}."
            )

        system_prompt = (
            "You are Corbel's Semantic Query Compiler. Your role is to translate business questions "
            "into a strictly validated StructuredQueryRequest AST.\n\n"
            "ONTOLOGY SCHEMA DEFINITION:\n"
            + "\n".join(entities_summary)
            + "\n\n"
            "RULES:\n"
            "1. Output ONLY a valid JSON object matching the StructuredQueryRequest schema.\n"
            "2. 'entity_name' MUST match one of the available entities exactly.\n"
            "3. Only filter or sort on properties listed in the ontology for that entity.\n"
            "4. Supported operators: 'eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'contains', 'in', 'is_null', 'is_not_null'.\n"
            "5. If a numeric value has currency signs or commas, strip them (e.g. $10,000 -> 10000).\n"
            "6. Set reasonable limit (default 50, maximum 500).\n"
        )

        user_content = f"User Request: \"{req.prompt}\""
        if req.target_entity:
            user_content += f"\nTarget Entity Hint: {req.target_entity}"

        model_request = ModelRequest(
            system_prompt=system_prompt,
            user_prompt=user_content,
            temperature=0.0,
            max_tokens=1024,
            response_schema=StructuredQueryRequest.model_json_schema(),
        )

        # 2. Invoke AI Gateway
        parsed_ast, model_response = await self.ai_gateway.generate_structured(
            model_request,
            StructuredQueryRequest,
        )

        # 3. Dry-run compile the parsed AST against the ontology to guarantee safety and validity
        target_obj = await self._get_business_object_by_name(project_id, parsed_ast.entity_name)
        if target_obj is None:
            raise EntityNotFoundQueryException(parsed_ast.entity_name)

        rel_stmt = (
            select(Relationship)
            .where(Relationship.project_id == project_id)
            .options(
                selectinload(Relationship.source_object),
                selectinload(Relationship.target_object),
            )
        )
        relationships = (await self.session.execute(rel_stmt)).scalars().all()

        all_objects_stmt = (
            select(BusinessObject)
            .where(BusinessObject.project_id == project_id)
            .options(selectinload(BusinessObject.properties))
        )
        all_objects_list = (await self.session.execute(all_objects_stmt)).scalars().all()
        all_objects_map = {o.name.lower(): o for o in all_objects_list}

        compiler = QueryCompiler(
            target_object=target_obj,
            relationships=list(relationships),
            all_objects=all_objects_map,
        )
        compiled = compiler.compile(parsed_ast)

        # Store server-side compilation audit reference
        token_count = model_response.token_usage.total_tokens
        nlq_ref = nlq_compilation_store.store(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            prompt=req.prompt,
            token_count=token_count,
        )
        parsed_ast.nlq_reference = nlq_ref

        explanation = (
            f"Parsed natural language query targeting entity '{parsed_ast.entity_name}' "
            f"with {len(parsed_ast.filters)} filter(s) and limit={parsed_ast.limit}."
        )

        return NaturalLanguageQueryResponse(
            prompt=req.prompt,
            parsed_query=parsed_ast,
            compiled_sql=compiled.sql,
            explanation=explanation,
            token_usage=model_response.token_usage,
            latency_ms=round(model_response.latency_ms, 2),
            nlq_reference=nlq_ref,
        )

    async def get_query_history(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 50,
    ) -> list[QueryExecutionAuditResponse]:
        """Retrieve audit history of executed queries for the project."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.VIEWER, ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        stmt = (
            select(QueryExecution)
            .where(QueryExecution.project_id == project_id)
            .order_by(QueryExecution.created_at.desc())
            .limit(min(limit, 200))
        )
        executions = (await self.session.execute(stmt)).scalars().all()

        return [
            QueryExecutionAuditResponse(
                id=str(e.id),
                project_id=str(e.project_id),
                user_id=str(e.user_id),
                entity_name=e.entity_name,
                query_ast=e.query_ast_json,
                compiled_sql=e.compiled_sql,
                row_count=e.row_count,
                execution_time_ms=e.execution_time_ms,
                is_nlq=e.is_nlq,
                nlq_prompt=e.nlq_prompt,
                token_count=e.token_count,
                created_at=e.created_at.isoformat(),
            )
            for e in executions
        ]

    # ==========================================================================
    # Internal Helpers
    # ==========================================================================

    async def _get_business_object_by_name(
        self,
        project_id: uuid.UUID,
        name: str,
    ) -> BusinessObject | None:
        """Fetch BusinessObject by name with properties eagerly loaded."""
        stmt = (
            select(BusinessObject)
            .where(
                BusinessObject.project_id == project_id,
                BusinessObject.name.ilike(name.strip()),
            )
            .options(selectinload(BusinessObject.properties))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _load_entity_into_sandbox(
        self,
        conn: sqlite3.Connection,
        obj: BusinessObject,
        table_name: str,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> None:
        """Create sandbox table for BusinessObject and load records from confirmed dataset versions."""
        # 1. Map confirmed properties: property_name -> (dataset_id, dataset_version_id, column_name, data_type)
        prop_mappings: dict[str, dict[str, Any]] = {}
        for p in obj.properties:
            if p.source_mapping_json and p.source_mapping_json.get("status") == "CONFIRMED":
                prop_mappings[p.name] = {
                    "dataset_id": uuid.UUID(p.source_mapping_json["dataset_id"]),
                    "dataset_version_id": uuid.UUID(p.source_mapping_json["dataset_version_id"]),
                    "column_name": p.source_mapping_json["column_name"],
                    "data_type": p.data_type,
                }

        if not prop_mappings:
            # Create empty table
            conn.execute(f"CREATE TABLE {table_name} (id TEXT)")
            return

        # 2. Map SQLite column types
        col_defs = []
        for p_name, meta in prop_mappings.items():
            dt = meta["data_type"].upper()
            sql_type = "TEXT"
            if dt in ("INTEGER", "NUMBER", "FLOAT"):
                sql_type = "NUMERIC"
            elif dt == "BOOLEAN":
                sql_type = "INTEGER"
            col_defs.append(f"{p_name} {sql_type}")

        create_sql = f"CREATE TABLE {table_name} ({', '.join(col_defs)})"
        conn.execute(create_sql)

        # 3. Find unique dataset versions feeding this entity
        # Typically in P2P an entity is mapped to a primary dataset version
        version_ids = {m["dataset_version_id"] for m in prop_mappings.values()}
        storage_root = Path(self.settings.DATASET_STORAGE_DIR).resolve()

        for ver_id in version_ids:
            v_stmt = select(DatasetVersion).where(
                DatasetVersion.id == ver_id,
                DatasetVersion.project_id == project_id,
            )
            version = (await self.session.execute(v_stmt)).scalar_one_or_none()
            if version is None:
                logger.warning(
                    "Referenced dataset version %s for entity '%s' not found in project %s",
                    ver_id,
                    obj.name,
                    project_id,
                )
                raise QueryExecutionException(
                    f"Referenced dataset version for entity '{obj.name}' could not be resolved."
                )

            file_path = (storage_root / version.storage_path).resolve()
            if not str(file_path).startswith(str(storage_root)):
                logger.error(
                    "Path traversal detected or storage root mismatch for entity '%s' (version %s): %s",
                    obj.name,
                    version.id,
                    file_path,
                )
                raise QueryExecutionException("Invalid dataset storage path.")

            if not file_path.exists():
                logger.warning(
                    "Backing dataset file missing on disk for entity '%s' (version %s): %s",
                    obj.name,
                    version.id,
                    file_path,
                )
                raise QueryExecutionException(
                    f"Underlying dataset file for entity '{obj.name}' is unavailable on storage."
                )

            parser = DatasetParser(file_path, version.file_format)
            headers, row_gen = parser.parse_headers_and_stream()
            header_idx = {h: idx for idx, h in enumerate(headers)}

            # Prepare insert statement
            cols_to_insert = list(prop_mappings.keys())
            placeholders = ", ".join(["?"] * len(cols_to_insert))
            insert_sql = f"INSERT INTO {table_name} ({', '.join(cols_to_insert)}) VALUES ({placeholders})"

            batch: list[list[Any]] = []
            for row in row_gen:
                row_vals: list[Any] = []
                for p_name in cols_to_insert:
                    src_col = prop_mappings[p_name]["column_name"]
                    idx = header_idx.get(src_col)
                    val = row[idx] if idx is not None and idx < len(row) else None
                    # Clean/coerce numeric if needed
                    dt = prop_mappings[p_name]["data_type"].upper()
                    if dt in ("INTEGER", "NUMBER", "FLOAT") and val is not None:
                        try:
                            val = float(str(val).replace(",", "").strip())
                        except (ValueError, TypeError):
                            val = None
                    elif dt == "BOOLEAN" and val is not None:
                        val_str = str(val).strip().lower()
                        val = 1 if val_str in ("true", "1", "yes") else 0
                    row_vals.append(val)
                batch.append(row_vals)

                if len(batch) >= 1000:
                    conn.executemany(insert_sql, batch)
                    batch.clear()

            if batch:
                conn.executemany(insert_sql, batch)

        conn.commit()
