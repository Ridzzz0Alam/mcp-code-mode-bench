"""Programmatic task checkers. No LLM judging.

Every checker takes (final_message, final_crm_state, base_crm_state, expected) and returns a bool.
"""

import re
from collections.abc import Callable
from typing import Any

Crm = dict[str, Any]
Checker = Callable[[str, Crm, Crm, Any], bool]

COLLECTION_KEYS = {"contacts": "contact_id", "deals": "deal_id", "notes": "note_id", "tasks": "task_id"}
_ANSWER = re.compile(r"<answer>(.*?)</answer>", re.IGNORECASE | re.DOTALL)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_BULLET = re.compile(r"^(?:\d+[.)]|[-*])\s+")


def extract_answer(message: str) -> str | None:
    """Return the text of the last <answer> tag, or None if there is none."""
    found = _ANSWER.findall(message)
    return found[-1].strip() if found else None


def normalize_text(text: str) -> str:
    return " ".join(text.split()).strip(" .`'\"*").casefold()


def _items(answer: str) -> list[str]:
    parts = re.split(r"[,\n]", answer)
    return [normalize_text(_BULLET.sub("", part.strip())) for part in parts if part.strip()]


def answer_number(message: str, state: Crm, base: Crm, expected: dict[str, float]) -> bool:
    """The answer must hold exactly one number, within the task's tolerance."""
    answer = extract_answer(message)
    if answer is None:
        return False
    numbers = _NUMBER.findall(answer.replace(",", ""))
    return len(numbers) == 1 and abs(float(numbers[0]) - expected["value"]) <= expected["tolerance"]


def answer_text(message: str, state: Crm, base: Crm, expected: str) -> bool:
    answer = extract_answer(message)
    return answer is not None and normalize_text(answer) == normalize_text(expected)


def answer_set(message: str, state: Crm, base: Crm, expected: list[str]) -> bool:
    answer = extract_answer(message)
    if answer is None:
        return False
    items = _items(answer)
    return len(items) == len(expected) and set(items) == {normalize_text(item) for item in expected}


def answer_ordered(message: str, state: Crm, base: Crm, expected: list[str]) -> bool:
    answer = extract_answer(message)
    return answer is not None and _items(answer) == [normalize_text(item) for item in expected]


def _contact_email(state: Crm, contact_id: str | None) -> str | None:
    for contact in state["contacts"]:
        if contact["contact_id"] == contact_id:
            return contact["email"].casefold()
    return None


def _matches(record: dict[str, Any], rule: dict[str, Any], state: Crm) -> bool:
    for key, wanted in rule.items():
        if key == "contact_email":
            if _contact_email(state, record.get("contact_id")) != wanted.casefold():
                return False
        elif key.endswith("_contains"):
            field = record.get(key.removesuffix("_contains")) or ""
            if not re.search(wanted, field, re.IGNORECASE):
                return False
        elif isinstance(wanted, str):
            if normalize_text(str(record.get(key))) != normalize_text(wanted):
                return False
        elif record.get(key) != wanted:
            return False
    return True


def crm_state(message: str, state: Crm, base: Crm, expected: dict[str, Any]) -> bool:
    """The CRM must hold exactly the expected new and changed records, and nothing else may differ.

    expected["new"] maps a collection to rules, each of which one new record must satisfy.
    expected["changed"] maps a collection to {record id: {field: new value}}.
    The final message is ignored, because the outcome is the final state.
    """
    for collection, key in COLLECTION_KEYS.items():
        before = {record[key]: record for record in base[collection]}
        after = {record[key]: record for record in state[collection]}
        if set(before) - set(after):
            return False
        changes = expected.get("changed", {}).get(collection, {})
        for record_id, record in before.items():
            if after[record_id] != record | changes.get(record_id, {}):
                return False
        unmatched = [record for record_id, record in after.items() if record_id not in before]
        rules = expected.get("new", {}).get(collection, [])
        if len(unmatched) != len(rules):
            return False
        for rule in rules:
            hit = next((record for record in unmatched if _matches(record, rule, state)), None)
            if hit is None:
                return False
            unmatched.remove(hit)
    return True


CHECKERS: dict[str, Checker] = {
    "answer_number": answer_number,
    "answer_text": answer_text,
    "answer_set": answer_set,
    "answer_ordered": answer_ordered,
    "crm_state": crm_state,
}


def check(task: dict[str, Any], message: str, state: Crm, base: Crm) -> bool:
    return CHECKERS[task["checker"]](message, state, base, task["expected"])
