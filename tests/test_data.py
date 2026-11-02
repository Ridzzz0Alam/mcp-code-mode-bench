import hashlib
import json
from pathlib import Path

from data.generate import generate


def _hashes(path: Path) -> dict[str, str]:
    return {str(f.relative_to(path)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(path.rglob("*.json"))}


def _sheet(base: Path, name: str) -> list[dict]:
    return json.loads((base / "sheets" / f"{name}.json").read_text())["rows"]


def test_generator_is_byte_identical(base_dir: Path, tmp_path: Path) -> None:
    generate(tmp_path / "again")
    assert _hashes(base_dir) == _hashes(tmp_path / "again")


def test_sheet_sizes(base_dir: Path) -> None:
    sizes = {name: len(_sheet(base_dir, name)) for name in ["orders", "customers", "inventory", "returns", "suppliers", "sales_reps"]}
    assert sizes == {"orders": 10_000, "customers": 10_000, "inventory": 10_000, "returns": 2_000, "suppliers": 500, "sales_reps": 50}


def test_sheet_references_resolve(base_dir: Path) -> None:
    customers = {r["customer_id"]: r for r in _sheet(base_dir, "customers")}
    skus = {r["sku"] for r in _sheet(base_dir, "inventory")}
    reps = {r["rep_id"]: r for r in _sheet(base_dir, "sales_reps")}
    suppliers = {r["supplier_id"] for r in _sheet(base_dir, "suppliers")}
    orders = _sheet(base_dir, "orders")
    for order in orders:
        assert order["sku"] in skus
        assert customers[order["customer_id"]]["region"] == order["region"]
        assert reps[order["rep_id"]]["region"] == order["region"]
        assert order["total"] == round(order["quantity"] * order["unit_price"] * (1 - order["discount_pct"] / 100), 2)
    assert all(r["supplier_id"] in suppliers for r in _sheet(base_dir, "inventory"))
    order_ids = {o["order_id"] for o in orders}
    assert all(r["order_id"] in order_ids for r in _sheet(base_dir, "returns"))


def test_planted_truth_appears_in_docs(base_dir: Path) -> None:
    docs = {d["id"]: "\n".join(s["body"] for s in d["sections"]) for d in json.loads((base_dir / "docs.json").read_text())}
    truth = json.loads((base_dir / "truth.json").read_text())
    assert len(docs) == 55
    for doc_id, items in truth["action_items"].items():
        for item in items:
            assert f"{item['owner']}: {item['description']} (due {item['due']})" in docs[doc_id]
    for doc_id, facts in truth["policy_facts"].items():
        for key, value in facts.items():
            assert f"The value of {key.replace('_', ' ')} is {value}." in docs[doc_id]
    for doc_id, plan in truth["account_plans"].items():
        for person in plan["stakeholders"]:
            assert f"{person['name']}, {person['title']}, {person['email']}" in docs[doc_id]


def test_stakeholders_are_new_to_the_crm(base_dir: Path) -> None:
    crm = json.loads((base_dir / "crm.json").read_text())
    truth = json.loads((base_dir / "truth.json").read_text())
    contact_names = {c["name"] for c in crm["contacts"]}
    assert len(contact_names) == 500
    for plan in truth["account_plans"].values():
        assert not contact_names & {p["name"] for p in plan["stakeholders"]}
