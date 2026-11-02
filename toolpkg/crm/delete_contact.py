from typing import Any, Literal

from toolpkg._bridge import call


def delete_contact(contact_id: str) -> Any:
    """Delete a contact. Contacts that still have deals cannot be deleted.
    """
    return call("delete_contact", {"contact_id": contact_id})
