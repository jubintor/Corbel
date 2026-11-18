"""Deterministic profiling engine for tabular datasets (No LLM usage)."""

import hashlib
import math
from collections.abc import Generator
from datetime import UTC, date, datetime
from typing import Any

from corbel.domains.data_intelligence.schemas import (
    ColumnProfile,
    ColumnSchema,
    DateTimeStats,
    NumericStats,
    ProfilingSummary,
    StringStats,
)

NULL_STRINGS = {"", "null", "none", "nan", "na", "n/a", "nil", "undefined"}

DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%f",
]


def is_null_value(val: Any) -> bool:
    """Check if value represents a null/missing datum."""
    if val is None:
        return True
    if isinstance(val, (int, float, bool, date, datetime)):
        return bool(isinstance(val, float) and math.isnan(val))
    val_str = str(val).strip().lower()
    return val_str in NULL_STRINGS


def parse_date_value(val: Any) -> datetime | None:
    """Attempt deterministic date/datetime parsing."""
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    if not isinstance(val, str):
        return None

    val_str = val.strip()
    # Try ISO first
    try:
        return datetime.fromisoformat(val_str.replace("Z", "+00:00"))
    except Exception:
        pass

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(val_str, fmt)
        except Exception:
            continue
    return None


class ColumnProfiler:
    """Accumulates single-pass statistics for an individual column."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.total_count = 0
        self.null_count = 0
        self.distinct_values: set[Any] = set()
        self.sample_values: list[Any] = []
        self.distinct_cap = 20000

        # Type counters
        self.bool_count = 0
        self.int_count = 0
        self.float_count = 0
        self.date_count = 0
        self.string_count = 0

        # Numeric stats (Welford's algorithm)
        self.numeric_count = 0
        self.numeric_sum = 0.0
        self.mean = 0.0
        self.M2 = 0.0
        self.min_numeric: float | None = None
        self.max_numeric: float | None = None
        self.zeros_count = 0
        self.numeric_values_sample: list[float] = []

        # Datetime stats
        self.earliest_date: datetime | None = None
        self.latest_date: datetime | None = None

        # String stats
        self.string_lens: list[int] = []

    def update(self, val: Any) -> None:
        """Update metrics with a new row value."""
        self.total_count += 1
        if is_null_value(val):
            self.null_count += 1
            return

        # Track distinct values up to cap
        if len(self.distinct_values) < self.distinct_cap:
            self.distinct_values.add(str(val))

        # Sample values (first 5 distinct non-null)
        if len(self.sample_values) < 5 and str(val) not in [str(s) for s in self.sample_values]:
            self.sample_values.append(val)

        # Type detection
        if isinstance(val, bool):
            self.bool_count += 1
            return

        val_str = str(val).strip()

        # Check boolean string
        if val_str.lower() in ("true", "false"):
            self.bool_count += 1
            return

        # Check integer
        is_int = False
        try:
            i_val = int(val_str)
            # Avoid confusing large strings with numbers
            if str(i_val) == val_str or (val_str.startswith("+") and str(i_val) == val_str[1:]):
                self.int_count += 1
                self._update_numeric(float(i_val))
                is_int = True
        except (ValueError, TypeError):
            pass

        if is_int:
            return

        # Check float
        is_float = False
        try:
            f_val = float(val_str)
            if not math.isnan(f_val) and not math.isinf(f_val):
                self.float_count += 1
                self._update_numeric(f_val)
                is_float = True
        except (ValueError, TypeError):
            pass

        if is_float:
            return

        # Check date/datetime
        dt_val = parse_date_value(val_str)
        if dt_val is not None:
            self.date_count += 1
            if self.earliest_date is None or dt_val < self.earliest_date:
                self.earliest_date = dt_val
            if self.latest_date is None or dt_val > self.latest_date:
                self.latest_date = dt_val
            return

        # Fallback to string
        self.string_count += 1
        self.string_lens.append(len(val_str))

    def _update_numeric(self, x: float) -> None:
        """Update Welford's algorithm for numerically stable variance."""
        self.numeric_count += 1
        self.numeric_sum += x
        if x == 0.0:
            self.zeros_count += 1

        if self.min_numeric is None or x < self.min_numeric:
            self.min_numeric = x
        if self.max_numeric is None or x > self.max_numeric:
            self.max_numeric = x

        delta = x - self.mean
        self.mean += delta / self.numeric_count
        delta2 = x - self.mean
        self.M2 += delta * delta2

        if len(self.numeric_values_sample) < 20000:
            self.numeric_values_sample.append(x)

    def finalize(self) -> ColumnProfile:
        """Compile and return the final ColumnProfile."""
        non_null_count = self.total_count - self.null_count
        null_pct = (self.null_count / self.total_count * 100.0) if self.total_count > 0 else 0.0
        distinct_count = len(self.distinct_values)
        unique_pct = (distinct_count / self.total_count * 100.0) if self.total_count > 0 else 0.0

        # Inferred type
        detected_type = "STRING"
        if non_null_count == 0:
            detected_type = "UNKNOWN"
        elif self.bool_count == non_null_count:
            detected_type = "BOOLEAN"
        elif self.int_count == non_null_count:
            detected_type = "INTEGER"
        elif (self.int_count + self.float_count) == non_null_count:
            detected_type = "FLOAT"
        elif self.date_count == non_null_count:
            detected_type = "DATETIME"
        elif self.string_count == non_null_count:
            detected_type = "STRING"
        else:
            # Mixed types: select dominant type
            type_counts = [
                ("INTEGER", self.int_count),
                ("FLOAT", self.float_count),
                ("DATETIME", self.date_count),
                ("BOOLEAN", self.bool_count),
                ("STRING", self.string_count),
            ]
            type_counts.sort(key=lambda t: t[1], reverse=True)
            dominant_type, dominant_count = type_counts[0]
            detected_type = dominant_type if dominant_count / non_null_count >= 0.90 else "STRING"

        # Numeric stats
        num_stats = None
        if self.numeric_count > 0:
            variance = self.M2 / (self.numeric_count - 1) if self.numeric_count > 1 else 0.0
            stddev = math.sqrt(variance) if variance >= 0 else 0.0
            median = None
            if self.numeric_values_sample:
                sorted_vals = sorted(self.numeric_values_sample)
                n = len(sorted_vals)
                if n % 2 == 1:
                    median = sorted_vals[n // 2]
                else:
                    median = (sorted_vals[(n // 2) - 1] + sorted_vals[n // 2]) / 2.0

            num_stats = NumericStats(
                min=self.min_numeric,
                max=self.max_numeric,
                mean=round(self.mean, 4),
                stddev=round(stddev, 4),
                median=round(median, 4) if median is not None else None,
                sum=round(self.numeric_sum, 4),
                zeros_count=self.zeros_count,
            )

        # DateTime stats
        dt_stats = None
        if self.date_count > 0 and self.earliest_date and self.latest_date:
            range_days = (self.latest_date - self.earliest_date).total_seconds() / 86400.0
            dt_stats = DateTimeStats(
                earliest=self.earliest_date.isoformat(),
                latest=self.latest_date.isoformat(),
                range_days=round(range_days, 2),
                invalid_count=non_null_count - self.date_count,
            )

        # String stats
        str_stats = None
        if self.string_lens:
            str_stats = StringStats(
                min_length=min(self.string_lens),
                max_length=max(self.string_lens),
                avg_length=round(sum(self.string_lens) / len(self.string_lens), 2),
            )

        # Quality warnings
        quality_warnings: list[str] = []
        if null_pct == 100.0:
            quality_warnings.append("ALL_NULL_COLUMN")
        elif null_pct >= 50.0:
            quality_warnings.append(f"HIGH_NULL_RATE ({round(null_pct, 1)}%)")

        if distinct_count == 1 and non_null_count > 1:
            quality_warnings.append("CONSTANT_COLUMN")

        if unique_pct == 100.0 and self.null_count == 0 and self.total_count > 1:
            quality_warnings.append("POTENTIAL_PRIMARY_KEY")

        if (
            self.string_count > 0
            and (self.int_count + self.float_count) > 0
            and non_null_count > 5
        ):
            quality_warnings.append("MIXED_DATA_TYPES")

        return ColumnProfile(
            column_name=self.name,
            detected_type=detected_type,
            total_count=self.total_count,
            null_count=self.null_count,
            non_null_count=non_null_count,
            null_percentage=round(null_pct, 2),
            distinct_count=distinct_count,
            unique_percentage=round(unique_pct, 2),
            sample_values=self.sample_values,
            numeric_stats=num_stats,
            datetime_stats=dt_stats,
            string_stats=str_stats,
            quality_warnings=quality_warnings,
        )


class DatasetProfiler:
    """Profiles a dataset in a single streaming pass without loading all rows into memory."""

    @staticmethod
    def profile_stream(
        headers: list[str],
        row_stream: Generator[list[Any], None, None],
    ) -> tuple[list[ColumnSchema], ProfilingSummary]:
        """Compute column schemas and comprehensive deterministic profile."""
        col_profilers = [ColumnProfiler(name=h) for h in headers]
        total_rows = 0
        seen_row_hashes: set[str] = set()
        duplicate_rows_count = 0

        for row in row_stream:
            total_rows += 1

            # Hash row values to detect duplicate rows
            canonical_row = tuple(str(c) if c is not None else "" for c in row)
            row_hash = hashlib.sha256(repr(canonical_row).encode("utf-8")).hexdigest()
            if row_hash in seen_row_hashes:
                duplicate_rows_count += 1
            else:
                if len(seen_row_hashes) < 100000:
                    seen_row_hashes.add(row_hash)

            for profiler, val in zip(col_profilers, row, strict=False):
                profiler.update(val)

        columns_profile = [p.finalize() for p in col_profilers]

        duplicate_pct = (
            round(duplicate_rows_count / total_rows * 100.0, 2) if total_rows > 0 else 0.0
        )

        dataset_warnings: list[str] = []
        if duplicate_rows_count > 0:
            dataset_warnings.append(
                f"DUPLICATE_ROWS_DETECTED ({duplicate_rows_count} rows, {duplicate_pct}%)"
            )

        all_null_cols = [c.column_name for c in columns_profile if c.null_percentage == 100.0]
        if all_null_cols:
            dataset_warnings.append(f"ALL_NULL_COLUMNS ({', '.join(all_null_cols)})")

        high_null_cols = [
            c.column_name for c in columns_profile if 50.0 <= c.null_percentage < 100.0
        ]
        if high_null_cols:
            dataset_warnings.append(f"HIGH_NULL_COLUMNS ({', '.join(high_null_cols)})")

        summary = ProfilingSummary(
            total_rows=total_rows,
            total_columns=len(headers),
            duplicate_rows_count=duplicate_rows_count,
            duplicate_rows_pct=duplicate_pct,
            columns=columns_profile,
            dataset_quality_warnings=dataset_warnings,
            profiled_at=datetime.now(UTC),
        )

        schemas = [
            ColumnSchema(
                name=col.column_name,
                data_type=col.detected_type,
                nullable=(col.null_count > 0),
                sample_values=col.sample_values,
            )
            for col in columns_profile
        ]

        return schemas, summary
