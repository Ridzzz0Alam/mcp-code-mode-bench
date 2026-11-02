"""Mock spreadsheet MCP server. Read-only, with no server-side aggregation by design."""

import csv
import io
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from servers.state import dumps, read_base

SHEET_IDS = ["orders", "customers", "inventory", "returns", "suppliers", "sales_reps"]

server = MCPServer("sheets", log_level="ERROR")


def _sheet(sheet_id: str) -> dict[str, Any]:
    if sheet_id not in SHEET_IDS:
        raise ToolError(f"Unknown sheet_id '{sheet_id}'. Known sheets: {', '.join(SHEET_IDS)}")
    return read_base(f"sheets/{sheet_id}.json")


def _column_names(sheet: dict[str, Any]) -> list[str]:
    return [column["name"] for column in sheet["columns"]]


def _check_columns(sheet: dict[str, Any], columns: list[str]) -> None:
    unknown = [c for c in columns if c not in _column_names(sheet)]
    if unknown:
        raise ToolError(f"Unknown column(s) {unknown} in sheet '{sheet['id']}'")


def _check_page(offset: int, limit: int | None) -> None:
    if offset < 0:
        raise ToolError("offset must be 0 or greater")
    if limit is not None and limit < 1:
        raise ToolError("limit must be 1 or greater")


def _row(sheet: dict[str, Any], row_number: int) -> dict[str, Any]:
    if not 1 <= row_number <= len(sheet["rows"]):
        raise ToolError(f"row_number must be between 1 and {len(sheet['rows'])}")
    return sheet["rows"][row_number - 1]


def _summary(sheet: dict[str, Any]) -> dict[str, Any]:
    return {"sheet_id": sheet["id"], "title": sheet["title"], "row_count": len(sheet["rows"]), "modified": sheet["modified"]}


def _cell_text(value: Any) -> str:
    return str(value).lower()


@server.tool(structured_output=False)
def list_sheets() -> str:
    """List every spreadsheet in the workspace with its title, row count and last modified date."""
    return dumps({"sheets": [_summary(_sheet(s)) for s in SHEET_IDS]})


@server.tool(structured_output=False)
def search_sheets(query: str) -> str:
    """Find spreadsheets whose title or description contains the query text, ignoring case."""
    needle = query.lower()
    sheets = [_sheet(s) for s in SHEET_IDS]
    return dumps({"sheets": [_summary(s) for s in sheets if needle in s["title"].lower() or needle in s["description"].lower()]})


@server.tool(structured_output=False)
def get_sheet_metadata(sheet_id: str) -> str:
    """Get a spreadsheet's description, column names and types, row count and last modified date."""
    sheet = _sheet(sheet_id)
    return dumps({**_summary(sheet), "description": sheet["description"], "columns": sheet["columns"]})


@server.tool(structured_output=False)
def read_rows(
    sheet_id: Annotated[str, Field(description="Identifier of the spreadsheet, as returned by list_sheets, for example 'orders'.")],
    offset: Annotated[int, Field(description="Zero-based index of the first row to return. Defaults to the first row of the sheet.")] = 0,
    limit: Annotated[int | None, Field(description="Maximum number of rows to return. When omitted, every row from offset to the end of the sheet is returned.")] = None,
) -> str:
    """Read rows from a spreadsheet as a list of objects keyed by column name.

    Rows are returned in the order they are stored in the sheet, and each row contains all of the
    sheet's columns. The response also reports the total number of rows in the sheet and how many
    rows were returned, so a caller can tell whether more rows exist after this range. When limit
    is omitted, the response contains every row from offset to the end of the sheet, whatever the
    size of the sheet. An offset past the end of the sheet returns an empty list and is not an
    error. Values keep the type declared in the sheet's column metadata: dates are ISO 8601
    strings, and booleans and numbers are JSON booleans and numbers.
    """
    sheet = _sheet(sheet_id)
    _check_page(offset, limit)
    rows = sheet["rows"][offset:] if limit is None else sheet["rows"][offset : offset + limit]
    return dumps({"sheet_id": sheet_id, "offset": offset, "returned": len(rows), "total_rows": len(sheet["rows"]), "rows": rows})


@server.tool(structured_output=False)
def read_range(sheet_id: str, start_row: int, end_row: int, columns: list[str] | None = None) -> str:
    """Read an inclusive range of rows, numbered from 1, optionally keeping only the named columns."""
    sheet = _sheet(sheet_id)
    if start_row < 1 or end_row < start_row:
        raise ToolError("start_row must be at least 1 and end_row must not be before start_row")
    _check_columns(sheet, columns or [])
    rows = sheet["rows"][start_row - 1 : end_row]
    if columns:
        rows = [{c: row[c] for c in columns} for row in rows]
    return dumps({"sheet_id": sheet_id, "start_row": start_row, "returned": len(rows), "rows": rows})


@server.tool(structured_output=False)
def get_row(sheet_id: str, row_number: int) -> str:
    """Get one row by its row number, counted from 1."""
    return dumps(_row(_sheet(sheet_id), row_number))


@server.tool(structured_output=False)
def get_cell(sheet_id: str, row_number: int, column: str) -> str:
    """Get a single cell value by row number, counted from 1, and column name."""
    sheet = _sheet(sheet_id)
    _check_columns(sheet, [column])
    return dumps({"value": _row(sheet, row_number)[column]})


@server.tool(structured_output=False)
def get_column(sheet_id: str, column: str, offset: int = 0, limit: int | None = None) -> str:
    """Get the values of one column in row order. When limit is omitted, all remaining values are returned."""
    sheet = _sheet(sheet_id)
    _check_columns(sheet, [column])
    _check_page(offset, limit)
    rows = sheet["rows"][offset:] if limit is None else sheet["rows"][offset : offset + limit]
    return dumps({"sheet_id": sheet_id, "column": column, "offset": offset, "returned": len(rows), "values": [row[column] for row in rows]})


@server.tool(structured_output=False)
def find_rows(
    sheet_id: Annotated[str, Field(description="Identifier of the spreadsheet to search, as returned by list_sheets.")],
    column: Annotated[str, Field(description="Name of the single column to compare. Must be one of the sheet's columns.")],
    value: Annotated[str, Field(description="Text to compare against the cell. Numbers and booleans are compared by their text form, such as '42' or 'true'.")],
    match: Annotated[Literal["exact", "contains"], Field(description="'exact' requires the whole cell to equal value; 'contains' accepts value anywhere in the cell. Both ignore case.")] = "exact",
    limit: Annotated[int | None, Field(description="Maximum number of matching rows to return. When omitted, all matching rows are returned.")] = None,
) -> str:
    """Find rows where one column matches a value, returned as full rows in sheet order.

    The comparison applies to one column at a time and ignores case. The response reports how many
    rows matched in total, even when limit caps the rows returned. Each returned row also includes
    its row_number, counted from 1, for use with get_row and get_cell.
    """
    sheet = _sheet(sheet_id)
    _check_columns(sheet, [column])
    _check_page(0, limit)
    needle = value.lower()
    matches = []
    for number, row in enumerate(sheet["rows"], start=1):
        text = _cell_text(row[column])
        if text == needle or (match == "contains" and needle in text):
            matches.append({"row_number": number, **row})
    rows = matches if limit is None else matches[:limit]
    return dumps({"sheet_id": sheet_id, "total_matches": len(matches), "returned": len(rows), "rows": rows})


@server.tool(structured_output=False)
def export_sheet_csv(sheet_id: str) -> str:
    """Export a whole spreadsheet as CSV text with a header row."""
    sheet = _sheet(sheet_id)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_column_names(sheet), lineterminator="\n")
    writer.writeheader()
    writer.writerows(sheet["rows"])
    return buffer.getvalue()


if __name__ == "__main__":
    server.run()
