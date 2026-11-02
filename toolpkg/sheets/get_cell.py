from typing import Any, Literal

from toolpkg._bridge import call


def get_cell(sheet_id: str, row_number: int, column: str) -> Any:
    """Get a single cell value by row number, counted from 1, and column name.
    """
    return call("get_cell", {"sheet_id": sheet_id, "row_number": row_number, "column": column})
