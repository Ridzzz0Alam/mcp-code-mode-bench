from typing import Any, Literal

from toolpkg._bridge import call


def list_tasks(assignee: str | None = None, status: Literal['open', 'done'] | None = None) -> Any:
    """List follow-up tasks, optionally for one assignee or status.
    """
    return call("list_tasks", {"assignee": assignee, "status": status})
