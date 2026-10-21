"""Verify downloaded data uses the same blob checksum as Git itself."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location("fetch_upstream", Path(__file__).parents[1] / "scripts/fetch_upstream.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize("content", [b"", b"hello\n", bytes(range(256))])
def test_blob_hash_matches_git(content):
    expected = subprocess.check_output(["git", "hash-object", "--stdin"], input=content).decode().strip()
    assert module.blob_hash(content) == expected
