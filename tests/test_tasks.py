"""Tasks are verified by the oracle, and checkers by negative cases that must fail."""

import asyncio
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from servers.client import open_tools
from servers.state import new_run_state
from tasks.build_tasks import TASKS_PATH, build, load_tasks, serialize
from tasks.checkers import COLLECTION_KEYS, answer_number, answer_ordered, answer_set, answer_text, check, extract_answer
from tasks.oracle import SOLVERS

TASKS = load_tasks()
IDS = [task["id"] for task in TASKS]
ANSWERS = [task for task in TASKS if task["checker"] != "crm_state"]
STATES = [task for task in TASKS if task["checker"] == "crm_state"]


@pytest.fixture(scope="session")
def oracle_runs(base_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    async def run_one(task: dict[str, Any]) -> dict[str, Any]:
        state_dir = new_run_state(tmp_path_factory.mktemp(task["id"]), base_dir)
        async with open_tools(state_dir, base_dir) as tools:
            message = await SOLVERS[task["id"]](tools, task.get("params", {}))
            calls = list(tools.calls)
        return {"message": message, "state": json.loads((state_dir / "crm.json").read_text()), "calls": calls}

    return {task["id"]: asyncio.run(run_one(task)) for task in TASKS}


@pytest.fixture(scope="session")
def base_crm(base_dir: Path) -> dict[str, Any]:
    return json.loads((base_dir / "crm.json").read_text())


def test_committed_tasks_match_the_data(base_dir: Path) -> None:
    assert TASKS_PATH.read_text(encoding="utf-8") == serialize(build(base_dir))


def test_task_shape() -> None:
    assert Counter(task["category"] for task in TASKS) == {"large-data": 12, "multi-step": 10, "simple": 8}
    assert len(set(IDS)) == 30
    for task in TASKS:
        assert {"id", "category", "prompt", "checker", "expected"} <= set(task)


async def test_prompts_do_not_name_tools(base_dir: Path, tmp_path: Path) -> None:
    async with open_tools(new_run_state(tmp_path / "s", base_dir), base_dir) as tools:
        names = [tool.name for tool in tools.tools]
    assert len(names) == 32
    for task in TASKS:
        assert not [name for name in names if name in task["prompt"]], task["id"]


def test_low_stock_list_is_reasonable() -> None:
    expected = next(task for task in TASKS if task["id"] == "L05")["expected"]
    assert 3 <= len(expected) <= 60


def test_quota_count_is_not_degenerate() -> None:
    """A count equal to all or none of the reps could be guessed without doing the work."""
    expected = next(task for task in TASKS if task["id"] == "L12")["expected"]
    assert 10 <= expected["value"] <= 40


def test_cross_document_task_has_several_items() -> None:
    expected = next(task for task in TASKS if task["id"] == "M10")["expected"]
    assert len(expected["new"]["tasks"]) >= 3


@pytest.mark.parametrize("task", TASKS, ids=IDS)
def test_oracle_passes(task: dict[str, Any], oracle_runs: dict[str, dict[str, Any]], base_crm: dict[str, Any]) -> None:
    run = oracle_runs[task["id"]]
    assert check(task, run["message"], run["state"], base_crm)


@pytest.mark.parametrize("task", [t for t in TASKS if t["category"] == "multi-step"], ids=lambda t: t["id"])
def test_multi_step_chains_three_tools(task: dict[str, Any], oracle_runs: dict[str, dict[str, Any]]) -> None:
    assert len(set(oracle_runs[task["id"]]["calls"])) >= 3


@pytest.mark.parametrize("task", [t for t in TASKS if t["category"] == "simple"], ids=lambda t: t["id"])
def test_simple_needs_at_most_two_calls(task: dict[str, Any], oracle_runs: dict[str, dict[str, Any]]) -> None:
    assert len(oracle_runs[task["id"]]["calls"]) <= 2


@pytest.mark.parametrize("task", [t for t in TASKS if t["category"] == "large-data"], ids=lambda t: t["id"])
def test_large_data_answer_needs_more_than_a_lookup(task: dict[str, Any], oracle_runs: dict[str, dict[str, Any]]) -> None:
    assert {"read_rows", "find_rows"} & set(oracle_runs[task["id"]]["calls"])


def _near_miss(task: dict[str, Any]) -> list[str]:
    expected = task["expected"]
    if task["checker"] == "answer_number":
        return [f"<answer>{expected['value'] + 1}</answer>", f"<answer>{expected['value']} or {expected['value'] + 1}</answer>"]
    if task["checker"] == "answer_text":
        return [f"<answer>{expected} extra</answer>"]
    misses = [f"<answer>{', '.join(expected[:-1])}</answer>", f"<answer>{', '.join(expected)}, SKU-99999</answer>"]
    if task["checker"] == "answer_ordered":
        misses.append(f"<answer>{', '.join(reversed(expected))}</answer>")
    return misses


@pytest.mark.parametrize("task", ANSWERS, ids=lambda t: t["id"])
def test_answer_checkers_reject_wrong_answers(task: dict[str, Any], base_crm: dict[str, Any]) -> None:
    assert not check(task, "I could not work it out.", base_crm, base_crm)
    assert not check(task, "<answer>wrong</answer>", base_crm, base_crm)
    for message in _near_miss(task):
        assert not check(task, message, base_crm, base_crm), message


@pytest.mark.parametrize("task", ANSWERS, ids=lambda t: t["id"])
def test_answer_checkers_need_the_answer_tag(task: dict[str, Any], oracle_runs: dict[str, dict[str, Any]], base_crm: dict[str, Any]) -> None:
    message = oracle_runs[task["id"]]["message"]
    assert not check(task, message.replace("<answer>", "").replace("</answer>", ""), base_crm, base_crm)


@pytest.mark.parametrize("task", STATES, ids=lambda t: t["id"])
def test_state_checkers_reject_the_unchanged_state(task: dict[str, Any], base_crm: dict[str, Any]) -> None:
    assert not check(task, "Done.", base_crm, base_crm)


def _new_records(state: dict[str, Any], base: dict[str, Any], collection: str) -> list[dict[str, Any]]:
    key = COLLECTION_KEYS[collection]
    known = {record[key] for record in base[collection]}
    return [record for record in state[collection] if record[key] not in known]


@pytest.mark.parametrize("task", STATES, ids=lambda t: t["id"])
def test_state_checkers_reject_partial_work(task: dict[str, Any], oracle_runs: dict[str, dict[str, Any]], base_crm: dict[str, Any]) -> None:
    state = copy.deepcopy(oracle_runs[task["id"]]["state"])
    for collection, rules in task["expected"].get("new", {}).items():
        if rules:
            state[collection].remove(_new_records(state, base_crm, collection)[-1])
            break
    else:
        collection, changes = next(iter(task["expected"]["changed"].items()))
        key = COLLECTION_KEYS[collection]
        original = next(r for r in base_crm[collection] if r[key] == next(iter(changes)))
        state[collection] = [original if r[key] == original[key] else r for r in state[collection]]
    assert not check(task, "Done.", state, base_crm)


@pytest.mark.parametrize("task", STATES, ids=lambda t: t["id"])
def test_state_checkers_reject_collateral_changes(task: dict[str, Any], oracle_runs: dict[str, dict[str, Any]], base_crm: dict[str, Any]) -> None:
    run = oracle_runs[task["id"]]
    untouched = next(c for c in run["state"]["contacts"] if c["contact_id"] == "C-0499")
    assert untouched == next(c for c in base_crm["contacts"] if c["contact_id"] == "C-0499"), "pick another bystander"

    edited = copy.deepcopy(run["state"])
    next(c for c in edited["contacts"] if c["contact_id"] == "C-0499")["title"] = "Changed"
    assert not check(task, "Done.", edited, base_crm)

    deleted = copy.deepcopy(run["state"])
    deleted["contacts"] = [c for c in deleted["contacts"] if c["contact_id"] != "C-0499"]
    assert not check(task, "Done.", deleted, base_crm)

    extra = copy.deepcopy(run["state"])
    extra["tasks"].append({"task_id": "T-9999", "title": "Stray", "assignee": "x", "due_date": "2026-01-01", "status": "open", "contact_id": None, "created_at": "2026-03-15"})
    assert not check(task, "Done.", extra, base_crm)


@pytest.mark.parametrize("task", STATES, ids=lambda t: t["id"])
def test_state_checkers_reject_wrong_values_in_new_records(task: dict[str, Any], oracle_runs: dict[str, dict[str, Any]], base_crm: dict[str, Any]) -> None:
    fields = {"tasks": "due_date", "contacts": "email", "deals": "amount", "notes": "body"}
    wrong = {"due_date": "1999-01-01", "email": "wrong@wrong.example", "amount": 1.0, "body": "unrelated text"}
    for collection, rules in task["expected"].get("new", {}).items():
        state = copy.deepcopy(oracle_runs[task["id"]]["state"])
        record = _new_records(state, base_crm, collection)[0]
        record[fields[collection]] = wrong[fields[collection]]
        assert not check(task, "Done.", state, base_crm), collection


def test_extract_answer_uses_the_last_tag() -> None:
    assert extract_answer("<answer>1</answer> no, <ANSWER> 2\n</ANSWER>") == "2"
    assert extract_answer("nothing here") is None


@pytest.mark.parametrize("text", ["$1,234.50", "1234.5", "1234.50 USD", "**1,234.50**"])
def test_number_formats_are_accepted(text: str) -> None:
    assert answer_number(f"<answer>{text}</answer>", {}, {}, {"value": 1234.5, "tolerance": 0.01})


def test_text_and_list_normalisation() -> None:
    assert answer_text("<answer> **Reno**. </answer>", {}, {}, "reno")
    assert answer_set("<answer>- B\n- a</answer>", {}, {}, ["A", "b"])
    assert answer_ordered("<answer>1. a\n2. b</answer>", {}, {}, ["A", "B"])
    assert not answer_ordered("<answer>b, a</answer>", {}, {}, ["A", "B"])
    assert not answer_set("<answer>a, a</answer>", {}, {}, ["A", "B"])
