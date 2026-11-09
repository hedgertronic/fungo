"""Cache publication invariants, including interrupted writes."""

from pathlib import Path

import pytest

from fungo import lookup
from fungo._cache import atomic_write, cache_root
from fungo.bbref import cache as bbref_cache
from fungo.lahman import tables as lahman_tables
from fungo.retrosheet import files as retrosheet_files


def test_cache_root_prefers_xdg_cache_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cache_root() == tmp_path / "fungo"


@pytest.mark.parametrize("value", [None, ""])
def test_cache_root_falls_back_to_home_cache(tmp_path, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    else:
        monkeypatch.setenv("XDG_CACHE_HOME", value)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cache_root() == tmp_path / ".cache" / "fungo"


def test_module_cache_dirs_share_the_root(tmp_path, monkeypatch):
    root = cache_root()
    assert root == lookup.CACHE_DIR
    assert root / "lahman" == lahman_tables.CACHE_DIR
    assert root / "retrosheet" == retrosheet_files.CACHE_DIR
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert bbref_cache._default_cache_dir() == tmp_path / "fungo" / "bbref_cache"


@pytest.mark.parametrize("old", [None, b"previous"])
def test_atomic_write_publishes_only_complete_bytes(tmp_path, monkeypatch, old):
    target = tmp_path / "entry"
    if old is not None:
        target.write_bytes(old)
    replace = Path.replace
    publications = []

    def observe(staged, destination):
        publications.append(staged.read_bytes())
        assert (target.read_bytes() if target.exists() else None) == old
        return replace(staged, destination)

    monkeypatch.setattr(Path, "replace", observe)
    atomic_write(target, b"complete new response")
    assert publications == [b"complete new response"]
    assert target.read_bytes() == b"complete new response"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("old", [None, b"previous"])
@pytest.mark.parametrize("failure", ["write", "replace"])
def test_atomic_write_failure_preserves_previous_state(
    tmp_path, monkeypatch, old, failure
):
    target = tmp_path / "entry"
    if old is not None:
        target.write_bytes(old)
    write = Path.write_bytes

    def fail(path, *args):
        if failure == "write":
            write(path, b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes" if failure == "write" else "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        atomic_write(target, b"complete new response")
    assert (target.read_bytes() if target.exists() else None) == old
    assert list(tmp_path.iterdir()) == ([] if old is None else [target])
