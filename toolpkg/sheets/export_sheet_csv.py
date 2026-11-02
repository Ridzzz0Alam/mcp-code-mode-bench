from typing import Any, Literal

from toolpkg._bridge import call


def export_sheet_csv(sheet_id: str) -> Any:
    """Export a whole spreadsheet as CSV text with a header row.
    """
    return call("export_sheet_csv", {"sheet_id": sheet_id})
