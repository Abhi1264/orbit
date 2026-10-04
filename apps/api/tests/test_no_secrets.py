from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SECRETS = ("AMPLITUDE_API_KEY", "METABASE_ADMIN_PASSWORD", "MB_ENCRYPTION_SECRET_KEY", "LLM_API_KEY")
HARDCODED_AMPLITUDE_KEY = re.compile(r"(?i)amplitude[_-]?api[_-]?key\W{1,4}[0-9a-f]{32}\b")
MAX_BYTES = 2_000_000


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [REPO / p for p in out.decode().split("\0") if p]


def tracked_texts() -> dict[str, str]:
    texts = {}
    for path in tracked_files():
        if path.is_file() and path.stat().st_size <= MAX_BYTES:
            texts[str(path.relative_to(REPO))] = path.read_text(errors="ignore")
    return texts


def env_values(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("\"'")
    return values


def test_env_files_are_not_tracked() -> None:
    env_files = [p.name for p in tracked_files() if p.name.startswith(".env")]
    assert env_files == [".env.example"]


def test_env_example_ships_integration_secrets_empty() -> None:
    example = env_values(REPO / ".env.example")
    for key in SECRETS:
        assert example.get(key) == "", f"{key} must be listed in .env.example with no value"


def test_no_amplitude_key_is_hardcoded() -> None:
    assert [name for name, text in tracked_texts().items() if HARDCODED_AMPLITUDE_KEY.search(text)] == []


def test_configured_secrets_are_not_in_tracked_files() -> None:
    local = env_values(REPO / ".env") if (REPO / ".env").is_file() else {}
    secrets = [v for key in SECRETS if len(v := os.environ.get(key) or local.get(key, "")) >= 8]
    if not secrets:
        pytest.skip("no secrets configured")
    leaks = sorted({name for name, text in tracked_texts().items() for s in secrets if s in text})
    assert leaks == [], "configured secrets found in these tracked files"
