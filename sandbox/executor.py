"""Runs submitted Python in a locked-down Docker container."""

import asyncio
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from servers.state import ROOT

IMAGE = "bench-sandbox:1"
TIMEOUT_S = 30.0
MEMORY = "512m"
OOM_EXIT_CODE = 137
# Enough to fill the truncated reply, and it stops a print loop from exhausting host memory.
CAPTURE_LIMIT_BYTES = 1024 * 1024


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool

    @property
    def failed(self) -> bool:
        return self.timed_out or self.exit_code != 0

    @property
    def out_of_memory(self) -> bool:
        return not self.timed_out and self.exit_code == OOM_EXIT_CODE


def docker_command(name: str, run_dir: Path, script: str) -> list[str]:
    return [
        "docker", "run", "--rm", "--name", name,
        "--network", "none",
        "--memory", MEMORY, "--memory-swap", MEMORY,
        "--cpus", "1", "--pids-limit", "128",
        "--read-only", "--tmpfs", "/tmp",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "-e", "PYTHONHASHSEED=0", "-e", "PYTHONPATH=/", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PYTHONUNBUFFERED=1",
        "-v", f"{ROOT / 'toolpkg'}:/toolpkg:ro",
        "-v", f"{run_dir / 'sock'}:/sock",
        "-v", f"{run_dir / 'workspace'}:/workspace",
        "-w", "/workspace",
        IMAGE, "python", f"/workspace/{script}",
    ]  # fmt: skip


async def _drain(stream: asyncio.StreamReader, sink: bytearray) -> None:
    while chunk := await stream.read(65536):
        if len(sink) < CAPTURE_LIMIT_BYTES:
            sink.extend(chunk[: CAPTURE_LIMIT_BYTES - len(sink)])


async def run_code(code: str, run_dir: Path, timeout_s: float = TIMEOUT_S) -> ExecResult:
    script = "_submitted.py"
    (run_dir / "workspace" / script).write_text(code, encoding="utf-8")
    name = f"bench-{uuid.uuid4().hex[:16]}"
    process = await asyncio.create_subprocess_exec(*docker_command(name, run_dir, script), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    assert process.stdout is not None and process.stderr is not None
    stdout, stderr = bytearray(), bytearray()
    drains = asyncio.gather(_drain(process.stdout, stdout), _drain(process.stderr, stderr))
    timed_out = False
    try:
        await asyncio.wait_for(process.wait(), timeout_s)
    except TimeoutError:
        timed_out = True
        killer = await asyncio.create_subprocess_exec("docker", "rm", "-f", name, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await killer.wait()
        await process.wait()
    await drains
    return ExecResult(stdout.decode(errors="replace"), stderr.decode(errors="replace"), None if timed_out else process.returncode, timed_out)
