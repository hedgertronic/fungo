"""Cache publication invariants, including interrupted writes."""

from pathlib import Path

import pytest

from fungo._cache import atomic_write


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
