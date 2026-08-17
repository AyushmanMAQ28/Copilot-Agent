import csv
import io
from dataclasses import dataclass


class CSVValidationError(ValueError):
    pass


@dataclass
class LoadedCSV:
    headers: list[str]
    rows: list[dict[str, str]]
    text: str


def load_csv(raw: bytes, filename: str, max_bytes: int, max_rows: int) -> LoadedCSV:
    if not filename.lower().endswith(".csv"):
        raise CSVValidationError("Only .csv files are accepted")
    if not raw:
        raise CSVValidationError("The CSV file is empty")
    if len(raw) > max_bytes:
        raise CSVValidationError(f"CSV exceeds the {max_bytes} byte upload limit")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVValidationError("CSV must be UTF-8 encoded") from exc
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = [h.strip() for h in (reader.fieldnames or [])]
        if not headers or any(not h for h in headers):
            raise CSVValidationError("CSV must have non-empty header names")
        if len(headers) != len(set(headers)):
            raise CSVValidationError("CSV header names must be unique")
        rows = []
        for row in reader:
            if len(rows) >= max_rows:
                raise CSVValidationError(f"CSV exceeds the {max_rows} row limit")
            if None in row:
                raise CSVValidationError("CSV rows have more fields than the header")
            rows.append({key: (value or "").strip() for key, value in row.items()})
    except csv.Error as exc:
        raise CSVValidationError(f"Invalid CSV: {exc}") from exc
    if not rows:
        raise CSVValidationError("CSV must contain at least one data row")
    return LoadedCSV(headers=headers, rows=rows, text=text)
