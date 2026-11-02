from typing import Any, Literal

from toolpkg._bridge import call


def get_row(sheet_id: str, row_number: int) -> Any:
    """Get one row by its row number, counted from 1.
    """
    return call("get_row", {"sheet_id": sheet_id, "row_number": row_number})
