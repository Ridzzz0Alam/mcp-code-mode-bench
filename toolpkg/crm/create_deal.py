from typing import Any, Literal

from toolpkg._bridge import call


def create_deal(name: str, contact_id: str, amount: float, close_date: str, stage: Literal['prospecting', 'qualified', 'proposal', 'negotiation', 'closed_won', 'closed_lost'] = 'prospecting', owner: str | None = None) -> Any:
    """Create a deal linked to an existing contact and return it with its assigned deal ID.

    The deal takes its company from the linked contact. The contact must already exist, so create
    the contact first if necessary. Amounts are in US dollars and must be greater than zero, and
    the close date must be a valid ISO date. To change a deal after creating it, use update_deal.

    Args:
        name: Short descriptive name, for example 'Northwind Logistics renewal'.
        contact_id: ID of the existing contact who is the main point of contact for this deal.
        amount: Expected deal value in US dollars. Must be greater than zero.
        close_date: Expected close date as an ISO date, for example '2026-06-30'.
        stage: Current sales stage of the deal.
        owner: Full name of the sales rep who owns the deal. Defaults to the contact's owner when omitted.
    """
    return call("create_deal", {"name": name, "contact_id": contact_id, "amount": amount, "close_date": close_date, "stage": stage, "owner": owner})
