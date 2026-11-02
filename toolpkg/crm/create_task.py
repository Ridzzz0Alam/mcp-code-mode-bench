from typing import Any, Literal

from toolpkg._bridge import call


def create_task(title: str, assignee: str, due_date: str, contact_id: str | None = None) -> Any:
    """Create an open follow-up task for a person, optionally linked to an existing contact.
    """
    return call("create_task", {"title": title, "assignee": assignee, "due_date": due_date, "contact_id": contact_id})
