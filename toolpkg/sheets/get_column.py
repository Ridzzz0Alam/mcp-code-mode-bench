from typing import Any, Literal

from toolpkg._bridge import call


def get_column(sheet_id: str, column: str, offset: int = 0, limit: int | None = None) -> Any:
    """Get the values of one column in row order. When limit is omitted, all remaining values are returned.
    """
    return call("get_column", {"sheet_id": sheet_id, "column": column, "offset": offset, "limit": limit})
