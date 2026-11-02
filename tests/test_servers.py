"""Every tool is exercised with normal and error input through an MCP client session."""

import csv
import io
import json
from pathlib import Path
from typing import Any, Callable

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from servers import crm, docs, sheets
from servers.state import load_crm, new_run_state, server_params

SERVERS = {"sheets": sheets.server, "docs": docs.server, "crm": crm.server}
CONTACT = {"name": "New Person", "email": "new.person@acme.example", "company": "Acme"}
Check = Callable[[Any], bool]


def _parsed(result: Any) -> Any:
    assert result.is_error is False, result.content
    assert len(result.content) == 1
    return result.content[0].text


async def call(server: MCPServer, tool: str, args: dict[str, Any]) -> Any:
    async with Client(server) as client:
        return await client.call_tool(tool, args)


# tool name -> (server, arguments, check on the decoded JSON result)
NORMAL: dict[str, tuple[str, dict[str, Any], Check]] = {
    "list_sheets": ("sheets", {}, lambda r: len(r["sheets"]) == 6),
    "search_sheets": ("sheets", {"query": "LEAD TIMES"}, lambda r: [s["sheet_id"] for s in r["sheets"]] == ["suppliers"]),
    "get_sheet_metadata": ("sheets", {"sheet_id": "returns"}, lambda r: r["row_count"] == 2000 and r["columns"][0] == {"name": "return_id", "type": "string"}),
    "read_rows": ("sheets", {"sheet_id": "orders", "offset": 9998}, lambda r: r["returned"] == 2 and r["rows"][1]["order_id"] == "O-10000"),
    "read_range": ("sheets", {"sheet_id": "orders", "start_row": 2, "end_row": 3, "columns": ["order_id"]}, lambda r: r["rows"] == [{"order_id": "O-00002"}, {"order_id": "O-00003"}]),
    "get_row": ("sheets", {"sheet_id": "sales_reps", "row_number": 1}, lambda r: r["rep_id"] == "R-001"),
    "get_cell": ("sheets", {"sheet_id": "sales_reps", "row_number": 2, "column": "rep_id"}, lambda r: r == {"value": "R-002"}),
    "get_column": ("sheets", {"sheet_id": "sales_reps", "column": "rep_id", "offset": 48}, lambda r: r["values"] == ["R-049", "R-050"]),
    "find_rows": ("sheets", {"sheet_id": "orders", "column": "order_id", "value": "o-00007"}, lambda r: r["total_matches"] == 1 and r["rows"][0]["row_number"] == 7),
    "list_folders": ("docs", {}, lambda r: {f["folder"]: f["doc_count"] for f in r["folders"]} == {"account-plans": 8, "meeting-notes": 40, "policies": 7}),
    "list_docs": ("docs", {"folder": "policies"}, lambda r: len(r["docs"]) == 7),
    "search_docs": ("docs", {"query": "refund", "folder": "policies", "limit": 1}, lambda r: r["results"][0]["title"] == "Refund policy" and "text" not in r["results"][0]),
    "get_doc": ("docs", {"doc_id": "DOC-P01"}, lambda r: r["text"].startswith("# Refund policy") and "## Exceptions" in r["text"]),
    "get_doc_metadata": ("docs", {"doc_id": "DOC-P01"}, lambda r: r["length_chars"] > 1000),
    "list_doc_sections": ("docs", {"doc_id": "DOC-M01"}, lambda r: [s["heading"] for s in r["sections"]] == ["Attendees", "Discussion", "Decisions", "Action items", "Parking lot"]),
    "get_doc_section": ("docs", {"doc_id": "DOC-M01", "heading": "action ITEMS"}, lambda r: r["heading"] == "Action items" and "(due " in r["body"]),
    "get_doc_comments": ("docs", {"doc_id": "DOC-M01"}, lambda r: r["comments"] == []),
    "list_contacts": ("crm", {"limit": 2, "offset": 1}, lambda r: r["total"] == 500 and [c["contact_id"] for c in r["contacts"]] == ["C-0002", "C-0003"]),
    "search_contacts": ("crm", {"query": ".EXAMPLE"}, lambda r: len(r["contacts"]) == 500),
    "get_contact": ("crm", {"contact_id": "C-0001"}, lambda r: r["contact_id"] == "C-0001"),
    "create_contact": ("crm", CONTACT, lambda r: r["contact_id"] == "C-0501" and r["created_at"] == "2026-03-15" and r["lifecycle_stage"] == "lead"),
    "update_contact": ("crm", {"contact_id": "C-0001", "title": "Chief Tester"}, lambda r: r["title"] == "Chief Tester"),
    "list_deals": ("crm", {"stage": "proposal", "limit": 1}, lambda r: r["total"] > 0 and r["deals"][0]["stage"] == "proposal"),
    "get_deal": ("crm", {"deal_id": "D-0001"}, lambda r: r["deal_id"] == "D-0001"),
    "create_deal": ("crm", {"name": "Pilot", "contact_id": "C-0001", "amount": 10.5, "close_date": "2026-06-30"}, lambda r: r["deal_id"] == "D-0301" and r["stage"] == "prospecting" and r["owner"]),
    "update_deal": ("crm", {"deal_id": "D-0001", "stage": "closed_won"}, lambda r: r["stage"] == "closed_won"),
    "list_notes": ("crm", {"entity_type": "deal", "entity_id": "D-0001"}, lambda r: r["notes"] == []),
    "add_note": ("crm", {"entity_type": "deal", "entity_id": "D-0001", "body": "Hello"}, lambda r: r["note_id"] == "N-0401"),
    "list_tasks": ("crm", {"status": "open"}, lambda r: r["tasks"] == []),
    "create_task": ("crm", {"title": "Call", "assignee": "Someone", "due_date": "2026-04-01"}, lambda r: r["task_id"] == "T-0001" and r["status"] == "open"),
}

# Each entry is checked separately because they do not decode to the common JSON shape or need setup.
SEPARATE = {"export_sheet_csv", "delete_contact"}

ERRORS: dict[str, tuple[str, dict[str, Any]]] = {
    "search_sheets": ("sheets", {}),
    "get_sheet_metadata": ("sheets", {"sheet_id": "nope"}),
    "read_rows": ("sheets", {"sheet_id": "orders", "limit": 0}),
    "read_range": ("sheets", {"sheet_id": "orders", "start_row": 5, "end_row": 2}),
    "get_row": ("sheets", {"sheet_id": "orders", "row_number": 10_001}),
    "get_cell": ("sheets", {"sheet_id": "orders", "row_number": 1, "column": "nope"}),
    "get_column": ("sheets", {"sheet_id": "orders", "column": "nope"}),
    "find_rows": ("sheets", {"sheet_id": "orders", "column": "status", "value": "x", "match": "regex"}),
    "export_sheet_csv": ("sheets", {"sheet_id": "nope"}),
    "list_docs": ("docs", {"folder": "nope"}),
    "search_docs": ("docs", {"query": "  "}),
    "get_doc": ("docs", {"doc_id": "nope"}),
    "get_doc_metadata": ("docs", {"doc_id": "nope"}),
    "list_doc_sections": ("docs", {"doc_id": "nope"}),
    "get_doc_section": ("docs", {"doc_id": "DOC-M01", "heading": "nope"}),
    "get_doc_comments": ("docs", {"doc_id": "nope"}),
    "list_contacts": ("crm", {"offset": -1}),
    "search_contacts": ("crm", {"query": ""}),
    "get_contact": ("crm", {"contact_id": "nope"}),
    "create_contact": ("crm", {**CONTACT, "email": "not-an-email"}),
    "update_contact": ("crm", {"contact_id": "C-0001"}),
    "delete_contact": ("crm", {"contact_id": "nope"}),
    "list_deals": ("crm", {"stage": "nope"}),
    "get_deal": ("crm", {"deal_id": "nope"}),
    "create_deal": ("crm", {"name": "x", "contact_id": "C-0001", "amount": 0, "close_date": "2026-06-30"}),
    "update_deal": ("crm", {"deal_id": "D-0001", "close_date": "soon"}),
    "list_notes": ("crm", {"entity_type": "nope", "entity_id": "x"}),
    "add_note": ("crm", {"entity_type": "contact", "entity_id": "nope", "body": "x"}),
    "list_tasks": ("crm", {"status": "nope"}),
    "create_task": ("crm", {"title": "x", "assignee": "y", "due_date": "soon"}),
}
# These take no arguments, so no input can be invalid.
NO_ERROR_CASE = {"list_sheets", "list_folders"}


async def test_cases_cover_every_tool() -> None:
    names: set[str] = set()
    for server in SERVERS.values():
        async with Client(server) as client:
            names |= {t.name for t in (await client.list_tools()).tools}
    assert len(names) == 32
    assert set(NORMAL) | SEPARATE == names
    assert set(ERRORS) | NO_ERROR_CASE == names


@pytest.mark.parametrize("tool", NORMAL)
async def test_normal_input(tool: str) -> None:
    server, args, check = NORMAL[tool]
    assert check(json.loads(_parsed(await call(SERVERS[server], tool, args))))


@pytest.mark.parametrize("tool", ERRORS)
async def test_error_input(tool: str) -> None:
    server, args = ERRORS[tool]
    assert (await call(SERVERS[server], tool, args)).is_error is True


async def test_read_rows_returns_everything_without_limit() -> None:
    result = json.loads(_parsed(await call(sheets.server, "read_rows", {"sheet_id": "orders"})))
    assert result["returned"] == result["total_rows"] == len(result["rows"]) == 10_000


async def test_export_csv_matches_rows(base_dir: Path) -> None:
    text = _parsed(await call(sheets.server, "export_sheet_csv", {"sheet_id": "sales_reps"}))
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 50
    assert rows[0]["rep_id"] == "R-001"


async def test_find_rows_contains_and_limit() -> None:
    result = json.loads(_parsed(await call(sheets.server, "find_rows", {"sheet_id": "inventory", "column": "category", "value": "NETWORK", "match": "contains", "limit": 3})))
    assert result["returned"] == 3
    assert result["total_matches"] > 3
    assert all(r["category"] == "Networking" for r in result["rows"])


async def test_find_rows_matches_booleans_as_text() -> None:
    result = json.loads(_parsed(await call(sheets.server, "find_rows", {"sheet_id": "suppliers", "column": "active", "value": "true", "limit": 1})))
    assert result["rows"][0]["active"] is True


async def test_no_server_side_aggregation_tools() -> None:
    async with Client(sheets.server) as client:
        names = [t.name for t in (await client.list_tools()).tools]
    assert not [n for n in names if any(word in n for word in ["sum", "avg", "group", "aggregate", "stat", "count", "query"])]


async def test_delete_contact() -> None:
    created = json.loads(_parsed(await call(crm.server, "create_contact", CONTACT)))
    assert json.loads(_parsed(await call(crm.server, "delete_contact", {"contact_id": created["contact_id"]}))) == {"deleted": created["contact_id"]}
    assert (await call(crm.server, "get_contact", {"contact_id": created["contact_id"]})).is_error is True


async def test_delete_contact_with_deals_is_rejected() -> None:
    linked = load_crm()["deals"][0]["contact_id"]
    assert (await call(crm.server, "delete_contact", {"contact_id": linked})).is_error is True
    assert any(c["contact_id"] == linked for c in load_crm()["contacts"])


async def test_duplicate_email_is_rejected() -> None:
    await call(crm.server, "create_contact", CONTACT)
    before = len(load_crm()["contacts"])
    assert (await call(crm.server, "create_contact", CONTACT)).is_error is True
    assert len(load_crm()["contacts"]) == before


async def test_writes_persist_to_state_but_not_base(base_dir: Path, run_state: Path) -> None:
    before = (base_dir / "crm.json").read_bytes()
    await call(crm.server, "create_contact", CONTACT)
    await call(crm.server, "update_deal", {"deal_id": "D-0001", "stage": "closed_lost"})
    state = json.loads((run_state / "crm.json").read_text())
    assert state["contacts"][-1]["email"] == CONTACT["email"]
    assert state["next_ids"]["contact"] == 502
    assert state["deals"][0]["stage"] == "closed_lost"
    assert (base_dir / "crm.json").read_bytes() == before


async def test_stdio_servers_expose_tools_and_isolate_state(base_dir: Path, tmp_path: Path) -> None:
    """Real subprocesses over stdio: writes in one run's state must not reach another's."""
    first, second = new_run_state(tmp_path / "a", base_dir), new_run_state(tmp_path / "b", base_dir)
    async with Client(server_params("crm", first, base_dir)) as one, Client(server_params("crm", second, base_dir)) as two:
        assert (await one.call_tool("create_contact", CONTACT)).is_error is False
        assert json.loads((await one.call_tool("get_contact", {"contact_id": "C-0501"})).content[0].text)["email"] == CONTACT["email"]
        assert (await two.call_tool("get_contact", {"contact_id": "C-0501"})).is_error is True
    assert len(json.loads((second / "crm.json").read_text())["contacts"]) == 500
    for name, count in [("sheets", 10), ("docs", 8)]:
        async with Client(server_params(name, first, base_dir)) as client:
            assert len((await client.list_tools()).tools) == count


def test_api_key_is_not_passed_to_servers(run_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp.client.stdio import get_default_environment

    monkeypatch.setenv("OPENCODE_API_KEY", "secret")
    params = server_params("crm", run_state)
    assert "OPENCODE_API_KEY" not in get_default_environment() | (params.env or {})
