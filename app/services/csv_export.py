"""CSV export helpers. Text cells that a spreadsheet could run as a formula are neutralised."""
import csv
import io
from datetime import datetime
from decimal import Decimal

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r", "\n")


def safe_text(value: str) -> str:
    """Prefix a single quote when a text cell starts with a formula character."""
    return "'" + value if value.startswith(_FORMULA_STARTS) else value


def cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return safe_text(value)  # only free text is sanitised; numbers below are left alone
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def to_csv(header: list[str], rows) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([cell(v) for v in row])
    return buf.getvalue()
