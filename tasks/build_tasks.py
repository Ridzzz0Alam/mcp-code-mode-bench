"""Compute every task's expected result from the generated data and write tasks/tasks.jsonl.

Usage: uv run python tasks/build_tasks.py
`params` holds inputs for tasks/oracle.py only. The agents receive nothing but `prompt`.
"""

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TASKS_PATH = ROOT / "tasks" / "tasks.jsonl"
FAKE_TODAY = date(2026, 3, 15)


def _best(totals: dict[str, float], count: int = 1) -> list[str]:
    """Top keys by value. Raises on a tie, because a tied task would have no single right answer."""
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    for (_, a), (_, b) in zip(ranked[: count + 1], ranked[1 : count + 1]):
        if abs(a - b) < 0.01:
            raise ValueError(f"Tie in ranking: {ranked[: count + 1]}")
    return [key for key, _ in ranked[:count]]


def _sum_by(rows: Iterable[dict[str, Any]], key: str, value: str) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[row[key]] += row[value]
    return dict(totals)


def _money(value: float) -> dict[str, float]:
    return {"value": round(value, 2), "tolerance": 0.01}


def _count(value: int) -> dict[str, float]:
    return {"value": value, "tolerance": 0}


def large_data_tasks(sheets: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    orders, customers, inventory = sheets["orders"], sheets["customers"], sheets["inventory"]
    returns, suppliers, reps = sheets["returns"], sheets["suppliers"], sheets["sales_reps"]
    completed = [o for o in orders if o["status"] == "completed"]
    german_enterprise = {c["customer_id"] for c in customers if c["country"] == "Germany" and c["segment"] == "enterprise"}
    inactive_suppliers = {s["supplier_id"] for s in suppliers if not s["active"]}
    order_channel = {o["order_id"]: o["channel"] for o in orders}
    rep_totals = _sum_by(completed, "rep_id", "total")
    rep_names = {r["rep_id"]: r["name"] for r in reps}
    latam_reps = {r["rep_id"] for r in reps if r["region"] == "LATAM"}
    months: dict[str, float] = defaultdict(float)
    for order in completed:
        months[order["order_date"][:7]] += order["total"]
    channel_refunds: dict[str, float] = defaultdict(float)
    for item in returns:
        channel_refunds[order_channel[item["order_id"]]] += item["refund_amount"]
    warehouse_values: dict[str, float] = defaultdict(float)
    for item in inventory:
        if not item["discontinued"]:
            warehouse_values[item["warehouse"]] += item["stock_on_hand"] * item["unit_cost"]
    low_stock = [i["sku"] for i in inventory if i["warehouse"] == "Rotterdam" and i["category"] == "Networking" and not i["discontinued"] and i["stock_on_hand"] < i["reorder_point"]]

    def row(number: int, prompt: str, checker: str, expected: Any) -> dict[str, Any]:
        return {"id": f"L{number:02d}", "category": "large-data", "prompt": prompt, "checker": checker, "expected": expected}

    return [
        row(1, "What was our total revenue from completed orders in the EMEA region in Q3 2025 (July through September)? Use the order total. Answer with the amount in dollars, rounded to 2 decimals.", "answer_number",
            _money(sum(o["total"] for o in completed if o["region"] == "EMEA" and "2025-07-01" <= o["order_date"] <= "2025-09-30"))),
        row(2, "How many APAC orders came through the partner channel with a discount of 15% or more and a status of shipped or completed? Answer with the number only.", "answer_number",
            _count(sum(o["region"] == "APAC" and o["channel"] == "partner" and o["discount_pct"] >= 15 and o["status"] in ("shipped", "completed") for o in orders))),
        row(3, "Which sales rep in the LATAM region brought in the most revenue from completed orders in 2025? Use the order total. Answer with the rep's full name.", "answer_text",
            rep_names[_best({k: v for k, v in rep_totals.items() if k in latam_reps})[0]]),
        row(4, "What are the top 5 SKUs by total quantity ordered, leaving out cancelled orders? Answer with the 5 SKUs in order from highest to lowest, separated by commas.", "answer_ordered",
            _best(_sum_by([o for o in orders if o["status"] != "cancelled"], "sku", "quantity"), 5)),
        row(5, "Which SKUs in the Networking category at the Rotterdam warehouse are not discontinued and have stock on hand below their reorder point? Answer with the SKUs separated by commas.", "answer_set", low_stock),
        row(6, "Leaving out discontinued items, which warehouse holds the highest inventory value, where value is stock on hand times unit cost? Answer with the warehouse name.", "answer_text", _best(warehouse_values)[0]),
        row(7, "What was the total revenue from completed orders placed by enterprise-segment customers based in Germany? Use the order total. Answer with the amount in dollars, rounded to 2 decimals.", "answer_number",
            _money(sum(o["total"] for o in completed if o["customer_id"] in german_enterprise))),
        row(8, "Which customer has the highest total spend across their completed and shipped orders? Use the order total. Answer with the customer ID.", "answer_text",
            _best(_sum_by([o for o in orders if o["status"] in ("completed", "shipped")], "customer_id", "total"))[0]),
        row(9, "Looking at returns, which sales channel of the original order has the highest total refund amount? Answer with the channel name.", "answer_text", _best(channel_refunds)[0]),
        row(10, "How many SKUs that are not discontinued and have stock on hand greater than zero come from suppliers marked as inactive? Answer with the number only.", "answer_number",
            _count(sum(not i["discontinued"] and i["stock_on_hand"] > 0 and i["supplier_id"] in inactive_suppliers for i in inventory))),
        row(11, "Which calendar month of 2025 had the highest revenue from completed orders? Use the order total. Answer in the form YYYY-MM.", "answer_text", _best(months)[0]),
        row(12, "How many sales reps met or beat their 2025 quota, counting the order total of their completed orders as revenue? Answer with the number only.", "answer_number",
            _count(sum(rep_totals.get(r["rep_id"], 0) >= r["quota_2025"] for r in reps))),
    ]


def _title(docs: dict[str, dict[str, Any]], doc_id: str) -> str:
    title = docs[doc_id]["title"]
    if sum(d["title"] == title for d in docs.values()) != 1:
        raise ValueError(f"Title is not unique: {title}")
    return title


def _task_rules(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"assignee": i["owner"], "due_date": i["due"], "title_contains": re.escape(i["description"])} for i in items]


def multi_step_tasks(sheets: dict[str, list[dict[str, Any]]], docs: dict[str, dict[str, Any]], crm: dict[str, Any], truth: dict[str, Any]) -> list[dict[str, Any]]:
    items_by_doc = truth["action_items"]
    plans, facts = truth["account_plans"], truth["policy_facts"]
    doc_by_size = {size: next(d for d in sorted(items_by_doc) if len(items_by_doc[d]) == size) for size in (3, 4, 5)}

    def row(number: int, prompt: str, expected: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"id": f"M{number:02d}", "category": "multi-step", "prompt": prompt, "checker": "crm_state", "expected": expected, "params": params or {}}

    tasks = []
    for number, size in enumerate((3, 4, 5), start=1):
        title = _title(docs, doc_by_size[size])
        tasks.append(row(number, f'Go through the action items in the meeting notes titled "{title}" and create a CRM follow-up task for each one. The task title must be the action item\'s text word for word (without the owner or due date), assigned to its owner, with its due date.',
                         {"new": {"tasks": _task_rules(items_by_doc[doc_by_size[size]])}}, {"title": title}))

    plan = plans["DOC-A01"]
    tasks.append(row(4, f'The account plan for {plan["company"]} lists key stakeholders. Add each of them to the CRM as a new contact with their name, email and job title, and with {plan["company"]} as the company.',
                     {"new": {"contacts": [{**p, "company": plan["company"]} for p in plan["stakeholders"]]}}, {"title": docs["DOC-A01"]["title"], "company": plan["company"]}))

    plan = plans["DOC-A02"]
    lead, deal = plan["stakeholders"][0], plan["deal"]
    tasks.append(row(5, f'The account plan for {plan["company"]} lists key stakeholders and a proposed deal. Add each stakeholder to the CRM as a new contact with their name, email and job title, and with {plan["company"]} as the company. Then create the proposed deal in the CRM with its amount, stage and expected close date, linked to {lead["name"]}.',
                     {"new": {"contacts": [{**p, "company": plan["company"]} for p in plan["stakeholders"]], "deals": [{"contact_email": lead["email"], "amount": deal["amount"], "stage": deal["stage"], "close_date": deal["close_date"]}]}},
                     {"title": docs["DOC-A02"]["title"], "company": plan["company"], "lead": lead["name"]}))

    contact = next(c for c in crm["contacts"] if c["contact_id"] == "C-0050")
    limit = facts["DOC-P03"]["rep_max_discount_pct"]
    tasks.append(row(6, f'{contact["name"]} at {contact["company"]} asked how much discount a sales rep can give. Check our discount approval policy for the rep maximum discount, then add a note to their CRM contact stating that percentage.',
                     {"new": {"notes": [{"entity_type": "contact", "entity_id": contact["contact_id"], "body_contains": rf"(?<![\d.]){limit}(?![\d])"}]}}, {"contact": contact["name"]}))

    def lapsed(owner: str) -> list[dict[str, Any]]:
        return [d for d in crm["deals"] if d["owner"] == owner and d["stage"] == "negotiation" and d["close_date"] < "2025-07-01"]

    owner = next(o for o in sorted({d["owner"] for d in crm["deals"]}) if 2 <= len(lapsed(o)) <= 5)
    tasks.append(row(7, f'{owner}\'s deals in the negotiation stage with a close date before 2025-07-01 have lapsed. Mark each of them as closed lost, and add a note to each deal saying it lapsed.',
                     {"changed": {"deals": {d["deal_id"]: {"stage": "closed_lost"} for d in lapsed(owner)}}, "new": {"notes": [{"entity_type": "deal", "entity_id": d["deal_id"], "body_contains": "laps"} for d in lapsed(owner)]}}, {"owner": owner}))

    apac_lead = max((r for r in sheets["sales_reps"] if r["region"] == "APAC"), key=lambda r: (r["quota_2025"], r["rep_id"]))
    by_company: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in crm["contacts"]:
        by_company[item["company"]].append(item)
    company = next(name for name in sorted(by_company) if 2 <= len(by_company[name]) <= 4 and all(c["owner"] != apac_lead["name"] for c in by_company[name]))
    tasks.append(row(8, f'Reassign every CRM contact at {company} to the APAC sales rep with the highest 2025 quota, so that rep becomes their owner.',
                     {"changed": {"contacts": {c["contact_id"]: {"owner": apac_lead["name"]} for c in by_company[company]}}}, {"company": company}))

    emea_lead = max((r for r in sheets["sales_reps"] if r["region"] == "EMEA"), key=lambda r: (r["quota_2025"], r["rep_id"]))
    window = facts["DOC-P01"]["refund_window_days"]
    due = (FAKE_TODAY + timedelta(days=window)).isoformat()
    tasks.append(row(9, 'Create a CRM task titled "Review refund window" for the EMEA sales rep with the highest 2025 quota. Set the due date to 2026-03-15 plus the number of days in the refund window from our refund policy.',
                     {"new": {"tasks": [{"assignee": emea_lead["name"], "due_date": due, "title_contains": "Review refund window"}]}}))

    owed: dict[str, list[dict[str, str]]] = defaultdict(list)
    for doc_id in sorted(items_by_doc):
        for item in items_by_doc[doc_id]:
            owed[item["owner"]].append(item)
    person = _best({name: float(len(items)) for name, items in owed.items()})[0]
    tasks.append(row(10, f'Find every action item assigned to {person} across all of our meeting notes, and create a CRM follow-up task for each one. The task title must be the action item\'s text word for word (without the owner or due date), assigned to {person}, with its due date.',
                     {"new": {"tasks": _task_rules(owed[person])}}, {"person": person}))
    return tasks


def simple_tasks(sheets: dict[str, list[dict[str, Any]]], crm: dict[str, Any], truth: dict[str, Any]) -> list[dict[str, Any]]:
    rep = next(r for r in sheets["sales_reps"] if r["rep_id"] == "R-017")
    order = next(o for o in sheets["orders"] if o["order_id"] == "O-04321")
    contact = next(c for c in crm["contacts"] if c["contact_id"] == "C-0123")
    deal = next(d for d in crm["deals"] if d["deal_id"] == "D-0042")

    def row(number: int, prompt: str, checker: str, expected: Any) -> dict[str, Any]:
        return {"id": f"S{number:02d}", "category": "simple", "prompt": prompt, "checker": checker, "expected": expected}

    return [
        row(1, "What is the 2025 quota for sales rep R-017? Answer with the number only.", "answer_number", _count(rep["quota_2025"])),
        row(2, "How many rows does the Inventory spreadsheet have? Answer with the number only.", "answer_number", _count(len(sheets["inventory"]))),
        row(3, "What is the status of order O-04321? Answer with the status only.", "answer_text", order["status"]),
        row(4, "How many days is the refund window in our refund policy? Answer with the number only.", "answer_number", _count(truth["policy_facts"]["DOC-P01"]["refund_window_days"])),
        row(5, "What is the email address of CRM contact C-0123? Answer with the email only.", "answer_text", contact["email"]),
        row(6, "What stage is CRM deal D-0042 in? Answer with the stage name exactly as stored.", "answer_text", deal["stage"]),
        row(7, 'Change the job title of CRM contact C-0200 to "Director of Operations".', "crm_state", {"changed": {"contacts": {"C-0200": {"title": "Director of Operations"}}}}),
        row(8, 'Add a note to CRM deal D-0100 saying "Customer asked for a revised quote".', "crm_state", {"new": {"notes": [{"entity_type": "deal", "entity_id": "D-0100", "body_contains": "Customer asked for a revised quote"}]}}),
    ]


def build(base: Path) -> list[dict[str, Any]]:
    sheets = {path.stem: json.loads(path.read_text())["rows"] for path in (base / "sheets").glob("*.json")}
    docs = {d["id"]: d for d in json.loads((base / "docs.json").read_text())}
    crm = json.loads((base / "crm.json").read_text())
    truth = json.loads((base / "truth.json").read_text())
    tasks = large_data_tasks(sheets) + multi_step_tasks(sheets, docs, crm, truth) + simple_tasks(sheets, crm, truth)
    if Counter(t["category"] for t in tasks) != {"large-data": 12, "multi-step": 10, "simple": 8}:
        raise ValueError("Unexpected task counts")
    return tasks


def serialize(tasks: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(task, sort_keys=True, ensure_ascii=False) + "\n" for task in tasks)


def load_tasks() -> list[dict[str, Any]]:
    return [json.loads(line) for line in TASKS_PATH.read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    TASKS_PATH.write_text(serialize(build(ROOT / "data")), encoding="utf-8")
