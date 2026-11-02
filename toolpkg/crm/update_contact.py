from typing import Any, Literal

from toolpkg._bridge import call


def update_contact(contact_id: str, title: str | None = None, phone: str | None = None, company: str | None = None, owner: str | None = None, lifecycle_stage: Literal['lead', 'customer', 'churned'] | None = None) -> Any:
    """Update fields on a contact. Only the fields provided are changed, and at least one is required.
    """
    return call("update_contact", {"contact_id": contact_id, "title": title, "phone": phone, "company": company, "owner": owner, "lifecycle_stage": lifecycle_stage})
