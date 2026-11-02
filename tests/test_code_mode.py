"""Condition C tests against real Docker containers. No model API is involved."""

import asyncio
import json
import shutil
import subprocess
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

import runner
from agents.code_mode import OUTPUT_LIMIT, PACKAGE_DIR, TRUNCATION_MARKER, CodeExposure
from agents.common import SYSTEM_CORE, system_prompt
from sandbox.executor import IMAGE, TIMEOUT_S, docker_command, run_code
from servers.client import open_tools
from servers.state import ROOT, load_crm
from tasks.build_tasks import load_tasks
from tasks.checkers import check
from tests.test_runner import FakeClient, args_for, reply
from toolpkg_gen import render_all

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is not installed")
TASKS = {task["id"]: task for task in load_tasks()}


@pytest.fixture(scope="session", autouse=True)
def sandbox_image() -> None:
    subprocess.run(["docker", "build", "-q", "-t", IMAGE, str(ROOT / "sandbox")], check=True, capture_output=True)


@pytest_asyncio.fixture
async def exposure(base_dir: Path, run_state: Path) -> AsyncIterator[CodeExposure]:
    # pytest sets up and tears down in different tasks, but the MCP client must enter and exit in one.
    ready: asyncio.Future[CodeExposure] = asyncio.get_running_loop().create_future()
    finished = asyncio.Event()

    async def own_client() -> None:
        async with open_tools(run_state, base_dir) as client:
            item = CodeExposure(client)
            await item.start()
            ready.set_result(item)
            await finished.wait()
            await item.close()

    owner = asyncio.create_task(own_client())
    try:
        yield await ready
    finally:
        finished.set()
        await owner


async def run(exposure: CodeExposure, code: str) -> str:
    return await exposure.execute("run_python", {"code": code})


async def test_generated_package_is_current() -> None:
    expected = await render_all()
    found = {str(p.relative_to(PACKAGE_DIR)): p.read_text() for p in PACKAGE_DIR.rglob("*.py") if "__pycache__" not in p.parts}
    assert found == expected


async def test_package_has_one_module_per_tool_with_a_docstring(base_dir: Path, run_state: Path) -> None:
    async with open_tools(run_state, base_dir) as client:
        names = {tool.name for tool in client.tools}
    modules = {p.stem: p.read_text() for p in PACKAGE_DIR.glob("*/*.py") if p.stem != "__init__"}
    assert set(modules) == names and len(names) == 32
    assert 'limit: int | None = None' in modules["read_rows"]
    assert "every row from offset" in modules["read_rows"]
    assert "Literal['exact', 'contains'] = 'exact'" in modules["find_rows"]


async def test_tool_call_reaches_the_server_and_prints(exposure: CodeExposure) -> None:
    code = "from toolpkg.crm.get_contact import get_contact\nprint(get_contact(contact_id='C-0123')['contact_id'])"
    assert (await run(exposure, code)).strip() == "C-0123"
    assert exposure.gateway.client.calls == ["get_contact"]
    assert exposure.code_executions == 1 and exposure.sandbox_errors == 0


async def test_large_results_cross_the_socket_without_reaching_the_model(exposure: CodeExposure) -> None:
    code = "from toolpkg.sheets.read_rows import read_rows\nprint(len(read_rows(sheet_id='orders')['rows']))"
    assert (await run(exposure, code)).strip() == "10000"


async def test_csv_comes_back_as_text(exposure: CodeExposure) -> None:
    code = "from toolpkg.sheets.export_sheet_csv import export_sheet_csv\nprint(export_sheet_csv(sheet_id='sales_reps').splitlines()[0])"
    assert (await run(exposure, code)).startswith("rep_id,")


async def test_crm_write_lands_in_the_run_state(exposure: CodeExposure) -> None:
    code = "from toolpkg.crm.create_task import create_task\nprint(create_task(title='x', assignee='y', due_date='2026-04-01')['task_id'])"
    assert (await run(exposure, code)).strip() == "T-0001"
    assert load_crm()["tasks"][0]["title"] == "x"


async def test_tool_errors_raise_inside_the_script(exposure: CodeExposure) -> None:
    code = """from toolpkg._bridge import ToolError
from toolpkg.crm.get_contact import get_contact
try:
    get_contact(contact_id='nope')
except ToolError as error:
    print('caught', error)
"""
    assert (await run(exposure, code)).startswith("caught")


async def test_gateway_rejects_unknown_tools(exposure: CodeExposure) -> None:
    code = """from toolpkg._bridge import call, ToolError
try:
    call('read_truth', {})
except ToolError as error:
    print(error)
"""
    assert "Unknown tool" in await run(exposure, code)


async def test_script_failure_returns_the_traceback_and_counts(exposure: CodeExposure) -> None:
    output = await run(exposure, "raise ValueError('bad thing')")
    assert "exit code 1" in output and "bad thing" in output
    assert exposure.sandbox_errors == 1


async def test_no_network(exposure: CodeExposure) -> None:
    code = """import socket
s = socket.socket()
s.settimeout(3)
try:
    s.connect(('1.1.1.1', 53))
    print('CONNECTED')
except OSError as error:
    print('blocked', error)
print(socket.if_nameindex())
"""
    output = await run(exposure, code)
    assert "CONNECTED" not in output and "blocked" in output
    assert "eth" not in output


async def test_package_and_root_are_read_only_and_workspace_is_not(exposure: CodeExposure) -> None:
    code = """for path in ['/toolpkg/x.py', '/toolpkg/crm/get_contact.py', '/x', '/usr/x']:
    try:
        open(path, 'a').close()
        print('WROTE', path)
    except OSError as error:
        print('denied', path)
open('/workspace/ok.txt', 'w').write('saved')
open('/tmp/ok.txt', 'w').write('saved')
print('workspace ok')
"""
    output = await run(exposure, code)
    assert "WROTE" not in output and output.count("denied") == 4 and "workspace ok" in output


async def test_workspace_persists_between_scripts_but_variables_do_not(exposure: CodeExposure) -> None:
    await run(exposure, "open('/workspace/state.txt', 'w').write('kept')\nx = 1")
    output = await run(exposure, "print(open('/workspace/state.txt').read())\nprint('x' in globals())")
    assert output.split() == ["kept", "False"]


async def test_host_data_and_secrets_are_not_visible(exposure: CodeExposure, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", "sk-must-not-leak")
    code = """import os
# GPG_KEY is the public release-signing key set by the official Python image.
print(sorted(k for k in os.environ if k != 'GPG_KEY' and ('KEY' in k or 'OPENCODE' in k or 'MCP' in k)))
print([p for p in ['/data', '/.env', '/home/ridz', '/repo', '/cache', '/sock/crm.json'] if os.path.exists(p)])
print(sorted(os.listdir('/toolpkg')))
print(os.getenv('PYTHONHASHSEED'), os.getuid() != 0)
"""
    lines = (await run(exposure, code)).splitlines()
    assert lines[0] == "[]" and lines[1] == "[]"
    assert "sk-must-not-leak" not in "\n".join(lines)
    assert not {"truth.json", "crm.json", ".env"} & set(eval(lines[2]))
    assert lines[3] == "0 True"


def test_docker_flags_enforce_the_limits() -> None:
    command = docker_command("n", Path("/tmp/r"), "s.py")
    joined = " ".join(command)
    for flag in ["--network none", "--memory 512m", "--memory-swap 512m", "--read-only", "--cap-drop ALL", "--pids-limit 128", ":/toolpkg:ro", "no-new-privileges"]:
        assert flag in joined
    assert TIMEOUT_S == 30


async def test_timeout_kills_the_container(tmp_path: Path) -> None:
    (tmp_path / "sock").mkdir()
    (tmp_path / "workspace").mkdir()
    result = await asyncio.wait_for(run_code("import time\nprint('started', flush=True)\ntime.sleep(60)", tmp_path, timeout_s=3), 30)
    assert result.timed_out and result.failed and "started" in result.stdout
    names = subprocess.run(["docker", "ps", "-q", "--filter", "name=bench-"], capture_output=True, text=True).stdout
    assert names.strip() == ""


async def test_timeout_message_and_count(exposure: CodeExposure, monkeypatch: pytest.MonkeyPatch) -> None:
    from agents import code_mode

    async def fast(code: str, run_dir: Path) -> Any:
        return await run_code(code, run_dir, timeout_s=2)

    monkeypatch.setattr(code_mode, "run_code", fast)
    assert "exceeded the 30 second limit" in await run(exposure, "import time\ntime.sleep(20)")
    assert exposure.sandbox_errors == 1


async def test_memory_limit_kills_or_fails_the_script(exposure: CodeExposure) -> None:
    code = """blocks = []
while True:
    blocks.append(bytearray(50 * 1024 * 1024))
    for i in range(0, len(blocks[-1]), 4096):
        blocks[-1][i] = 1
"""
    output = await run(exposure, code)
    assert "out of memory" in output or "MemoryError" in output
    assert exposure.sandbox_errors == 1


async def test_output_is_truncated_at_the_limit_and_counted(exposure: CodeExposure) -> None:
    output = await run(exposure, f"print('x' * {OUTPUT_LIMIT * 3})")
    assert output.endswith(TRUNCATION_MARKER) and len(output) == OUTPUT_LIMIT + len(TRUNCATION_MARKER)
    assert exposure.truncated_outputs == 1


async def test_output_at_the_limit_is_not_truncated(exposure: CodeExposure) -> None:
    output = await run(exposure, f"print('x' * {OUTPUT_LIMIT - 1})")
    assert not output.endswith(TRUNCATION_MARKER) and exposure.truncated_outputs == 0


async def test_print_flood_does_not_hang(exposure: CodeExposure) -> None:
    output = await asyncio.wait_for(run(exposure, "for _ in range(200):\n    print('y' * 100000)"), 60)
    assert output.endswith(TRUNCATION_MARKER)


async def test_empty_output_is_explained(exposure: CodeExposure) -> None:
    assert "printed nothing" in await run(exposure, "x = 1")


async def test_list_and_read_files(exposure: CodeExposure) -> None:
    assert (await exposure.execute("list_files", {})).split() == ["crm/", "docs/", "sheets/"]
    listing = (await exposure.execute("list_files", {"path": "sheets"})).split()
    assert len(listing) == 10 and "read_rows.py" in listing and not [n for n in listing if n.startswith("_")]
    assert "def get_row" in await exposure.execute("read_file", {"path": "sheets/get_row.py"})


@pytest.mark.parametrize("path", ["../.env", "../data/truth.json", "/etc/passwd", "sheets/../../.env", "sheets/../../data/crm.json"])
async def test_file_tools_stay_inside_the_package(exposure: CodeExposure, path: str) -> None:
    assert (await exposure.execute("read_file", {"path": path})).startswith("Error")


@pytest.mark.parametrize("path", ["..", "../data", "/etc"])
async def test_listing_stays_inside_the_package(exposure: CodeExposure, path: str) -> None:
    assert (await exposure.execute("list_files", {"path": path})).startswith("Error")


async def test_bad_tool_input_is_reported(exposure: CodeExposure) -> None:
    assert "missing argument" in await exposure.execute("run_python", {})
    assert "unknown tool" in await exposure.execute("read_rows", {"sheet_id": "orders"})
    assert exposure.code_executions == 0


async def test_system_prompt_core_matches_other_conditions(exposure: CodeExposure) -> None:
    prompt = system_prompt(exposure)
    assert prompt.startswith(SYSTEM_CORE) and "toolpkg" in prompt
    assert "toolpkg" not in SYSTEM_CORE


ORACLE_CODE = {
    "L02": """from toolpkg.sheets.read_rows import read_rows
rows = read_rows(sheet_id='orders')['rows']
print(sum(r['region'] == 'APAC' and r['channel'] == 'partner' and r['discount_pct'] >= 15 and r['status'] in ('shipped', 'completed') for r in rows))
""",
    "M04": """import re
from toolpkg.docs.list_docs import list_docs
from toolpkg.docs.get_doc_section import get_doc_section
from toolpkg.crm.create_contact import create_contact
doc = next(d for d in list_docs()['docs'] if d['title'] == {title!r})
body = get_doc_section(doc_id=doc['doc_id'], heading='Key stakeholders')['body']
for name, title, email in re.findall(r'^- (.+?), (.+?), (\\S+@\\S+)$', body, re.M):
    create_contact(name=name, email=email, company={company!r}, title=title)
print('done')
""",
    "S05": """from toolpkg.crm.get_contact import get_contact
print(get_contact(contact_id='C-0123')['email'])
""",
}


@pytest.mark.parametrize("task_id", ORACLE_CODE)
async def test_oracle_as_code_passes_each_category(task_id: str, exposure: CodeExposure, base_dir: Path, run_state: Path) -> None:
    task = TASKS[task_id]
    output = await run(exposure, ORACLE_CODE[task_id].format(**task.get("params", {})) if task_id == "M04" else ORACLE_CODE[task_id])
    state = json.loads((run_state / "crm.json").read_text())
    base = json.loads((base_dir / "crm.json").read_text())
    assert check(task, f"<answer>{output.strip()}</answer>", state, base), output


async def test_runner_logs_code_mode_metrics(tmp_path: Path, base_dir: Path) -> None:
    code = ORACLE_CODE["S05"]

    def script(kwargs: dict[str, Any]) -> Any:
        last = kwargs["messages"][-1]
        if last["role"] == "user":
            return reply(calls=[("run_python", json.dumps({"code": code}))])
        return reply(f"<answer>{last['content'].strip()}</answer>")

    client = FakeClient(script)
    await runner.amain(args_for(conditions="C"), client, tmp_path / "r", tmp_path / "c", base_dir)
    row = runner.read_rows(tmp_path / "r" / "runs.jsonl")[0]
    assert row["success"] is True and row["code_executions"] == 1 and row["tool_calls"] == 1 and row["sandbox_errors"] == 0
    assert [tool["function"]["name"] for tool in client.requests[0]["tools"]] == ["list_files", "read_file", "run_python"]
    assert json.loads((tmp_path / "r" / "run_meta.json").read_text())["sandbox_image"].startswith("sha256:")
    assert not list(Path(tempfile.gettempdir()).glob("bench-*/sock/gateway.sock"))
