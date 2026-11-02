from typing import Any, Literal

from toolpkg._bridge import call


def list_sheets() -> Any:
    """List every spreadsheet in the workspace with its title, row count and last modified date.
    """
    return call("list_sheets", {})
