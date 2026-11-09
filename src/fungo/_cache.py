"""Private helpers for publishing complete cache files."""

from pathlib import Path
from tempfile import TemporaryDirectory


def atomic_write(path: Path, data: bytes) -> None:
    """Replace ``path`` only after all bytes have been written and closed.

    The parent directory must exist. Staging on the same filesystem makes
    replacement atomic: readers see either the previous file or the complete
    new file. Failed writes leave the previous file intact and propagate the
    error; temporary files are cleaned up on success and failure. This does
    not provide a transaction across multiple cache files or power-loss durability.
    """
    with TemporaryDirectory(prefix=".fungo-", dir=path.parent) as directory:
        staged = Path(directory) / path.name
        staged.write_bytes(data)
        staged.replace(path)
