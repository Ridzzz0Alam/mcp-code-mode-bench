from typing import Any, Literal

from toolpkg._bridge import call


def get_sheet_metadata(sheet_id: str) -> Any:
    """Get a spreadsheet's description, column names and types, row count and last modified date.
    """
    return call("get_sheet_metadata", {"sheet_id": sheet_id})
