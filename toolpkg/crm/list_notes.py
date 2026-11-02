from typing import Any, Literal

from toolpkg._bridge import call


def list_notes(entity_type: Literal['contact', 'deal'], entity_id: str) -> Any:
    """List the notes attached to a contact or deal, oldest first as stored.
    """
    return call("list_notes", {"entity_type": entity_type, "entity_id": entity_id})
