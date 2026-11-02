from typing import Any, Literal

from toolpkg._bridge import call


def list_deals(stage: Literal['prospecting', 'qualified', 'proposal', 'negotiation', 'closed_won', 'closed_lost'] | None = None, owner: str | None = None, contact_id: str | None = None, offset: int = 0, limit: int | None = None) -> Any:
    """List deals, optionally filtered by stage, owner or contact. When limit is omitted, all remaining deals are returned.
    """
    return call("list_deals", {"stage": stage, "owner": owner, "contact_id": contact_id, "offset": offset, "limit": limit})
