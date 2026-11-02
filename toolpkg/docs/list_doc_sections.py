from typing import Any, Literal

from toolpkg._bridge import call


def list_doc_sections(doc_id: str) -> Any:
    """List a document's section headings in order, with each section's length in characters.
    """
    return call("list_doc_sections", {"doc_id": doc_id})
