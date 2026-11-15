"""Deterministic Query Compiler translating structured ASTs into safe, parameterized SQL."""

import re
from typing import Any

from corbel.domains.ontology.models import BusinessObject, Property, Relationship
from corbel.domains.query.exceptions import (
    QueryValidationException,
    UnmappedPropertyQueryException,
)
from corbel.domains.query.schemas import (
    QueryFilter,
    QueryJoin,
    QueryOperator,
    QuerySort,
    SortDirection,
    StructuredQueryRequest,
)

# Reject dangerous SQL keywords or punctuation in identifiers
SAFE_IDENTIFIER_REGEX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DANGEROUS_SQL_PATTERNS = re.compile(
    r"\b(ALTER|CREATE|DELETE|DROP|EXEC|EXECUTE|INSERT|MERGE|TRUNCATE|UPDATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


class CompiledQuery:
    """Compiled query result holding parameterized SQL, parameters, and column projections."""

    def __init__(
        self,
        sql: str,
        parameters: list[Any],
        projected_columns: list[str],
        primary_table: str,
        primary_columns_map: dict[str, str],  # property_name -> source_column
        joined_tables: list[dict[str, Any]],
    ) -> None:
        self.sql = sql
        self.parameters = parameters
        self.projected_columns = projected_columns
        self.primary_table = primary_table
        self.primary_columns_map = primary_columns_map
        self.joined_tables = joined_tables


class QueryCompiler:
    """Deterministic compiler and validator for structured ontology queries."""

    def __init__(
        self,
        target_object: BusinessObject,
        relationships: list[Relationship] | None = None,
        all_objects: dict[str, BusinessObject] | None = None,
    ) -> None:
        self.target_object = target_object
        self.relationships = {r.name.lower(): r for r in (relationships or [])}
        self.all_objects = all_objects or {}

        # Build property maps for target object
        self.props_by_name: dict[str, Property] = {
            p.name.lower(): p for p in self.target_object.properties
        }
        self.mapped_props: dict[str, str] = {}  # prop_name (lowercase) -> column_name
        for p in self.target_object.properties:
            if p.source_mapping_json and p.source_mapping_json.get("status") == "CONFIRMED":
                col = p.source_mapping_json.get("column_name")
                if col:
                    self.mapped_props[p.name.lower()] = col

    def compile(self, ast: StructuredQueryRequest) -> CompiledQuery:
        """Validate and compile a StructuredQueryRequest into parameterized read-only SQL."""
        # 1. Validate entity name
        if ast.entity_name.lower() != self.target_object.name.lower():
            raise QueryValidationException(
                f"Target entity in request ('{ast.entity_name}') does not match "
                f"compiler context entity ('{self.target_object.name}')."
            )

        primary_table = f"_t_{self.target_object.name.lower()}"
        primary_alias = "_t0"

        # 2. Resolve projected columns
        projected_columns: list[str] = []
        select_expressions: list[str] = []

        if not ast.fields:
            # Default to all confirmed mapped properties of the target entity
            if not self.mapped_props:
                raise QueryValidationException(
                    f"Entity '{self.target_object.name}' has no confirmed property mappings. "
                    "Cannot execute query."
                )
            for p_name, _ in self.mapped_props.items():
                orig_prop = self.props_by_name[p_name]
                projected_columns.append(orig_prop.name)
                select_expressions.append(f"{primary_alias}.{orig_prop.name}")
        else:
            for field in ast.fields:
                self._validate_identifier(field)
                f_lower = field.lower()
                if f_lower not in self.props_by_name:
                    raise QueryValidationException(
                        f"Property '{field}' does not exist on business entity '{self.target_object.name}'."
                    )
                if f_lower not in self.mapped_props:
                    raise UnmappedPropertyQueryException(self.target_object.name, field)

                orig_prop = self.props_by_name[f_lower]
                projected_columns.append(orig_prop.name)
                select_expressions.append(f"{primary_alias}.{orig_prop.name}")

        # 3. Handle Joins
        joined_tables: list[dict[str, Any]] = []
        join_clauses: list[str] = []

        for i, join_spec in enumerate(ast.joins, start=1):
            join_alias = f"_t{i}"
            join_meta = self._compile_join(join_spec, primary_alias, join_alias)
            joined_tables.append(join_meta)
            join_clauses.append(join_meta["clause"])

            # Add projected fields from joined entity
            for j_field in join_spec.fields:
                self._validate_identifier(j_field)
                jf_lower = j_field.lower()
                target_props = join_meta["target_props_by_name"]
                target_mapped = join_meta["target_mapped_props"]
                if jf_lower not in target_props:
                    raise QueryValidationException(
                        f"Property '{j_field}' does not exist on joined entity '{join_meta['target_name']}'."
                    )
                if jf_lower not in target_mapped:
                    raise UnmappedPropertyQueryException(join_meta["target_name"], j_field)
                orig_j_prop = target_props[jf_lower]
                alias_name = f"{join_meta['target_name']}_{orig_j_prop.name}"
                select_expressions.append(f"{join_alias}.{orig_j_prop.name} AS {alias_name}")
                projected_columns.append(alias_name)

        # 4. Compile WHERE filters
        parameters: list[Any] = []
        where_conditions: list[str] = []

        for f in ast.filters:
            cond_sql, cond_params = self._compile_filter(f, primary_alias)
            where_conditions.append(cond_sql)
            parameters.extend(cond_params)

        # 5. Compile ORDER BY
        order_clauses: list[str] = []
        for s in ast.sorts:
            order_sql = self._compile_sort(s, primary_alias)
            order_clauses.append(order_sql)

        # 6. Assemble complete SQL query
        sql_parts: list[str] = [
            f"SELECT {', '.join(select_expressions)}",
            f"FROM {primary_table} AS {primary_alias}",
        ]

        if join_clauses:
            sql_parts.extend(join_clauses)

        if where_conditions:
            sql_parts.append(f"WHERE {' AND '.join(where_conditions)}")

        if order_clauses:
            sql_parts.append(f"ORDER BY {', '.join(order_clauses)}")

        # Limit and Offset (strictly parameterized)
        clamped_limit = max(1, min(ast.limit, 500))
        clamped_offset = max(0, ast.offset)
        sql_parts.append("LIMIT ? OFFSET ?")
        parameters.append(clamped_limit)
        parameters.append(clamped_offset)

        full_sql = " ".join(sql_parts)

        # Safety Assertions
        if DANGEROUS_SQL_PATTERNS.search(full_sql):
            raise QueryValidationException("Dangerous SQL pattern detected in query compilation.")

        return CompiledQuery(
            sql=full_sql,
            parameters=parameters,
            projected_columns=projected_columns,
            primary_table=primary_table,
            primary_columns_map=self.mapped_props,
            joined_tables=joined_tables,
        )

    def _compile_filter(self, f: QueryFilter, alias: str) -> tuple[str, list[Any]]:
        """Validate and compile a single filter condition into parameterized SQL."""
        self._validate_identifier(f.field)
        f_lower = f.field.lower()

        if f_lower not in self.props_by_name:
            raise QueryValidationException(
                f"Cannot filter by property '{f.field}': property does not exist on entity '{self.target_object.name}'."
            )
        if f_lower not in self.mapped_props:
            raise UnmappedPropertyQueryException(self.target_object.name, f.field)

        prop = self.props_by_name[f_lower]
        col_expr = f"{alias}.{prop.name}"
        params: list[Any] = []

        # Validate and coerce value according to property data type
        val = self._coerce_value(f.value, prop.data_type, f.operator)

        if f.operator == QueryOperator.EQ:
            sql = f"{col_expr} = ?"
            params.append(val)
        elif f.operator == QueryOperator.NEQ:
            sql = f"{col_expr} != ?"
            params.append(val)
        elif f.operator == QueryOperator.GT:
            sql = f"{col_expr} > ?"
            params.append(val)
        elif f.operator == QueryOperator.GTE:
            sql = f"{col_expr} >= ?"
            params.append(val)
        elif f.operator == QueryOperator.LT:
            sql = f"{col_expr} < ?"
            params.append(val)
        elif f.operator == QueryOperator.LTE:
            sql = f"{col_expr} <= ?"
            params.append(val)
        elif f.operator == QueryOperator.CONTAINS:
            sql = f"{col_expr} LIKE ?"
            params.append(f"%{val}%")
        elif f.operator == QueryOperator.STARTS_WITH:
            sql = f"{col_expr} LIKE ?"
            params.append(f"{val}%")
        elif f.operator == QueryOperator.ENDS_WITH:
            sql = f"{col_expr} LIKE ?"
            params.append(f"%{val}")
        elif f.operator == QueryOperator.IN:
            if not isinstance(val, (list, tuple, set)) or not val:
                raise QueryValidationException(f"Operator 'IN' requires a non-empty list of values for '{f.field}'.")
            placeholders = ", ".join(["?"] * len(val))
            sql = f"{col_expr} IN ({placeholders})"
            params.extend(list(val))
        elif f.operator == QueryOperator.NOT_IN:
            if not isinstance(val, (list, tuple, set)) or not val:
                raise QueryValidationException(f"Operator 'NOT_IN' requires a non-empty list of values for '{f.field}'.")
            placeholders = ", ".join(["?"] * len(val))
            sql = f"{col_expr} NOT IN ({placeholders})"
            params.extend(list(val))
        elif f.operator == QueryOperator.IS_NULL:
            sql = f"{col_expr} IS NULL"
        elif f.operator == QueryOperator.IS_NOT_NULL:
            sql = f"{col_expr} IS NOT NULL"
        else:
            raise QueryValidationException(f"Unsupported query operator '{f.operator}'.")

        return sql, params

    def _compile_sort(self, s: QuerySort, alias: str) -> str:
        """Validate and compile ordering clause."""
        self._validate_identifier(s.field)
        f_lower = s.field.lower()
        if f_lower not in self.props_by_name:
            raise QueryValidationException(
                f"Cannot sort by property '{s.field}': property does not exist on entity '{self.target_object.name}'."
            )
        if f_lower not in self.mapped_props:
            raise UnmappedPropertyQueryException(self.target_object.name, s.field)

        prop = self.props_by_name[f_lower]
        direction = "ASC" if s.direction == SortDirection.ASC else "DESC"
        return f"{alias}.{prop.name} {direction}"

    def _compile_join(self, join_spec: QueryJoin, primary_alias: str, join_alias: str) -> dict[str, Any]:
        """Validate relationship and compile join clause with verified source and target properties."""
        rel_key = join_spec.relationship_name.lower().strip()
        if rel_key not in self.relationships:
            raise QueryValidationException(
                f"Relationship '{join_spec.relationship_name}' does not exist in the project ontology."
            )

        rel = self.relationships[rel_key]

        # Determine whether primary entity is the source or target of this relationship
        if rel.source_object_id == self.target_object.id:
            joined_obj = rel.target_object
            joined_obj_id = rel.target_object_id
            primary_prop_key = "source_property"
            joined_prop_key = "target_property"
        elif rel.target_object_id == self.target_object.id:
            joined_obj = rel.source_object
            joined_obj_id = rel.source_object_id
            primary_prop_key = "target_property"
            joined_prop_key = "source_property"
        else:
            raise QueryValidationException(
                f"Relationship '{rel.name}' does not connect to entity '{self.target_object.name}'."
            )

        if joined_obj is None and joined_obj_id:
            for o in self.all_objects.values():
                if o.id == joined_obj_id:
                    joined_obj = o
                    break

        if joined_obj is None:
            raise QueryValidationException(
                f"Target entity for relationship '{rel.name}' could not be resolved."
            )

        # 1. Read the relationship's actual join expression
        join_exp = rel.join_expression_json
        if not isinstance(join_exp, dict) or not join_exp:
            raise QueryValidationException(
                f"Relationship '{rel.name}' lacks valid join metadata."
            )

        prim_prop_name = join_exp.get(primary_prop_key) or join_exp.get("foreign_key_property")
        joined_prop_name = join_exp.get(joined_prop_key) or join_exp.get("foreign_key_property")
        if not prim_prop_name or not joined_prop_name:
            raise QueryValidationException(
                f"Relationship '{rel.name}' join metadata must specify source and target properties."
            )

        # 2. Validate identifiers before constructing SQL
        self._validate_identifier(prim_prop_name)
        self._validate_identifier(joined_prop_name)

        # 3. Validate that primary property belongs to primary entity and is confirmed mapped
        prim_lower = prim_prop_name.lower()
        if prim_lower not in self.props_by_name:
            raise QueryValidationException(
                f"Join property '{prim_prop_name}' in relationship '{rel.name}' does not exist on entity '{self.target_object.name}'."
            )
        if prim_lower not in self.mapped_props:
            raise UnmappedPropertyQueryException(self.target_object.name, prim_prop_name)
        orig_prim_prop = self.props_by_name[prim_lower]

        # 4. Validate that joined property belongs to joined entity and is confirmed mapped
        joined_props_by_name = {p.name.lower(): p for p in joined_obj.properties}
        joined_mapped_props: dict[str, str] = {}
        for p in joined_obj.properties:
            if p.source_mapping_json and p.source_mapping_json.get("status") == "CONFIRMED":
                col = p.source_mapping_json.get("column_name")
                if col:
                    joined_mapped_props[p.name.lower()] = col

        joined_lower = joined_prop_name.lower()
        if joined_lower not in joined_props_by_name:
            raise QueryValidationException(
                f"Join property '{joined_prop_name}' in relationship '{rel.name}' does not exist on joined entity '{joined_obj.name}'."
            )
        if joined_lower not in joined_mapped_props:
            raise UnmappedPropertyQueryException(joined_obj.name, joined_prop_name)
        orig_joined_prop = joined_props_by_name[joined_lower]

        join_table = f"_t_{joined_obj.name.lower()}"
        clause = f"LEFT JOIN {join_table} AS {join_alias} ON {primary_alias}.{orig_prim_prop.name} = {join_alias}.{orig_joined_prop.name}"

        return {
            "relationship_name": rel.name,
            "target_name": joined_obj.name,
            "target_object": joined_obj,
            "target_props_by_name": joined_props_by_name,
            "target_mapped_props": joined_mapped_props,
            "table": join_table,
            "alias": join_alias,
            "clause": clause,
        }

    def _coerce_value(self, val: Any, data_type: str, operator: QueryOperator) -> Any:
        """Validate and coerce value to match property data type."""
        if operator in (QueryOperator.IS_NULL, QueryOperator.IS_NOT_NULL):
            return None

        if operator in (QueryOperator.IN, QueryOperator.NOT_IN):
            if not isinstance(val, (list, tuple)):
                raise QueryValidationException("Value for IN/NOT_IN must be a list.")
            return [self._coerce_single_value(v, data_type) for v in val]

        return self._coerce_single_value(val, data_type)

    @staticmethod
    def _coerce_single_value(val: Any, data_type: str) -> Any:
        if val is None:
            return None

        dt_upper = data_type.upper()
        if dt_upper in ("NUMBER", "FLOAT", "INTEGER"):
            if isinstance(val, (int, float)):
                return val
            try:
                val_str = str(val).strip().replace(",", "")
                return float(val_str) if "." in val_str else int(val_str)
            except (ValueError, TypeError) as err:
                raise QueryValidationException(
                    f"Value '{val}' cannot be converted to numeric type for property."
                ) from err

        elif dt_upper == "BOOLEAN":
            if isinstance(val, bool):
                return 1 if val else 0
            val_str = str(val).strip().lower()
            if val_str in ("true", "1", "yes", "t"):
                return 1
            elif val_str in ("false", "0", "no", "f"):
                return 0
            raise QueryValidationException(f"Value '{val}' is not a valid boolean.")

        return str(val)

    @staticmethod
    def _validate_identifier(name: str) -> None:
        """Reject SQL injection characters in property or column names."""
        if not SAFE_IDENTIFIER_REGEX.match(name.strip()):
            raise QueryValidationException(
                f"Invalid identifier name '{name}': contains unsafe characters or spaces."
            )
