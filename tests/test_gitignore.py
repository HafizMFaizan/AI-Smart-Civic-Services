"""Regression tests for the .gitignore hardening fix.

No git repository is required -- these tests check the file's content and
pattern semantics directly rather than shelling out to `git check-ignore`.
"""

import fnmatch
from pathlib import Path

GITIGNORE_PATH = Path(__file__).resolve().parent.parent / ".gitignore"


def _non_comment_lines() -> list[str]:
    lines = GITIGNORE_PATH.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def test_gitignore_contains_required_rules():
    lines = _non_comment_lines()

    assert "*.db" in lines
    assert ".env" in lines
    assert "!.env.example" in lines


def test_gitignore_db_pattern_matches_runtime_database_files():
    lines = _non_comment_lines()
    db_pattern = next(line for line in lines if line == "*.db")

    assert fnmatch.fnmatch("civic_services.db", db_pattern)
    assert fnmatch.fnmatch("database/civic_services.db".split("/")[-1], db_pattern)


def test_gitignore_env_pattern_does_not_match_env_example():
    lines = _non_comment_lines()
    env_pattern = next(line for line in lines if line == ".env")

    assert fnmatch.fnmatch(".env", env_pattern)
    assert not fnmatch.fnmatch(".env.example", env_pattern)


def test_gitignore_excludes_generated_and_local_tool_files():
    # Found during the Phase 4B final audit: __pycache__, .pytest_cache, and
    # .claude/settings.local.json were all present on disk and unignored --
    # committing them would pollute the repo with generated/machine-local files.
    lines = _non_comment_lines()

    assert "__pycache__/" in lines
    assert "*.pyc" in lines
    assert ".pytest_cache/" in lines
    assert ".claude/settings.local.json" in lines
