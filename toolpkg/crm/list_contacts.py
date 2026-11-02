from typing import Any, Literal

from toolpkg._bridge import call


def list_contacts(company: str | None = None, owner: str | None = None, offset: int = 0, limit: int | None = None) -> Any:
    """List contacts, optionally for one exact company or owner name. When limit is omitted, all remaining contacts are returned.
    """
    return call("list_contacts", {"company": company, "owner": owner, "offset": offset, "limit": limit})
