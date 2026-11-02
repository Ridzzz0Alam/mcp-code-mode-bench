from typing import Any, Literal

from toolpkg._bridge import call


def find_rows(sheet_id: str, column: str, value: str, match: Literal['exact', 'contains'] = 'exact', limit: int | None = None) -> Any:
    """Find rows where one column matches a value, returned as full rows in sheet order.

    The comparison applies to one column at a time and ignores case. The response reports how many
    rows matched in total, even when limit caps the rows returned. Each returned row also includes
    its row_number, counted from 1, for use with get_row and get_cell.

    Args:
        sheet_id: Identifier of the spreadsheet to search, as returned by list_sheets.
        column: Name of the single column to compare. Must be one of the sheet's columns.
        value: Text to compare against the cell. Numbers and booleans are compared by their text form, such as '42' or 'true'.
        match: 'exact' requires the whole cell to equal value; 'contains' accepts value anywhere in the cell. Both ignore case.
        limit: Maximum number of matching rows to return. When omitted, all matching rows are returned.
    """
    return call("find_rows", {"sheet_id": sheet_id, "column": column, "value": value, "match": match, "limit": limit})
