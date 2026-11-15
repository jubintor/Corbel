"""Unit tests for dataset file parsing, filename sanitization, and encoding detection."""

import json
from pathlib import Path

import pytest

from corbel.domains.data_intelligence.exceptions import (
    EmptyDatasetException,
    InvalidDatasetHeaderException,
    MalformedDatasetException,
    UnsafeFilenameException,
    UnsupportedFileFormatException,
)
from corbel.domains.data_intelligence.parser import (
    DatasetParser,
    detect_file_format,
    sanitize_filename,
)


def test_sanitize_filename_valid() -> None:
    assert sanitize_filename("suppliers.csv") == "suppliers.csv"
    assert sanitize_filename("p2p_invoices_2024.json") == "p2p_invoices_2024.json"
    assert sanitize_filename("  orders-report.xlsx  ") == "orders-report.xlsx"


def test_sanitize_filename_unsafe_traversal_rejected() -> None:
    with pytest.raises(UnsafeFilenameException):
        sanitize_filename("../../etc/passwd")

    with pytest.raises(UnsafeFilenameException):
        sanitize_filename("..\\..\\windows\\system32")

    with pytest.raises(UnsafeFilenameException):
        sanitize_filename("orders\0.csv")

    with pytest.raises(UnsafeFilenameException):
        sanitize_filename("   ")


def test_detect_file_format() -> None:
    assert detect_file_format("data.csv") == "CSV"
    assert detect_file_format("data.JSON") == "JSON"
    assert detect_file_format("data.jsonl") == "JSON"
    assert detect_file_format("data.xlsx") == "XLSX"

    with pytest.raises(UnsupportedFileFormatException):
        detect_file_format("script.py")

    with pytest.raises(UnsupportedFileFormatException):
        detect_file_format("archive.zip")


def test_parse_valid_csv(tmp_path: Path) -> None:
    csv_file = tmp_path / "valid.csv"
    csv_file.write_text("id,name,amount\n1,Alpha,100.5\n2,Beta,200.0\n", encoding="utf-8")

    parser = DatasetParser(csv_file, "CSV")
    headers, stream = parser.parse_headers_and_stream()
    assert headers == ["id", "name", "amount"]

    rows = list(stream)
    assert len(rows) == 2
    assert rows[0] == ["1", "Alpha", "100.5"]
    assert rows[1] == ["2", "Beta", "200.0"]


def test_parse_csv_semicolon_delimited(tmp_path: Path) -> None:
    csv_file = tmp_path / "semicolon.csv"
    csv_file.write_text("id;product;price\n101;Widget;49.99\n102;Gadget;19.99\n", encoding="utf-8")

    parser = DatasetParser(csv_file, "CSV")
    headers, stream = parser.parse_headers_and_stream()
    assert headers == ["id", "product", "price"]
    rows = list(stream)
    assert len(rows) == 2
    assert rows[0] == ["101", "Widget", "49.99"]


def test_parse_csv_with_bom(tmp_path: Path) -> None:
    csv_file = tmp_path / "bom.csv"
    csv_file.write_text("po_num,vendor\nPO1,Acme\n", encoding="utf-8-sig")

    parser = DatasetParser(csv_file, "CSV")
    headers, stream = parser.parse_headers_and_stream()
    assert headers == ["po_num", "vendor"]
    rows = list(stream)
    assert len(rows) == 1
    assert rows[0] == ["PO1", "Acme"]


def test_parse_csv_empty_file_fails(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.csv"
    empty_file.write_bytes(b"")

    with pytest.raises(EmptyDatasetException):
        DatasetParser(empty_file, "CSV")


def test_parse_csv_empty_header_fails(tmp_path: Path) -> None:
    csv_file = tmp_path / "no_headers.csv"
    csv_file.write_text(",,,  \n1,2,3,4\n", encoding="utf-8")

    parser = DatasetParser(csv_file, "CSV")
    with pytest.raises(InvalidDatasetHeaderException):
        parser.parse_headers_and_stream()


def test_parse_csv_duplicate_headers_deduplicated(tmp_path: Path) -> None:
    csv_file = tmp_path / "dupe_headers.csv"
    csv_file.write_text("name,name,name\nJohn,Doe,Smith\n", encoding="utf-8")

    parser = DatasetParser(csv_file, "CSV")
    headers, stream = parser.parse_headers_and_stream()
    assert headers == ["name", "name_1", "name_2"]
    rows = list(stream)
    assert len(rows) == 1
    assert rows[0] == ["John", "Doe", "Smith"]


def test_parse_valid_json_array(tmp_path: Path) -> None:
    json_file = tmp_path / "records.json"
    records = [
        {"vendor_id": "V1", "name": "Supplier A", "active": True},
        {"vendor_id": "V2", "name": "Supplier B", "active": False},
    ]
    json_file.write_text(json.dumps(records), encoding="utf-8")

    parser = DatasetParser(json_file, "JSON")
    headers, stream = parser.parse_headers_and_stream()
    assert headers == ["vendor_id", "name", "active"]

    rows = list(stream)
    assert len(rows) == 2
    assert rows[0] == ["V1", "Supplier A", True]
    assert rows[1] == ["V2", "Supplier B", False]


def test_parse_json_lines(tmp_path: Path) -> None:
    jsonl_file = tmp_path / "records.jsonl"
    jsonl_file.write_text(
        '{"event": "login", "code": 1}\n{"event": "logout", "code": 0}\n', encoding="utf-8"
    )

    parser = DatasetParser(jsonl_file, "JSON")
    headers, stream = parser.parse_headers_and_stream()
    assert headers == ["event", "code"]
    rows = list(stream)
    assert len(rows) == 2
    assert rows[0] == ["login", 1]
    assert rows[1] == ["logout", 0]


def test_parse_malformed_json_fails(tmp_path: Path) -> None:
    json_file = tmp_path / "bad.json"
    json_file.write_text("[{broken_json", encoding="utf-8")

    parser = DatasetParser(json_file, "JSON")
    with pytest.raises(MalformedDatasetException):
        parser.parse_headers_and_stream()


def test_parse_preview_limit(tmp_path: Path) -> None:
    csv_file = tmp_path / "large.csv"
    content = "col\n" + "\n".join(str(i) for i in range(50))
    csv_file.write_text(content, encoding="utf-8")

    parser = DatasetParser(csv_file, "CSV")
    headers, rows = parser.get_preview(limit=5)
    assert headers == ["col"]
    assert len(rows) == 5
    assert rows[0] == {"col": "0"}
    assert rows[4] == {"col": "4"}
