from typing import Any, Literal

from toolpkg._bridge import call


def get_doc_comments(doc_id: str) -> Any:
    """Get the review comments left on a document.
    """
    return call("get_doc_comments", {"doc_id": doc_id})
