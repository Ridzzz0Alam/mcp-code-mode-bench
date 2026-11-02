from typing import Any, Literal

from toolpkg._bridge import call


def list_folders() -> Any:
    """List document folders with the number of documents in each.
    """
    return call("list_folders", {})
