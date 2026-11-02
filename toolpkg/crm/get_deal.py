from typing import Any, Literal

from toolpkg._bridge import call


def get_deal(deal_id: str) -> Any:
    """Get one deal by ID.
    """
    return call("get_deal", {"deal_id": deal_id})
