from typing import Any, Literal

from toolpkg._bridge import call


def update_deal(deal_id: str, stage: Literal['prospecting', 'qualified', 'proposal', 'negotiation', 'closed_won', 'closed_lost'] | None = None, amount: float | None = None, close_date: str | None = None, owner: str | None = None) -> Any:
    """Update fields on a deal and return the updated record.

    Only the fields provided are changed, and at least one is required. Moving a deal to
    'closed_won' or 'closed_lost' does not create any note, so add one with add_note if a reason
    should be recorded.

    Args:
        deal_id: ID of the deal to change.
        stage: New sales stage.
        amount: New expected value in US dollars. Must be greater than zero.
        close_date: New expected close date as an ISO date.
        owner: Full name of the sales rep who now owns the deal.
    """
    return call("update_deal", {"deal_id": deal_id, "stage": stage, "amount": amount, "close_date": close_date, "owner": owner})
