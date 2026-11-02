from typing import Any, Literal

from toolpkg._bridge import call


def create_contact(name: str, email: str, company: str, title: str | None = None, phone: str | None = None, owner: str | None = None, lifecycle_stage: Literal['lead', 'customer', 'churned'] = 'lead') -> Any:
    """Create a new contact record and return it with its assigned contact ID.

    The email address must not already belong to another contact; a duplicate is rejected and no
    record is created. New contacts start with the lifecycle stage given here, which defaults to
    'lead'. To change an existing person's details, use update_contact instead.

    Args:
        name: Full name of the person, for example 'Ava Bennett'.
        email: Work email address. Must be unique across all contacts.
        company: Name of the company the person works for, spelled exactly as it should appear on their record.
        title: Job title, for example 'CFO'.
        phone: Phone number in any format.
        owner: Full name of the sales rep who owns this contact.
        lifecycle_stage: Where the contact is in the customer lifecycle.
    """
    return call("create_contact", {"name": name, "email": email, "company": company, "title": title, "phone": phone, "owner": owner, "lifecycle_stage": lifecycle_stage})
