"""Tests for filesystem tool (read_file, write_file, list_dir)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.tools import filesystem


@pytest.fixture()
def home_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the filesystem module at a temporary HOME."""
    monkeypatch.setattr(filesystem, "_HOME", tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_read_file_success(home_tmp: Path) -> None:
    f = home_tmp / "hello.txt"
    f.write_text("hello world")
    result = await filesystem.read_file(str(f))
    assert result == "hello world"


@pytest.mark.asyncio
async def test_read_file_truncation(home_tmp: Path) -> None:
    f = home_tmp / "big.txt"
    content = "x" * 1000
    f.write_text(content)
    result = await filesystem.read_file(str(f), read_cap=100)
    assert "truncated" in result
    assert "1000 total chars" in result
    assert result.endswith("x" * 100)


@pytest.mark.asyncio
async def test_read_file_offset_and_limit(home_tmp: Path) -> None:
    f = home_tmp / "data.txt"
    f.write_text("0123456789")
    result = await filesystem.read_file(str(f), offset=2, limit=3)
    assert result == "234"


@pytest.mark.asyncio
async def test_read_file_not_found(home_tmp: Path) -> None:
    with pytest.raises(FileNotFoundError):
        await filesystem.read_file(str(home_tmp / "nope.txt"))


@pytest.mark.asyncio
async def test_write_file_creates_file(home_tmp: Path) -> None:
    target = home_tmp / "sub" / "dir" / "out.txt"
    await filesystem.write_file(str(target), "payload")
    assert target.read_text() == "payload"


@pytest.mark.asyncio
async def test_write_file_append(home_tmp: Path) -> None:
    f = home_tmp / "log.txt"
    f.write_text("line1\n")
    await filesystem.write_file(str(f), "line2\n", append=True)
    assert f.read_text() == "line1\nline2\n"


@pytest.mark.asyncio
async def test_write_file_overwrite(home_tmp: Path) -> None:
    f = home_tmp / "out.txt"
    f.write_text("old")
    await filesystem.write_file(str(f), "new")
    assert f.read_text() == "new"


@pytest.mark.asyncio
async def test_list_dir_basic(home_tmp: Path) -> None:
    (home_tmp / "a.txt").write_text("a")
    (home_tmp / "b").mkdir()
    result = await filesystem.list_dir(str(home_tmp))
    entries = json.loads(result)
    names = {e["name"] for e in entries}
    assert "a.txt" in names
    assert "b" in names
    file_entry = next(e for e in entries if e["name"] == "a.txt")
    assert file_entry["type"] == "file"
    assert file_entry["size"] == 1
    dir_entry = next(e for e in entries if e["name"] == "b")
    assert dir_entry["type"] == "dir"


@pytest.mark.asyncio
async def test_list_dir_recursive(home_tmp: Path) -> None:
    sub = home_tmp / "sub"
    sub.mkdir()
    (sub / "inner.txt").write_text("hi")
    result = await filesystem.list_dir(str(home_tmp), recursive=True)
    entries = json.loads(result)
    names = {e["name"] for e in entries}
    assert "sub/inner.txt" in names


@pytest.mark.asyncio
async def test_list_dir_not_a_directory(home_tmp: Path) -> None:
    f = home_tmp / "file.txt"
    f.write_text("x")
    with pytest.raises(NotADirectoryError):
        await filesystem.list_dir(str(f))


@pytest.mark.asyncio
async def test_path_escape_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(filesystem, "_HOME", tmp_path)
    with pytest.raises(PermissionError, match="outside allowed prefixes"):
        await filesystem.read_file("/etc/passwd")


@pytest.mark.asyncio
async def test_symlink_escape_blocked(home_tmp: Path) -> None:
    link = home_tmp / "evil_link"
    link.symlink_to("/etc/passwd")
    with pytest.raises(PermissionError):
        await filesystem.read_file(str(link))
