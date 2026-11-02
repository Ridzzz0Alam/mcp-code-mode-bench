from typing import Any, Literal

from toolpkg._bridge import call


def get_doc_section(doc_id: str, heading: str) -> Any:
    """Get one section of a document by its exact heading, ignoring case.
    """
    return call("get_doc_section", {"doc_id": doc_id, "heading": heading})
