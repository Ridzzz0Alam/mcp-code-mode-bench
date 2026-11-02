"""Condition B tests, using the real servers and a fake API client."""

import json
from pathlib import Path
from typing import Any

import pytest

import runner
from agents.code_mode import CodeExposure
from agents.common import SYSTEM_CORE, system_prompt
from agents.direct import DirectExposure
from agents.tool_search import TOP_K, ToolSearchExposure
from servers.client import open_tools
from tests.test_runner import FakeClient, args_for, reply


def names(exposure: ToolSearchExposure) -> list[str]:
    return [tool["function"]["name"] for tool in exposure.tools()]


async def test_starts_with_only_search(base_dir: Path, run_state: Path) -> None:
    async with open_tools(run_state, base_dir) as client:
        assert names(ToolSearchExposure(client)) == ["search_tools"]


async def test_search_loads_schemas_that_persist(base_dir: Path, run_state: Path) -> None:
    async with open_tools(run_state, base_dir) as client:
        exposure = ToolSearchExposure(client)
        result = await exposure.execute("search_tools", {"query": "read rows from a spreadsheet"})
        assert "read_rows" in result and len(result.splitlines()) == TOP_K + 1
        first = names(exposure)
        assert "read_rows" in first and len(first) == TOP_K + 1
        full = next(t for t in exposure.tools() if t["function"]["name"] == "read_rows")
        assert "sheet_id" in full["function"]["parameters"]["properties"]

        await exposure.execute("search_tools", {"query": "create a follow-up task for a person"})
        second = names(exposure)
        assert second[: len(first)] == first and "create_task" in second
        assert len(second) == len(set(second))

        again = await exposure.execute("search_tools", {"query": "read rows from a spreadsheet"})
        assert "read_rows" in again and names(exposure) == second


async def test_ranking_is_deterministic(base_dir: Path, run_state: Path) -> None:
    async with open_tools(run_state, base_dir) as client:
        results = [await ToolSearchExposure(client).execute("search_tools", {"query": "find contact email"}) for _ in range(3)]
    assert len(set(results)) == 1


@pytest.mark.parametrize(("query", "tool"), [("search documents by keyword", "search_docs"), ("update a deal stage", "update_deal"), ("add a note to a contact", "add_note"), ("export spreadsheet as csv", "export_sheet_csv")])
async def test_search_finds_the_obvious_tool(base_dir: Path, run_state: Path, query: str, tool: str) -> None:
    async with open_tools(run_state, base_dir) as client:
        exposure = ToolSearchExposure(client)
        await exposure.execute("search_tools", {"query": query})
        assert tool in names(exposure)


async def test_tool_that_is_not_loaded_gets_a_clear_error(base_dir: Path, run_state: Path) -> None:
    async with open_tools(run_state, base_dir) as client:
        exposure = ToolSearchExposure(client)
        result = await exposure.execute("get_contact", {"contact_id": "C-0001"})
        assert "not loaded" in result and "search_tools" in result
        assert client.calls == []


async def test_bad_or_unmatched_queries_load_nothing(base_dir: Path, run_state: Path) -> None:
    async with open_tools(run_state, base_dir) as client:
        exposure = ToolSearchExposure(client)
        assert (await exposure.execute("search_tools", {})).startswith("Error")
        assert (await exposure.execute("search_tools", {"query": "  "})).startswith("Error")
        assert await exposure.execute("search_tools", {"query": "zzzzqqq"}) == "No matching tools."
        assert names(exposure) == ["search_tools"]


async def test_results_are_returned_verbatim_like_condition_a(base_dir: Path, run_state: Path) -> None:
    async with open_tools(run_state, base_dir) as client:
        direct = DirectExposure(client)
        search = ToolSearchExposure(client)
        await search.execute("search_tools", {"query": "read rows from a spreadsheet"})
        arguments = {"sheet_id": "orders"}
        result = await search.execute("read_rows", arguments)
        assert result == await direct.execute("read_rows", arguments)
        assert len(result) > 2_000_000


async def test_schemas_match_condition_a(base_dir: Path, run_state: Path) -> None:
    async with open_tools(run_state, base_dir) as client:
        direct = {t["function"]["name"]: t for t in DirectExposure(client).tools()}
        search = ToolSearchExposure(client)
        await search.execute("search_tools", {"query": "read rows from a spreadsheet"})
        for tool in search.tools()[1:]:
            assert tool == direct[tool["function"]["name"]]


async def test_only_the_condition_block_differs_between_conditions(base_dir: Path, run_state: Path) -> None:
    async with open_tools(run_state, base_dir) as client:
        code = CodeExposure(client)
        exposures = [DirectExposure(client), ToolSearchExposure(client), code]
        prompts = [system_prompt(exposure) for exposure in exposures]
        await code.close()
    divider = "\n\n## How tools are exposed\n"
    assert {prompt.split(divider)[0] for prompt in prompts} == {SYSTEM_CORE}
    assert len({prompt.split(divider)[1] for prompt in prompts}) == 3


async def test_runner_end_to_end(tmp_path: Path, base_dir: Path) -> None:
    def script(kwargs: dict[str, Any]) -> Any:
        last = kwargs["messages"][-1]
        if last["role"] == "user":
            return reply(calls=[("search_tools", json.dumps({"query": "get one contact by id"}))])
        if "now available" in last["content"]:
            return reply(calls=[("get_contact", '{"contact_id":"C-0123"}')])
        return reply(f"<answer>{json.loads(last['content'])['email']}</answer>")

    client = FakeClient(script)
    await runner.amain(args_for(conditions="B"), client, tmp_path / "r", tmp_path / "c", base_dir)
    row = runner.read_rows(tmp_path / "r" / "runs.jsonl")[0]
    assert row["success"] is True and row["model_turns"] == 3
    # tool_calls counts real MCP calls in every condition, so search_tools is not included.
    assert row["tool_calls"] == 1 and row["code_executions"] == 0
    assert [t["function"]["name"] for t in client.requests[0]["tools"]] == ["search_tools"]
    assert "get_contact" in [t["function"]["name"] for t in client.requests[1]["tools"]]
