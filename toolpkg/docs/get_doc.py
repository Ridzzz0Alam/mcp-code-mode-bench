from typing import Any, Literal

from toolpkg._bridge import call


def get_doc(doc_id: str) -> Any:
    """Get the full text of a document, including every section.
    """
    return call("get_doc", {"doc_id": doc_id})
