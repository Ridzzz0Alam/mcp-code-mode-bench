from typing import Any, Literal

from toolpkg._bridge import call


def search_contacts(query: str) -> Any:
    """Find contacts whose name, email or company contains the query text, ignoring case.
    """
    return call("search_contacts", {"query": query})
