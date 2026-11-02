from typing import Any, Literal

from toolpkg._bridge import call


def get_contact(contact_id: str) -> Any:
    """Get one contact by ID.
    """
    return call("get_contact", {"contact_id": contact_id})
