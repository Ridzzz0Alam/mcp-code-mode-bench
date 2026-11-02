from typing import Any, Literal

from toolpkg._bridge import call


def search_sheets(query: str) -> Any:
    """Find spreadsheets whose title or description contains the query text, ignoring case.
    """
    return call("search_sheets", {"query": query})
