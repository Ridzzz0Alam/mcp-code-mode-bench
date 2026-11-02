from typing import Any, Literal

from toolpkg._bridge import call


def add_note(entity_type: Literal['contact', 'deal'], entity_id: str, body: str, author: str | None = None) -> Any:
    """Attach a text note to an existing contact or deal.
    """
    return call("add_note", {"entity_type": entity_type, "entity_id": entity_id, "body": body, "author": author})
