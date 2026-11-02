from typing import Any, Literal

from toolpkg._bridge import call


def list_docs(folder: str | None = None) -> Any:
    """List documents with title, folder and last updated date, optionally for one folder only.
    """
    return call("list_docs", {"folder": folder})
