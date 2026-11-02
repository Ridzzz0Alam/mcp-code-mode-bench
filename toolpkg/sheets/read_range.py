from typing import Any, Literal

from toolpkg._bridge import call


def read_range(sheet_id: str, start_row: int, end_row: int, columns: list[str] | None = None) -> Any:
    """Read an inclusive range of rows, numbered from 1, optionally keeping only the named columns.
    """
    return call("read_range", {"sheet_id": sheet_id, "start_row": start_row, "end_row": end_row, "columns": columns})
