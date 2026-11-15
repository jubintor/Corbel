"""Unit tests for deterministic data profiling (No LLM)."""

from typing import Any

from corbel.domains.data_intelligence.profiler import DatasetProfiler


def test_profiler_numeric_statistics() -> None:
    headers = ["amount", "count"]

    def row_stream() -> Any:
        # values: [10, 20, 30, 40, 50], mean = 30, stddev = 15.8114, sum = 150
        data = [
            ["10", "0"],
            ["20", "2"],
            ["30", "0"],
            ["40", "4"],
            ["50", "0"],
        ]
        yield from data

    schemas, summary = DatasetProfiler.profile_stream(headers, row_stream())

    assert summary.total_rows == 5
    assert summary.total_columns == 2
    assert summary.duplicate_rows_count == 0

    amount_col = summary.columns[0]
    assert amount_col.detected_type == "INTEGER"
    assert amount_col.null_count == 0
    assert amount_col.non_null_count == 5
    assert amount_col.distinct_count == 5
    assert amount_col.numeric_stats is not None
    assert amount_col.numeric_stats.min == 10.0
    assert amount_col.numeric_stats.max == 50.0
    assert amount_col.numeric_stats.mean == 30.0
    assert amount_col.numeric_stats.sum == 150.0
    assert amount_col.numeric_stats.median == 30.0
    assert round(amount_col.numeric_stats.stddev or 0, 2) == 15.81

    count_col = summary.columns[1]
    assert count_col.numeric_stats is not None
    assert count_col.numeric_stats.zeros_count == 3


def test_profiler_null_and_missing_values() -> None:
    headers = ["optional_col", "all_null_col"]

    def row_stream() -> Any:
        yield ["val1", ""]
        yield ["", "null"]
        yield ["val2", "nan"]
        yield [None, "None"]

    schemas, summary = DatasetProfiler.profile_stream(headers, row_stream())

    opt_col = summary.columns[0]
    assert opt_col.total_count == 4
    assert opt_col.null_count == 2
    assert opt_col.non_null_count == 2
    assert opt_col.null_percentage == 50.0
    assert "HIGH_NULL_RATE (50.0%)" in opt_col.quality_warnings

    null_col = summary.columns[1]
    assert null_col.null_count == 4
    assert null_col.null_percentage == 100.0
    assert "ALL_NULL_COLUMN" in null_col.quality_warnings


def test_profiler_datetime_statistics() -> None:
    headers = ["order_date"]

    def row_stream() -> Any:
        yield ["2024-01-01"]
        yield ["2024-01-11"]
        yield ["2024-01-21"]

    schemas, summary = DatasetProfiler.profile_stream(headers, row_stream())

    date_col = summary.columns[0]
    assert date_col.detected_type in ("DATE", "DATETIME")
    assert date_col.datetime_stats is not None
    assert "2024-01-01" in (date_col.datetime_stats.earliest or "")
    assert "2024-01-21" in (date_col.datetime_stats.latest or "")
    assert date_col.datetime_stats.range_days == 20.0


def test_profiler_duplicate_row_detection() -> None:
    headers = ["colA", "colB"]

    def row_stream() -> Any:
        yield ["A", "1"]
        yield ["A", "1"]  # duplicate
        yield ["B", "2"]
        yield ["B", "2"]  # duplicate
        yield ["C", "3"]

    schemas, summary = DatasetProfiler.profile_stream(headers, row_stream())

    assert summary.total_rows == 5
    assert summary.duplicate_rows_count == 2
    assert summary.duplicate_rows_pct == 40.0
    assert any("DUPLICATE_ROWS_DETECTED" in w for w in summary.dataset_quality_warnings)


def test_profiler_constant_column() -> None:
    headers = ["currency"]

    def row_stream() -> Any:
        yield ["USD"]
        yield ["USD"]
        yield ["USD"]

    schemas, summary = DatasetProfiler.profile_stream(headers, row_stream())

    col = summary.columns[0]
    assert col.distinct_count == 1
    assert "CONSTANT_COLUMN" in col.quality_warnings


def test_profiler_potential_primary_key() -> None:
    headers = ["po_number"]

    def row_stream() -> Any:
        yield ["PO-001"]
        yield ["PO-002"]
        yield ["PO-003"]

    schemas, summary = DatasetProfiler.profile_stream(headers, row_stream())

    col = summary.columns[0]
    assert col.unique_percentage == 100.0
    assert "POTENTIAL_PRIMARY_KEY" in col.quality_warnings


def test_profiler_reproducibility() -> None:
    """Verifies profiling output is 100% deterministic and identical on repeated execution."""
    headers = ["id", "amount", "status"]
    data = [
        ["1", "100.5", "ACTIVE"],
        ["2", "250.0", "PENDING"],
        ["3", "300.75", "ACTIVE"],
    ]

    schemas1, summary1 = DatasetProfiler.profile_stream(headers, (d for d in data))
    schemas2, summary2 = DatasetProfiler.profile_stream(headers, (d for d in data))

    assert summary1.total_rows == summary2.total_rows
    assert summary1.duplicate_rows_count == summary2.duplicate_rows_count
    assert summary1.columns[1].numeric_stats == summary2.columns[1].numeric_stats
