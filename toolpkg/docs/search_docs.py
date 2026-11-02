from typing import Any, Literal

from toolpkg._bridge import call


def search_docs(query: str, folder: str | None = None, limit: int = 10) -> Any:
    """Search documents by keyword and return the best matches with a short snippet of matching text.

    Documents are ranked by how many times the query words occur, with occurrences in the title
    counted more heavily, and ties are broken by document ID. Each result contains the document ID,
    title, folder, last updated date, match score, and a snippet around the first match. The full
    text is not included; use get_doc or get_doc_section to read a result.

    Args:
        query: Words to look for. A document matches when its title or text contains at least one of them, ignoring case.
        folder: Restrict the search to this folder, as returned by list_folders. Searches all folders when omitted.
        limit: Maximum number of documents to return, from 1 to 50.
    """
    return call("search_docs", {"query": query, "folder": folder, "limit": limit})
