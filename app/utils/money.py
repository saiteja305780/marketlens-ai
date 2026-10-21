from decimal import Decimal, InvalidOperation
from typing import Any


def to_decimal(value: Any) -> Decimal | None:
    """None stays None (missing). Garbage raises, so the record gets rejected."""
    if value is None:
        return None
    try:
        return Decimal(str(value).strip())  # str() avoids float artifacts
    except InvalidOperation:
        raise ValueError(f"unparseable price: {value!r}") from None