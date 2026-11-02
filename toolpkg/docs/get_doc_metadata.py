from typing import Any, Literal

from toolpkg._bridge import call


def get_doc_metadata(doc_id: str) -> Any:
    """Get a document's title, folder, author, last updated date and length in characters.
    """
    return call("get_doc_metadata", {"doc_id": doc_id})
