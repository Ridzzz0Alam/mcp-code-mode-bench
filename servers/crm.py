"""Mock CRM MCP server. Reads and writes only the per-run state in MCP_STATE_DIR."""

from datetime import date
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from servers.state import FAKE_TODAY, dumps, load_crm, save_crm

Stage = Literal["prospecting", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]
Lifecycle = Literal["lead", "customer", "churned"]
Entity = Literal["contact", "deal"]

server = MCPServer("crm", log_level="ERROR")


def _find(crm: dict[str, Any], collection: str, key: str, value: str) -> dict[str, Any]:
    for record in crm[collection]:
        if record[key] == value:
            return record
    raise ToolError(f"No record with {key} '{value}'")


def _next_id(crm: dict[str, Any], kind: str, prefix: str) -> str:
    number = crm["next_ids"][kind]
    crm["next_ids"][kind] = number + 1
    return f"{prefix}-{number:04d}"


def _check_date(name: str, value: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"{name} must be an ISO date such as 2026-03-15") from None


def _check_page(offset: int, limit: int | None) -> None:
    if offset < 0:
        raise ToolError("offset must be 0 or greater")
    if limit is not None and limit < 1:
        raise ToolError("limit must be 1 or greater")


def _page(records: list[dict[str, Any]], offset: int, limit: int | None) -> list[dict[str, Any]]:
    return records[offset:] if limit is None else records[offset : offset + limit]


@server.tool(structured_output=False)
def list_contacts(company: str | None = None, owner: str | None = None, offset: int = 0, limit: int | None = None) -> str:
    """List contacts, optionally for one exact company or owner name. When limit is omitted, all remaining contacts are returned."""
    _check_page(offset, limit)
    contacts = [c for c in load_crm()["contacts"] if (company is None or c["company"] == company) and (owner is None or c["owner"] == owner)]
    return dumps({"total": len(contacts), "contacts": _page(contacts, offset, limit)})


@server.tool(structured_output=False)
def search_contacts(query: str) -> str:
    """Find contacts whose name, email or company contains the query text, ignoring case."""
    if not query.strip():
        raise ToolError("query must not be empty")
    needle = query.lower()
    return dumps({"contacts": [c for c in load_crm()["contacts"] if needle in f"{c['name']} {c['email']} {c['company']}".lower()]})


@server.tool(structured_output=False)
def get_contact(contact_id: str) -> str:
    """Get one contact by ID."""
    return dumps(_find(load_crm(), "contacts", "contact_id", contact_id))


@server.tool(structured_output=False)
def create_contact(
    name: Annotated[str, Field(description="Full name of the person, for example 'Ava Bennett'.")],
    email: Annotated[str, Field(description="Work email address. Must be unique across all contacts.")],
    company: Annotated[str, Field(description="Name of the company the person works for, spelled exactly as it should appear on their record.")],
    title: Annotated[str | None, Field(description="Job title, for example 'CFO'.")] = None,
    phone: Annotated[str | None, Field(description="Phone number in any format.")] = None,
    owner: Annotated[str | None, Field(description="Full name of the sales rep who owns this contact.")] = None,
    lifecycle_stage: Annotated[Lifecycle, Field(description="Where the contact is in the customer lifecycle.")] = "lead",
) -> str:
    """Create a new contact record and return it with its assigned contact ID.

    The email address must not already belong to another contact; a duplicate is rejected and no
    record is created. New contacts start with the lifecycle stage given here, which defaults to
    'lead'. To change an existing person's details, use update_contact instead.
    """
    if "@" not in email:
        raise ToolError("email must be a valid email address")
    crm = load_crm()
    if any(c["email"].lower() == email.lower() for c in crm["contacts"]):
        raise ToolError(f"A contact with email '{email}' already exists")
    contact = {
        "contact_id": _next_id(crm, "contact", "C"),
        "name": name,
        "email": email,
        "phone": phone,
        "title": title,
        "company": company,
        "owner": owner,
        "lifecycle_stage": lifecycle_stage,
        "created_at": FAKE_TODAY,
    }
    crm["contacts"].append(contact)
    save_crm(crm)
    return dumps(contact)


@server.tool(structured_output=False)
def update_contact(
    contact_id: str,
    title: str | None = None,
    phone: str | None = None,
    company: str | None = None,
    owner: str | None = None,
    lifecycle_stage: Lifecycle | None = None,
) -> str:
    """Update fields on a contact. Only the fields provided are changed, and at least one is required."""
    changes = {k: v for k, v in {"title": title, "phone": phone, "company": company, "owner": owner, "lifecycle_stage": lifecycle_stage}.items() if v is not None}
    crm = load_crm()
    contact = _find(crm, "contacts", "contact_id", contact_id)
    if not changes:
        raise ToolError("Provide at least one field to update")
    contact.update(changes)
    save_crm(crm)
    return dumps(contact)


@server.tool(structured_output=False)
def delete_contact(contact_id: str) -> str:
    """Delete a contact. Contacts that still have deals cannot be deleted."""
    crm = load_crm()
    contact = _find(crm, "contacts", "contact_id", contact_id)
    if any(d["contact_id"] == contact_id for d in crm["deals"]):
        raise ToolError(f"Contact '{contact_id}' still has deals")
    crm["contacts"].remove(contact)
    save_crm(crm)
    return dumps({"deleted": contact_id})


@server.tool(structured_output=False)
def list_deals(stage: Stage | None = None, owner: str | None = None, contact_id: str | None = None, offset: int = 0, limit: int | None = None) -> str:
    """List deals, optionally filtered by stage, owner or contact. When limit is omitted, all remaining deals are returned."""
    _check_page(offset, limit)
    deals = [
        d
        for d in load_crm()["deals"]
        if (stage is None or d["stage"] == stage) and (owner is None or d["owner"] == owner) and (contact_id is None or d["contact_id"] == contact_id)
    ]
    return dumps({"total": len(deals), "deals": _page(deals, offset, limit)})


@server.tool(structured_output=False)
def get_deal(deal_id: str) -> str:
    """Get one deal by ID."""
    return dumps(_find(load_crm(), "deals", "deal_id", deal_id))


@server.tool(structured_output=False)
def create_deal(
    name: Annotated[str, Field(description="Short descriptive name, for example 'Northwind Logistics renewal'.")],
    contact_id: Annotated[str, Field(description="ID of the existing contact who is the main point of contact for this deal.")],
    amount: Annotated[float, Field(description="Expected deal value in US dollars. Must be greater than zero.")],
    close_date: Annotated[str, Field(description="Expected close date as an ISO date, for example '2026-06-30'.")],
    stage: Annotated[Stage, Field(description="Current sales stage of the deal.")] = "prospecting",
    owner: Annotated[str | None, Field(description="Full name of the sales rep who owns the deal. Defaults to the contact's owner when omitted.")] = None,
) -> str:
    """Create a deal linked to an existing contact and return it with its assigned deal ID.

    The deal takes its company from the linked contact. The contact must already exist, so create
    the contact first if necessary. Amounts are in US dollars and must be greater than zero, and
    the close date must be a valid ISO date. To change a deal after creating it, use update_deal.
    """
    if amount <= 0:
        raise ToolError("amount must be greater than zero")
    _check_date("close_date", close_date)
    crm = load_crm()
    contact = _find(crm, "contacts", "contact_id", contact_id)
    deal = {
        "deal_id": _next_id(crm, "deal", "D"),
        "name": name,
        "company": contact["company"],
        "contact_id": contact_id,
        "owner": owner or contact["owner"],
        "stage": stage,
        "amount": amount,
        "close_date": close_date,
    }
    crm["deals"].append(deal)
    save_crm(crm)
    return dumps(deal)


@server.tool(structured_output=False)
def update_deal(
    deal_id: Annotated[str, Field(description="ID of the deal to change.")],
    stage: Annotated[Stage | None, Field(description="New sales stage.")] = None,
    amount: Annotated[float | None, Field(description="New expected value in US dollars. Must be greater than zero.")] = None,
    close_date: Annotated[str | None, Field(description="New expected close date as an ISO date.")] = None,
    owner: Annotated[str | None, Field(description="Full name of the sales rep who now owns the deal.")] = None,
) -> str:
    """Update fields on a deal and return the updated record.

    Only the fields provided are changed, and at least one is required. Moving a deal to
    'closed_won' or 'closed_lost' does not create any note, so add one with add_note if a reason
    should be recorded.
    """
    if amount is not None and amount <= 0:
        raise ToolError("amount must be greater than zero")
    if close_date is not None:
        _check_date("close_date", close_date)
    changes = {k: v for k, v in {"stage": stage, "amount": amount, "close_date": close_date, "owner": owner}.items() if v is not None}
    crm = load_crm()
    deal = _find(crm, "deals", "deal_id", deal_id)
    if not changes:
        raise ToolError("Provide at least one field to update")
    deal.update(changes)
    save_crm(crm)
    return dumps(deal)


@server.tool(structured_output=False)
def list_notes(entity_type: Entity, entity_id: str) -> str:
    """List the notes attached to a contact or deal, oldest first as stored."""
    return dumps({"notes": [n for n in load_crm()["notes"] if n["entity_type"] == entity_type and n["entity_id"] == entity_id]})


@server.tool(structured_output=False)
def add_note(entity_type: Entity, entity_id: str, body: str, author: str | None = None) -> str:
    """Attach a text note to an existing contact or deal."""
    if not body.strip():
        raise ToolError("body must not be empty")
    crm = load_crm()
    if entity_type == "contact":
        _find(crm, "contacts", "contact_id", entity_id)
    else:
        _find(crm, "deals", "deal_id", entity_id)
    note = {"note_id": _next_id(crm, "note", "N"), "entity_type": entity_type, "entity_id": entity_id, "body": body, "author": author, "created_at": FAKE_TODAY}
    crm["notes"].append(note)
    save_crm(crm)
    return dumps(note)


@server.tool(structured_output=False)
def list_tasks(assignee: str | None = None, status: Literal["open", "done"] | None = None) -> str:
    """List follow-up tasks, optionally for one assignee or status."""
    return dumps({"tasks": [t for t in load_crm()["tasks"] if (assignee is None or t["assignee"] == assignee) and (status is None or t["status"] == status)]})


@server.tool(structured_output=False)
def create_task(title: str, assignee: str, due_date: str, contact_id: str | None = None) -> str:
    """Create an open follow-up task for a person, optionally linked to an existing contact."""
    if not title.strip():
        raise ToolError("title must not be empty")
    _check_date("due_date", due_date)
    crm = load_crm()
    if contact_id is not None:
        _find(crm, "contacts", "contact_id", contact_id)
    task = {"task_id": _next_id(crm, "task", "T"), "title": title, "assignee": assignee, "due_date": due_date, "status": "open", "contact_id": contact_id, "created_at": FAKE_TODAY}
    crm["tasks"].append(task)
    save_crm(crm)
    return dumps(task)


if __name__ == "__main__":
    server.run()
