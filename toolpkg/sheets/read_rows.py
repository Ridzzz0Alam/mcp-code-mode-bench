from typing import Any, Literal

from toolpkg._bridge import call


def read_rows(sheet_id: str, offset: int = 0, limit: int | None = None) -> Any:
    """Read rows from a spreadsheet as a list of objects keyed by column name.

    Rows are returned in the order they are stored in the sheet, and each row contains all of the
    sheet's columns. The response also reports the total number of rows in the sheet and how many
    rows were returned, so a caller can tell whether more rows exist after this range. When limit
    is omitted, the response contains every row from offset to the end of the sheet, whatever the
    size of the sheet. An offset past the end of the sheet returns an empty list and is not an
    error. Values keep the type declared in the sheet's column metadata: dates are ISO 8601
    strings, and booleans and numbers are JSON booleans and numbers.

    Args:
        sheet_id: Identifier of the spreadsheet, as returned by list_sheets, for example 'orders'.
        offset: Zero-based index of the first row to return. Defaults to the first row of the sheet.
        limit: Maximum number of rows to return. When omitted, every row from offset to the end of the sheet is returned.
    """
    return call("read_rows", {"sheet_id": sheet_id, "offset": offset, "limit": limit})
