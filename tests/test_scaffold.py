from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_dependencies_import() -> None:
    import dotenv  # noqa: F401
    import matplotlib  # noqa: F401
    import mcp  # noqa: F401
    import openai  # noqa: F401
    import pandas  # noqa: F401
    import rank_bm25  # noqa: F401


def test_layout_exists() -> None:
    for name in ["data", "servers", "toolpkg", "tasks", "agents", "sandbox", "cache", "results", "analysis"]:
        assert (ROOT / name).is_dir(), name


def test_env_is_gitignored() -> None:
    assert ".env" in (ROOT / ".gitignore").read_text().splitlines()
