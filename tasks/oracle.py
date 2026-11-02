"""Scripted, LLM-free solutions that reach the data only through the MCP tools.

Answers are computed here independently of tasks/build_tasks.py, so a passing oracle means two
separate implementations agree. Each solver returns the final message an agent would send.
"""

import json
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

from servers.client import ToolClient

Solver = Callable[[ToolClient, dict[str, Any]], Awaitable[str]]
SOLVERS: dict[str, Solver] = {}
ACTION_ITEM = re.compile(r"^- (.+?): (.+) \(due (\d{4}-\d{2}-\d{2})\)$", re.MULTILINE)
STAKEHOLDER = re.compile(r"^- (.+?), (.+?), (\S+@\S+)$", re.MULTILINE)


def solver(task_id: str) -> Callable[[Solver], Solver]:
    def register(function: Solver) -> Solver:
        SOLVERS[task_id] = function
        return function

    return register


async def _call(tools: ToolClient, tool: str, /, **arguments: Any) -> Any:
    result = await tools.call(tool, arguments)
    if result.is_error:
        raise RuntimeError(f"{tool} failed: {result.text}")
    return json.loads(result.text)


async def _rows(tools: ToolClient, sheet_id: str) -> list[dict[str, Any]]:
    return (await _call(tools, "read_rows", sheet_id=sheet_id))["rows"]


async def _doc_id(tools: ToolClient, title: str) -> str:
    docs = (await _call(tools, "list_docs"))["docs"]
    return next(d["doc_id"] for d in docs if d["title"] == title)


async def _section(tools: ToolClient, doc_id: str, heading: str) -> str:
    return (await _call(tools, "get_doc_section", doc_id=doc_id, heading=heading))["body"]


def _answer(value: Any) -> str:
    return f"Here is the result. <answer>{value}</answer>"


def _top(totals: dict[str, float]) -> str:
    return max(totals, key=lambda key: totals[key])


async def _completed(tools: ToolClient) -> list[dict[str, Any]]:
    return [o for o in await _rows(tools, "orders") if o["status"] == "completed"]


@solver("L01")
async def _l01(tools: ToolClient, params: dict[str, Any]) -> str:
    total = sum(o["total"] for o in await _completed(tools) if o["region"] == "EMEA" and o["order_date"][5:7] in ("07", "08", "09"))
    return _answer(f"${total:,.2f}")


@solver("L02")
async def _l02(tools: ToolClient, params: dict[str, Any]) -> str:
    return _answer(len([o for o in await _rows(tools, "orders") if o["region"] == "APAC" and o["channel"] == "partner" and o["discount_pct"] >= 15 and o["status"] != "pending" and o["status"] != "cancelled" and o["status"] != "refunded"]))


@solver("L03")
async def _l03(tools: ToolClient, params: dict[str, Any]) -> str:
    names = {r["rep_id"]: r["name"] for r in await _rows(tools, "sales_reps") if r["region"] == "LATAM"}
    totals: dict[str, float] = defaultdict(float)
    for order in await _completed(tools):
        if order["rep_id"] in names:
            totals[order["rep_id"]] += order["total"]
    return _answer(names[_top(totals)])


@solver("L04")
async def _l04(tools: ToolClient, params: dict[str, Any]) -> str:
    totals: dict[str, int] = defaultdict(int)
    for order in await _rows(tools, "orders"):
        if order["status"] != "cancelled":
            totals[order["sku"]] += order["quantity"]
    return _answer(", ".join(sorted(totals, key=lambda sku: -totals[sku])[:5]))


@solver("L05")
async def _l05(tools: ToolClient, params: dict[str, Any]) -> str:
    rows = (await _call(tools, "find_rows", sheet_id="inventory", column="warehouse", value="Rotterdam"))["rows"]
    return _answer("\n".join(f"- {r['sku']}" for r in rows if r["category"] == "Networking" and not r["discontinued"] and r["stock_on_hand"] < r["reorder_point"]))


@solver("L06")
async def _l06(tools: ToolClient, params: dict[str, Any]) -> str:
    totals: dict[str, float] = defaultdict(float)
    for item in await _rows(tools, "inventory"):
        if not item["discontinued"]:
            totals[item["warehouse"]] += item["stock_on_hand"] * item["unit_cost"]
    return _answer(_top(totals))


@solver("L07")
async def _l07(tools: ToolClient, params: dict[str, Any]) -> str:
    wanted = {c["customer_id"] for c in await _rows(tools, "customers") if c["country"] == "Germany" and c["segment"] == "enterprise"}
    return _answer(round(sum(o["total"] for o in await _completed(tools) if o["customer_id"] in wanted), 2))


@solver("L08")
async def _l08(tools: ToolClient, params: dict[str, Any]) -> str:
    totals: dict[str, float] = defaultdict(float)
    for order in await _rows(tools, "orders"):
        if order["status"] in ("completed", "shipped"):
            totals[order["customer_id"]] += order["total"]
    return _answer(_top(totals))


@solver("L09")
async def _l09(tools: ToolClient, params: dict[str, Any]) -> str:
    channels = {o["order_id"]: o["channel"] for o in await _rows(tools, "orders")}
    totals: dict[str, float] = defaultdict(float)
    for item in await _rows(tools, "returns"):
        totals[channels[item["order_id"]]] += item["refund_amount"]
    return _answer(_top(totals))


@solver("L10")
async def _l10(tools: ToolClient, params: dict[str, Any]) -> str:
    inactive = {r["supplier_id"] for r in (await _call(tools, "find_rows", sheet_id="suppliers", column="active", value="false"))["rows"]}
    return _answer(len([i for i in await _rows(tools, "inventory") if not i["discontinued"] and i["stock_on_hand"] > 0 and i["supplier_id"] in inactive]))


@solver("L11")
async def _l11(tools: ToolClient, params: dict[str, Any]) -> str:
    totals: dict[str, float] = defaultdict(float)
    for order in await _completed(tools):
        totals[order["order_date"][:7]] += order["total"]
    return _answer(_top(totals))


@solver("L12")
async def _l12(tools: ToolClient, params: dict[str, Any]) -> str:
    totals: dict[str, float] = defaultdict(float)
    for order in await _completed(tools):
        totals[order["rep_id"]] += order["total"]
    return _answer(len([r for r in await _rows(tools, "sales_reps") if totals[r["rep_id"]] >= r["quota_2025"]]))


async def _items_to_tasks(tools: ToolClient, title: str) -> None:
    body = await _section(tools, await _doc_id(tools, title), "Action items")
    for owner, description, due in ACTION_ITEM.findall(body):
        await _call(tools, "create_task", title=description, assignee=owner, due_date=due)


@solver("M01")
@solver("M02")
@solver("M03")
async def _meeting_items(tools: ToolClient, params: dict[str, Any]) -> str:
    await _items_to_tasks(tools, params["title"])
    return "Done."


async def _add_stakeholders(tools: ToolClient, doc_id: str, company: str) -> dict[str, str]:
    created = {}
    for name, title, email in STAKEHOLDER.findall(await _section(tools, doc_id, "Key stakeholders")):
        created[name] = (await _call(tools, "create_contact", name=name, email=email, company=company, title=title))["contact_id"]
    return created


@solver("M04")
async def _m04(tools: ToolClient, params: dict[str, Any]) -> str:
    await _add_stakeholders(tools, await _doc_id(tools, params["title"]), params["company"])
    return "Done."


@solver("M05")
async def _m05(tools: ToolClient, params: dict[str, Any]) -> str:
    doc_id = await _doc_id(tools, params["title"])
    created = await _add_stakeholders(tools, doc_id, params["company"])
    amount, stage, close = re.fullmatch(r"Amount: (\d+) USD\. Stage: (\w+)\. Expected close: ([\d-]+)\.", await _section(tools, doc_id, "Proposed deal")).groups()
    await _call(tools, "create_deal", name=f"{params['company']} proposed deal", contact_id=created[params["lead"]], amount=float(amount), stage=stage, close_date=close)
    return "Done."


async def _policy_value(tools: ToolClient, query: str, label: str) -> int:
    found = (await _call(tools, "search_docs", query=query, folder="policies", limit=1))["results"][0]
    text = (await _call(tools, "get_doc", doc_id=found["doc_id"]))["text"]
    return int(re.search(rf"The value of {label} is (\d+)\.", text).group(1))


@solver("M06")
async def _m06(tools: ToolClient, params: dict[str, Any]) -> str:
    limit = await _policy_value(tools, "discount approval", "rep max discount pct")
    contact = (await _call(tools, "search_contacts", query=params["contact"]))["contacts"][0]
    await _call(tools, "add_note", entity_type="contact", entity_id=contact["contact_id"], body=f"Reps can give up to {limit}% discount.")
    return "Done."


@solver("M07")
async def _m07(tools: ToolClient, params: dict[str, Any]) -> str:
    for deal in (await _call(tools, "list_deals", owner=params["owner"], stage="negotiation"))["deals"]:
        if deal["close_date"] < "2025-07-01":
            await _call(tools, "update_deal", deal_id=deal["deal_id"], stage="closed_lost")
            await _call(tools, "add_note", entity_type="deal", entity_id=deal["deal_id"], body="This deal lapsed.")
    return "Done."


async def _top_quota(tools: ToolClient, region: str) -> str:
    reps = (await _call(tools, "find_rows", sheet_id="sales_reps", column="region", value=region))["rows"]
    return max(reps, key=lambda r: r["quota_2025"])["name"]


@solver("M08")
async def _m08(tools: ToolClient, params: dict[str, Any]) -> str:
    owner = await _top_quota(tools, "APAC")
    for contact in (await _call(tools, "list_contacts", company=params["company"]))["contacts"]:
        await _call(tools, "update_contact", contact_id=contact["contact_id"], owner=owner)
    return "Done."


@solver("M09")
async def _m09(tools: ToolClient, params: dict[str, Any]) -> str:
    owner = await _top_quota(tools, "EMEA")
    days = await _policy_value(tools, "refund policy", "refund window days")
    await _call(tools, "create_task", title="Review refund window", assignee=owner, due_date=(date(2026, 3, 15) + timedelta(days=days)).isoformat())
    return "Done."


@solver("M10")
async def _m10(tools: ToolClient, params: dict[str, Any]) -> str:
    for doc in (await _call(tools, "list_docs", folder="meeting-notes"))["docs"]:
        for owner, description, due in ACTION_ITEM.findall(await _section(tools, doc["doc_id"], "Action items")):
            if owner == params["person"]:
                await _call(tools, "create_task", title=description, assignee=owner, due_date=due)
    return "Done."


@solver("S01")
async def _s01(tools: ToolClient, params: dict[str, Any]) -> str:
    return _answer((await _call(tools, "find_rows", sheet_id="sales_reps", column="rep_id", value="R-017"))["rows"][0]["quota_2025"])


@solver("S02")
async def _s02(tools: ToolClient, params: dict[str, Any]) -> str:
    return _answer((await _call(tools, "get_sheet_metadata", sheet_id="inventory"))["row_count"])


@solver("S03")
async def _s03(tools: ToolClient, params: dict[str, Any]) -> str:
    return _answer((await _call(tools, "find_rows", sheet_id="orders", column="order_id", value="O-04321"))["rows"][0]["status"])


@solver("S04")
async def _s04(tools: ToolClient, params: dict[str, Any]) -> str:
    return _answer(await _policy_value(tools, "refund policy", "refund window days"))


@solver("S05")
async def _s05(tools: ToolClient, params: dict[str, Any]) -> str:
    return _answer((await _call(tools, "get_contact", contact_id="C-0123"))["email"])


@solver("S06")
async def _s06(tools: ToolClient, params: dict[str, Any]) -> str:
    return _answer((await _call(tools, "get_deal", deal_id="D-0042"))["stage"])


@solver("S07")
async def _s07(tools: ToolClient, params: dict[str, Any]) -> str:
    await _call(tools, "update_contact", contact_id="C-0200", title="Director of Operations")
    return "Done."


@solver("S08")
async def _s08(tools: ToolClient, params: dict[str, Any]) -> str:
    await _call(tools, "add_note", entity_type="deal", entity_id="D-0100", body="Customer asked for a revised quote")
    return "Done."
