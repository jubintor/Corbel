"""Streaming file parser and schema discovery engine for tabular datasets."""

import csv
import json
import os
import re
from collections.abc import Generator
from pathlib import Path
from typing import Any

from corbel.domains.data_intelligence.exceptions import (
    EmptyDatasetException,
    InvalidDatasetHeaderException,
    MalformedDatasetException,
    UnsafeFilenameException,
    UnsupportedFileFormatException,
)
from corbel.domains.data_intelligence.models import FileFormat

SUPPORTED_EXTENSIONS = {
    ".csv": FileFormat.CSV.value,
    ".json": FileFormat.JSON.value,
    ".jsonl": FileFormat.JSON.value,
    ".xlsx": FileFormat.XLSX.value,
}


def sanitize_filename(filename: str) -> str:
    """Validate and sanitize untrusted filename against path traversal and unsafe characters."""
    if not filename or not filename.strip():
        raise UnsafeFilenameException("Filename cannot be empty")

    raw_name = filename.strip()
    # Reject null bytes, directory traversal patterns
    if "\0" in raw_name or ".." in raw_name or "/" in raw_name or "\\" in raw_name:
        raise UnsafeFilenameException(filename)

    base = os.path.basename(raw_name)
    # Sanitize characters: allow alphanumeric, underscore, hyphen, dot
    clean_name = re.sub(r"[^\w\.\-]", "_", base)
    if not clean_name or clean_name.startswith("."):
        raise UnsafeFilenameException(filename)

    return clean_name


def detect_file_format(filename: str) -> str:
    """Detect file format enum string from filename extension."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileFormatException(ext, list(SUPPORTED_EXTENSIONS.keys()))
    return SUPPORTED_EXTENSIONS[ext]


class DatasetParser:
    """Streaming parser for supported tabular formats (CSV, JSON, XLSX)."""

    def __init__(self, file_path: str | Path, file_format: str) -> None:
        self.file_path = Path(file_path)
        self.file_format = file_format
        if not self.file_path.exists():
            raise MalformedDatasetException(f"Dataset file '{self.file_path}' does not exist on disk.")

        file_size = self.file_path.stat().st_size
        if file_size == 0:
            raise EmptyDatasetException("Dataset file is empty (0 bytes).")

    def _open_text_file(self) -> tuple[Any, str]:
        """Try opening file with UTF-8, UTF-8-sig (BOM), or Latin-1 encoding."""
        for enc in ["utf-8-sig", "utf-8", "latin-1"]:
            try:
                f = open(self.file_path, encoding=enc, errors="replace")  # noqa: SIM115
                # Read a test chunk to verify decodability
                sample = f.read(4096)
                if not sample.strip():
                    f.close()
                    raise EmptyDatasetException("Dataset file contains no readable text content.")
                f.seek(0)
                return f, enc
            except UnicodeDecodeError:
                continue
            except EmptyDatasetException:
                raise
            except Exception as e:
                raise MalformedDatasetException(f"Failed to read dataset file: {e}") from e

        raise MalformedDatasetException("Unable to decode dataset file with supported character encodings.")

    def parse_headers_and_stream(self) -> tuple[list[str], Generator[list[Any], None, None]]:
        """Return (headers, row_generator) for the dataset."""
        if self.file_format == FileFormat.CSV.value:
            return self._parse_csv_stream()
        elif self.file_format == FileFormat.JSON.value:
            return self._parse_json_stream()
        elif self.file_format == FileFormat.XLSX.value:
            return self._parse_xlsx_stream()
        else:
            raise UnsupportedFileFormatException(self.file_format, list(SUPPORTED_EXTENSIONS.keys()))

    def _parse_csv_stream(self) -> tuple[list[str], Generator[list[Any], None, None]]:
        """Parse CSV file in streaming mode with delimiter sniffing."""
        f, encoding = self._open_text_file()
        sample = f.read(8192)
        f.seek(0)

        delimiter = ","
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample, delimiters=",;\t|")
            delimiter = dialect.delimiter
        except Exception:
            # Fallback delimiter detection
            if "\t" in sample and sample.count("\t") > sample.count(","):
                delimiter = "\t"
            elif ";" in sample and sample.count(";") > sample.count(","):
                delimiter = ";"
            elif "|" in sample and sample.count("|") > sample.count(","):
                delimiter = "|"

        reader = csv.reader(f, delimiter=delimiter)
        try:
            raw_headers = next(reader, None)
        except Exception as e:
            f.close()
            raise MalformedDatasetException(f"Failed to read CSV headers: {e}") from e

        if raw_headers is None or len(raw_headers) == 0:
            f.close()
            raise EmptyDatasetException("CSV file contains no rows or headers.")

        headers = self._clean_and_deduplicate_headers(raw_headers)

        def row_generator() -> Generator[list[Any], None, None]:
            try:
                for _line_num, row in enumerate(reader, start=2):
                    # Pad or slice to match header count
                    if len(row) < len(headers):
                        row = row + [""] * (len(headers) - len(row))
                    elif len(row) > len(headers):
                        row = row[: len(headers)]
                    yield row
            finally:
                f.close()

        return headers, row_generator()

    def _parse_json_stream(self) -> tuple[list[str], Generator[list[Any], None, None]]:
        """Parse JSON array of objects or JSON lines (NDJSON)."""
        f, _ = self._open_text_file()
        first_char = ""
        while True:
            ch = f.read(1)
            if not ch:
                break
            if not ch.isspace():
                first_char = ch
                break

        f.seek(0)

        if first_char == "[":
            # Standard JSON Array
            try:
                data = json.load(f)
            except Exception as e:
                f.close()
                raise MalformedDatasetException(f"Malformed JSON document: {e}") from e
            finally:
                f.close()

            if not isinstance(data, list):
                raise MalformedDatasetException("Root JSON payload must be an array of records.")

            if len(data) == 0:
                raise EmptyDatasetException("JSON array is empty (contains 0 records).")

            # Extract headers from first N records to preserve field ordering
            headers_dict: dict[str, None] = {}
            for item in data[:50]:
                if isinstance(item, dict):
                    for k in item:
                        headers_dict[str(k)] = None
                else:
                    raise MalformedDatasetException("JSON array elements must be objects/dictionaries.")

            headers = list(headers_dict.keys())
            if not headers:
                raise InvalidDatasetHeaderException("No valid column headers found in JSON records.")

            clean_headers = self._clean_and_deduplicate_headers(headers)

            def json_array_generator() -> Generator[list[Any], None, None]:
                for item in data:
                    if isinstance(item, dict):
                        yield [item.get(h, None) for h in clean_headers]

            return clean_headers, json_array_generator()

        else:
            # Assume JSON Lines (NDJSON)
            lines = f.readlines()
            f.close()
            if not lines:
                raise EmptyDatasetException("JSON Lines file contains no data.")

            records: list[dict[str, Any]] = []
            for i, line in enumerate(lines):
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    obj = json.loads(line_str)
                    if isinstance(obj, dict):
                        records.append(obj)
                    else:
                        raise MalformedDatasetException(f"Line {i + 1} is not a valid JSON object.")
                except json.JSONDecodeError as e:
                    raise MalformedDatasetException(f"Malformed JSON on line {i + 1}: {e}") from e

            if not records:
                raise EmptyDatasetException("JSON Lines file contained no valid JSON objects.")

            headers_dict = {}
            for item in records[:50]:
                for k in item:
                    headers_dict[str(k)] = None

            headers = list(headers_dict.keys())
            clean_headers = self._clean_and_deduplicate_headers(headers)

            def ndjson_generator() -> Generator[list[Any], None, None]:
                for item in records:
                    yield [item.get(h, None) for h in clean_headers]

            return clean_headers, ndjson_generator()

    def _parse_xlsx_stream(self) -> tuple[list[str], Generator[list[Any], None, None]]:
        """Parse Excel XLSX file using openpyxl in read-only mode."""
        try:
            import openpyxl
        except ImportError as e:
            raise MalformedDatasetException("openpyxl is required to parse Excel files.") from e

        try:
            wb = openpyxl.load_workbook(self.file_path, read_only=True, data_only=True)
            sheet = wb.active
            if sheet is None:
                wb.close()
                raise EmptyDatasetException("Excel workbook contains no active sheets.")

            row_iter = sheet.iter_rows(values_only=True)
            raw_headers = next(row_iter, None)
            if raw_headers is None:
                wb.close()
                raise EmptyDatasetException("Excel sheet contains no data.")

            headers = self._clean_and_deduplicate_headers([str(h or "") for h in raw_headers])

            def xlsx_generator() -> Generator[list[Any], None, None]:
                try:
                    for row in row_iter:
                        if row is None or all(c is None or str(c).strip() == "" for c in row):
                            continue
                        row_list = list(row)
                        if len(row_list) < len(headers):
                            row_list += [None] * (len(headers) - len(row_list))
                        else:
                            row_list = row_list[: len(headers)]
                        yield row_list
                finally:
                    wb.close()

            return headers, xlsx_generator()
        except EmptyDatasetException:
            raise
        except InvalidDatasetHeaderException:
            raise
        except Exception as e:
            raise MalformedDatasetException(f"Failed to parse Excel spreadsheet: {e}") from e

    def _clean_and_deduplicate_headers(self, raw_headers: list[Any]) -> list[str]:
        """Strip whitespace, reject empty header rows, and deduplicate duplicate column names."""
        cleaned = [str(h).strip() for h in raw_headers]
        if not cleaned or all(not h for h in cleaned):
            raise InvalidDatasetHeaderException("Header row contains only empty column names.")

        seen: dict[str, int] = {}
        unique_headers: list[str] = []
        for i, h in enumerate(cleaned):
            col_name = h if h else f"unnamed_column_{i + 1}"
            if col_name in seen:
                seen[col_name] += 1
                unique_headers.append(f"{col_name}_{seen[col_name]}")
            else:
                seen[col_name] = 0
                unique_headers.append(col_name)

        return unique_headers

    def get_preview(self, limit: int = 20) -> tuple[list[str], list[dict[str, Any]]]:
        """Read up to `limit` rows for visual inspection."""
        headers, generator = self.parse_headers_and_stream()
        rows: list[dict[str, Any]] = []
        for row in generator:
            row_dict: dict[str, Any] = {}
            for col, val in zip(headers, row, strict=False):
                row_dict[col] = val
            rows.append(row_dict)
            if len(rows) >= limit:
                break
        return headers, rows
