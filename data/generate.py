"""Generate the seeded fake dataset. Usage: uv run python data/generate.py [out_dir]

Writes sheets/*.json, docs.json and crm.json, which the servers serve, and truth.json,
which only checkers may read. No server exposes truth.json.
"""

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

SEED = 20260315
YEAR_START = date(2025, 1, 1)

REGION_COUNTRIES = {
    "North America": ["United States", "Canada", "Mexico"],
    "EMEA": ["Germany", "France", "United Kingdom", "Netherlands", "South Africa", "UAE"],
    "APAC": ["Japan", "Australia", "Singapore", "India", "South Korea"],
    "LATAM": ["Brazil", "Argentina", "Chile", "Colombia"],
}
REGIONS = list(REGION_COUNTRIES)
FIRST = """Ava Liam Noah Mia Zoe Omar Nina Leo Iris Hugo Maya Ivan Lena Theo Ruth Saul Dana Eli
Tara Yuki Priya Mateo Sofia Kofi Amara Chen Wei Lars Greta Paolo Ines Rafael Nadia Tomas Elsa Arjun
Keiko Diego Freya Malik""".split()
LAST = """Abara Bennett Castillo Dubois Eriksen Fischer Garcia Haddad Ito Jansen Kowalski Larsen
Mbeki Novak Okafor Petrov Quinn Rossi Silva Tanaka Ueda Vargas Weber Xu Yilmaz Zhang Ahmed Brandt
Costa Dahl Evans Farah Gupta Holm Ibrahim Jung Kaur Lopez Moreau Nair""".split()
COMPANY_A = """Northwind Bluepeak Ironleaf Silverline Redwood Brightwater Stonebridge Cobalt
Evergreen Summit Harbor Lumen Meridian Orchard Pinnacle Quartz Riverbend Solstice Trailhead Vertex""".split()
COMPANY_B = "Logistics Foods Systems Health Energy Robotics Retail Media Labs Partners".split()
CATEGORIES = ["Networking", "Storage", "Peripherals", "Audio", "Displays", "Power", "Cabling", "Furniture"]
ADJECTIVES = "Compact Rugged Pro Silent Ultra Modular Slim Heavy-Duty Wireless Smart".split()
NOUNS = "Switch Router Drive Dock Hub Headset Monitor Charger Cable Desk".split()
WAREHOUSES = ["Rotterdam", "Memphis", "Singapore", "Sao Paulo", "Reno", "Leipzig"]
STAGES = ["prospecting", "qualified", "proposal", "negotiation", "closed_won", "closed_lost"]
TOPICS = """the renewal pipeline|warehouse throughput|the onboarding checklist|partner enablement|quarterly
forecasting|support ticket volume|the pricing review|the migration timeline|customer churn signals|vendor
contracts|hiring plans|the analytics rollout|regional inventory levels|the security audit|freight
costs""".replace("\n", " ").split("|")
FILLER = [
    "The team reviewed {t} and agreed the current numbers were directionally useful but incomplete.",
    "Several people pointed out that {t} depends on inputs that arrive later than anyone would like.",
    "There was a long discussion about {t}, with no strong objection to the existing approach.",
    "Compared with the previous cycle, {t} looked steadier, although a few outliers need explaining.",
    "Someone noted that earlier work on {t} was never fully written down, which slows new starters.",
    "It was suggested that {t} should be revisited once the next reporting period has closed.",
    "Feedback from the field on {t} was mixed, and most of it was anecdotal rather than measured.",
    "The group spent time on the assumptions behind {t} and how sensitive they are to seasonality.",
]


def _day(rng: random.Random, span: int = 364, start: date = YEAR_START) -> str:
    return (start + timedelta(days=rng.randint(0, span))).isoformat()


def _sheet(sheet_id: str, title: str, description: str, modified: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    types = {bool: "boolean", int: "integer", float: "number", str: "string"}
    columns = [{"name": k, "type": types[type(v)]} for k, v in rows[0].items()]
    return {"id": sheet_id, "title": title, "description": description, "modified": modified, "columns": columns, "rows": rows}


def _unique_names(rng: random.Random, count: int) -> list[str]:
    pairs = [f"{first} {last}" for first in FIRST for last in LAST]
    return rng.sample(pairs, count)


def _companies(rng: random.Random) -> list[str]:
    pairs = [f"{a} {b}" for a in COMPANY_A for b in COMPANY_B]
    rng.shuffle(pairs)
    return pairs


def _email(name: str, company: str) -> str:
    return f"{name.lower().replace(' ', '.')}@{company.split()[0].lower()}.example"


def build_sheets(seed: int) -> dict[str, dict[str, Any]]:
    rng = random.Random(f"{seed}:reps")
    reps = [
        {
            "rep_id": f"R-{i + 1:03d}",
            "name": name,
            "region": REGIONS[i % len(REGIONS)],
            "hire_date": _day(rng, 2500, date(2018, 1, 1)),
            "quota_2025": rng.randrange(1_000_000, 3_000_000, 10_000),
        }
        for i, name in enumerate(_unique_names(rng, 50))
    ]

    rng = random.Random(f"{seed}:suppliers")
    suppliers = []
    for i in range(500):
        suppliers.append(
            {
                "supplier_id": f"S-{i + 1:04d}",
                "name": f"{rng.choice(COMPANY_A)} {rng.choice(['Supply', 'Trading', 'Components', 'Manufacturing'])} {i + 1}",
                "country": rng.choice(rng.choice(list(REGION_COUNTRIES.values()))),
                "lead_time_days": rng.randint(3, 90),
                "rating": round(rng.uniform(1.0, 5.0), 1),
                "active": rng.random() > 0.1,
            }
        )

    rng = random.Random(f"{seed}:inventory")
    inventory = []
    for i in range(10_000):
        cost = round(rng.uniform(2.0, 900.0), 2)
        inventory.append(
            {
                "sku": f"SKU-{i + 1:05d}",
                "product_name": f"{rng.choice(ADJECTIVES)} {rng.choice(NOUNS)} {rng.randint(100, 999)}",
                "category": rng.choice(CATEGORIES),
                "supplier_id": f"S-{rng.randint(1, 500):04d}",
                "warehouse": rng.choice(WAREHOUSES),
                "stock_on_hand": rng.randint(0, 2000),
                "reorder_point": rng.randint(20, 500),
                "unit_cost": cost,
                "unit_price": round(cost * rng.uniform(1.15, 2.2), 2),
                "last_restock_date": _day(rng),
                "discontinued": rng.random() < 0.05,
            }
        )

    rng = random.Random(f"{seed}:customers")
    companies = _companies(rng)
    customers = []
    for i in range(10_000):
        region = rng.choice(REGIONS)
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        company = rng.choice(companies)
        customers.append(
            {
                "customer_id": f"CU-{i + 1:05d}",
                "name": name,
                "company": company,
                "email": f"{name.lower().replace(' ', '.')}.{i + 1}@{company.split()[0].lower()}.example",
                "country": rng.choice(REGION_COUNTRIES[region]),
                "region": region,
                "segment": rng.choices(["enterprise", "mid-market", "smb", "consumer"], [1, 2, 4, 3])[0],
                "signup_date": _day(rng, 2000, date(2019, 6, 1)),
                "is_active": rng.random() > 0.15,
            }
        )

    rng = random.Random(f"{seed}:orders")
    reps_by_region = {r: [rep["rep_id"] for rep in reps if rep["region"] == r] for r in REGIONS}
    orders = []
    for i in range(10_000):
        customer = rng.choice(customers)
        item = rng.choice(inventory)
        quantity = rng.randint(1, 40)
        discount = rng.choice([0, 0, 0, 5, 10, 15, 20])
        orders.append(
            {
                "order_id": f"O-{i + 1:05d}",
                "order_date": _day(rng),
                "customer_id": customer["customer_id"],
                "sku": item["sku"],
                "quantity": quantity,
                "unit_price": item["unit_price"],
                "discount_pct": discount,
                "total": round(quantity * item["unit_price"] * (1 - discount / 100), 2),
                "status": rng.choices(["completed", "shipped", "pending", "cancelled", "refunded"], [70, 10, 6, 8, 6])[0],
                "channel": rng.choice(["web", "phone", "partner", "retail"]),
                "region": customer["region"],
                "rep_id": rng.choice(reps_by_region[customer["region"]]),
            }
        )

    rng = random.Random(f"{seed}:returns")
    refunded = [o for o in orders if o["status"] == "refunded"]
    completed = [o for o in orders if o["status"] == "completed"]
    returned = (refunded + rng.sample(completed, 2000))[:2000]
    returns = []
    for i, order in enumerate(returned):
        returns.append(
            {
                "return_id": f"RT-{i + 1:05d}",
                "order_id": order["order_id"],
                "return_date": (date.fromisoformat(order["order_date"]) + timedelta(days=rng.randint(1, 45))).isoformat(),
                "reason": rng.choice(["damaged", "wrong_item", "no_longer_needed", "late_delivery", "defective"]),
                "refund_amount": round(order["total"] * rng.choice([1.0, 1.0, 0.75, 0.5]), 2),
                "condition": rng.choice(["new", "opened", "used", "unsellable"]),
            }
        )

    return {
        "orders": _sheet("orders", "Orders 2025", "Every customer order placed in 2025.", "2026-01-05", orders),
        "customers": _sheet("customers", "Customers", "All customer accounts and their segment.", "2026-02-10", customers),
        "inventory": _sheet("inventory", "Inventory", "Stock levels and pricing per SKU.", "2026-03-01", inventory),
        "returns": _sheet("returns", "Returns 2025", "Returned orders with refund amounts.", "2026-01-20", returns),
        "suppliers": _sheet("suppliers", "Suppliers", "Supplier directory with lead times and ratings.", "2025-11-12", suppliers),
        "sales_reps": _sheet("sales_reps", "Sales reps", "Sales reps with region and 2025 quota.", "2025-12-01", reps),
    }


def _paragraphs(rng: random.Random, count: int) -> list[str]:
    paragraphs = []
    for _ in range(count):
        topic = rng.choice(TOPICS)
        paragraphs.append(" ".join(s.format(t=topic) for s in rng.sample(FILLER, rng.randint(4, 6))))
    return paragraphs


def build_docs(seed: int, rep_names: list[str], stakeholder_names: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(f"{seed}:docs")
    docs: list[dict[str, Any]] = []
    action_items: dict[str, list[dict[str, str]]] = {}
    for i in range(40):
        doc_id = f"DOC-M{i + 1:02d}"
        day = _day(rng, 70, date(2026, 1, 1))
        topic = rng.choice(TOPICS)
        items = [
            {
                "owner": owner,
                "description": f"Prepare a written update on {rng.choice(TOPICS)} (ref {doc_id}-{n + 1})",
                "due": _day(rng, 30, date(2026, 3, 16)),
            }
            for n, owner in enumerate(rng.sample(rep_names, rng.randint(2, 6)))
        ]
        action_items[doc_id] = items
        attendees = sorted({item["owner"] for item in items} | set(rng.sample(rep_names, 3)))
        sections = [
            ("Attendees", ", ".join(attendees)),
            ("Discussion", "\n\n".join(_paragraphs(rng, rng.randint(6, 12)))),
            ("Decisions", "\n".join(f"- Keep the current plan for {rng.choice(TOPICS)}." for _ in range(rng.randint(2, 4)))),
            ("Action items", "\n".join(f"- {x['owner']}: {x['description']} (due {x['due']})" for x in items)),
            ("Parking lot", "\n\n".join(_paragraphs(rng, 2))),
        ]
        docs.append(_doc(doc_id, f"Meeting notes {day}: {topic}", "meeting-notes", day, rng.choice(rep_names), sections))

    policy_facts: dict[str, dict[str, int]] = {}
    policies = [
        ("Refund policy", {"refund_window_days": rng.randint(14, 60), "restocking_fee_pct": rng.randint(5, 25)}),
        ("Expense policy", {"meal_limit_usd": rng.randint(40, 120), "hotel_limit_usd": rng.randint(150, 400)}),
        ("Discount approval policy", {"rep_max_discount_pct": rng.randint(5, 15), "manager_max_discount_pct": rng.randint(20, 35)}),
        ("Data retention policy", {"log_retention_days": rng.randint(30, 400), "backup_retention_days": rng.randint(30, 90)}),
        ("Travel policy", {"advance_booking_days": rng.randint(7, 30), "max_flight_class_hours": rng.randint(6, 12)}),
        ("Security policy", {"password_rotation_days": rng.randint(60, 180), "session_timeout_minutes": rng.randint(10, 60)}),
        ("Vendor onboarding policy", {"review_cycle_months": rng.randint(6, 24), "min_supplier_rating_x10": rng.randint(20, 40)}),
    ]
    for i, (title, facts) in enumerate(policies):
        doc_id = f"DOC-P{i + 1:02d}"
        policy_facts[doc_id] = facts
        sections = [("Purpose", "\n\n".join(_paragraphs(rng, 3)))]
        for n, (key, value) in enumerate(facts.items()):
            sections.append((f"Rule {n + 1}", f"The value of {key.replace('_', ' ')} is {value}.\n\n" + "\n\n".join(_paragraphs(rng, 6))))
        sections.append(("Exceptions", "\n\n".join(_paragraphs(rng, 4))))
        docs.append(_doc(doc_id, title, "policies", _day(rng, 300), rng.choice(rep_names), sections))

    account_plans: dict[str, dict[str, Any]] = {}
    plan_companies = rng.sample(_companies(random.Random(f"{seed}:customers")), 8)
    names = iter(stakeholder_names)
    for i, company in enumerate(plan_companies):
        doc_id = f"DOC-A{i + 1:02d}"
        people = []
        for _ in range(rng.randint(3, 5)):
            name = next(names)
            people.append({"name": name, "title": rng.choice(["CFO", "VP Sales", "Head of IT", "COO", "Procurement Lead"]), "email": _email(name, company)})
        deal = {"amount": rng.randrange(20_000, 500_000, 5_000), "stage": rng.choice(["qualified", "proposal", "negotiation"]), "close_date": _day(rng, 180, date(2026, 4, 1))}
        account_plans[doc_id] = {"company": company, "stakeholders": people, "deal": deal}
        sections = [
            ("Background", "\n\n".join(_paragraphs(rng, 5))),
            ("Key stakeholders", "\n".join(f"- {p['name']}, {p['title']}, {p['email']}" for p in people)),
            ("Proposed deal", f"Amount: {deal['amount']} USD. Stage: {deal['stage']}. Expected close: {deal['close_date']}."),
            ("Risks", "\n\n".join(_paragraphs(rng, 3))),
        ]
        docs.append(_doc(doc_id, f"Account plan: {company}", "account-plans", _day(rng, 60, date(2026, 1, 1)), rng.choice(rep_names), sections))

    return docs, {"action_items": action_items, "policy_facts": policy_facts, "account_plans": account_plans}


def _doc(doc_id: str, title: str, folder: str, updated: str, author: str, sections: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "id": doc_id,
        "title": title,
        "folder": folder,
        "updated": updated,
        "author": author,
        "sections": [{"heading": h, "body": b} for h, b in sections],
        "comments": [],
    }


def build_crm(seed: int, rep_names: list[str], contact_names: list[str]) -> dict[str, Any]:
    rng = random.Random(f"{seed}:crm")
    companies = _companies(rng)[:120]
    owners = rep_names[:12]
    contacts = []
    for i, name in enumerate(contact_names):
        company = rng.choice(companies)
        contacts.append(
            {
                "contact_id": f"C-{i + 1:04d}",
                "name": name,
                "email": _email(name, company),
                "phone": f"+1-555-{rng.randint(1000, 9999)}",
                "title": rng.choice(["CEO", "CFO", "VP Sales", "Head of IT", "Buyer", "Analyst", "COO"]),
                "company": company,
                "owner": rng.choice(owners),
                "lifecycle_stage": rng.choice(["lead", "customer", "churned"]),
                "created_at": _day(rng),
            }
        )
    deals = []
    for i in range(300):
        contact = rng.choice(contacts)
        stage = rng.choice(STAGES)
        deals.append(
            {
                "deal_id": f"D-{i + 1:04d}",
                "name": f"{contact['company']} {rng.choice(['renewal', 'expansion', 'pilot', 'rollout'])}",
                "company": contact["company"],
                "contact_id": contact["contact_id"],
                "owner": contact["owner"],
                "stage": stage,
                "amount": rng.randrange(5_000, 750_000, 2_500),
                "close_date": _day(rng, 500),
            }
        )
    notes = []
    for i in range(400):
        contact = rng.choice(contacts)
        notes.append(
            {
                "note_id": f"N-{i + 1:04d}",
                "entity_type": "contact",
                "entity_id": contact["contact_id"],
                "body": f"Spoke with {contact['name']} about {rng.choice(TOPICS)}.",
                "author": contact["owner"],
                "created_at": _day(rng),
            }
        )
    return {"contacts": contacts, "deals": deals, "notes": notes, "tasks": [], "next_ids": {"contact": 501, "deal": 301, "note": 401, "task": 1}}


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def generate(out: Path, seed: int = SEED) -> None:
    sheets = build_sheets(seed)
    rep_names = [row["name"] for row in sheets["sales_reps"]["rows"]]
    available = [n for n in _unique_names(random.Random(f"{seed}:people"), 700) if n not in rep_names]
    contact_names, stakeholder_names = available[:500], available[500:]
    docs, truth = build_docs(seed, rep_names, stakeholder_names)
    (out / "sheets").mkdir(parents=True, exist_ok=True)
    for sheet_id, sheet in sheets.items():
        _write(out / "sheets" / f"{sheet_id}.json", sheet)
    _write(out / "docs.json", docs)
    _write(out / "crm.json", build_crm(seed, rep_names, contact_names))
    _write(out / "truth.json", truth)


if __name__ == "__main__":
    generate(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent)
