"""Lahman database access seam — SABR page + Box shared-link internals.

SABR hosts the Lahman CSVs on its Box account behind shared links that change
with each annual release, so the access path is discovered at runtime in three
steps (all verified live 2026-07-11):

1. Fetch ``https://sabr.org/lahman-database/`` and pick the Box shared link
   whose anchor text names the comma-delimited (CSV) version.
2. Fetch the Box shared-folder page(s) and parse the embedded folder JSON —
   each file object carries ``"typedID":"f_{id}"`` followed by ``"name"``;
   the listing is paginated (``"pageCount"``; ``?page=N`` selects a page).
3. Download a table via Box's shared-file download route,
   ``/index.php?rm=box_download_shared_file&shared_name={hash}&file_id=f_{id}``,
   which returns ``text/csv`` with a ``Content-Disposition`` attachment.

Steps 2 and 3 ride an undocumented Box internal — the same fragility class as
the FanGraphs okhttp UA exemption (:mod:`fungo.fangraphs.api`). Every failure
mode raises :class:`~fungo.exceptions.LahmanError` naming the condition and
its recovery step (``refresh()`` for download failures, where a stale cached
index after an annual release is the likely cause; re-verification against
the SABR page for discovery failures); nothing here retries or falls back
silently. Both sabr.org (WordPress) and sabr.box.com accept the
default fungo User-Agent (verified 2026-07-11) — no browser impersonation is
needed, so requests go through :mod:`fungo.http` unmodified.
"""

from __future__ import annotations

import re

from fungo import http
from fungo.exceptions import LahmanError

#####################################################################
# URLs / constants
#####################################################################

SABR_URL = "https://sabr.org/lahman-database/"
BOX_BASE_URL = "https://sabr.box.com"

# The CSV folder's shared-link hash for version 2025 (verified 2026-07-11).
# A reference for manual recovery only — discovery always runs against the
# SABR page at runtime, since this hash changes with each annual release.
FALLBACK_SHARED_NAME = "y1prhc795jk8zvmelfd3jq7tl389y6cd"

_REVERIFY_HINT = (
    "The access path rides an undocumented Box internal and needs "
    f"re-verification against {SABR_URL} — do not retry."
)

# Download failures get a different first step: each annual release changes
# the Box file ids, so a stale cached index is the most likely cause and
# refresh() is the fix. Discovery failures keep the plain re-verify hint —
# refresh() would just re-run the failing discovery.
_DOWNLOAD_HINT = (
    "The most likely cause is a stale cached index after a new annual "
    "release — call fungo.lahman.refresh() and retry once. If that also "
    "fails, the access path rides an undocumented Box internal and needs "
    f"re-verification against {SABR_URL}."
)

# Box shared links on the SABR page, captured with their anchor text so the
# CSV ("Comma-delimited version") link can be told apart from SQL/Access.
_BOX_ANCHOR_RE = re.compile(
    r'<a[^>]+href="https://sabr\.box\.com/s/([A-Za-z0-9]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)

# One file object in Box's embedded folder JSON: "typedID":"f_{id}" precedes
# "name" within the same object ([^{}]*? keeps the match inside one object).
_FILE_ENTRY_RE = re.compile(r'"typedID":"(f_\d+)"[^{}]*?"name":"([^"]+)"')

# Total page count of the paginated folder listing.
_PAGE_COUNT_RE = re.compile(r'"pageCount":(\d+)')


#####################################################################
# Discovery
#####################################################################


def discover_shared_name() -> str:
    """Find the CSV folder's Box shared-link hash on the SABR Lahman page.

    Fetches ``sabr.org/lahman-database`` and returns the hash from the Box
    shared link whose anchor text names the comma-delimited version.

    Returns:
        The shared-link hash (the ``{hash}`` in ``sabr.box.com/s/{hash}``).

    Raises:
        LahmanError: If the page carries no Box shared links, or none is
            labeled as the comma-delimited (CSV) version.
        RequestError: On transport failure fetching the SABR page.
    """
    page = http.request_bytes(SABR_URL).decode("utf-8", errors="replace")

    anchors: list[tuple[str, str]] = _BOX_ANCHOR_RE.findall(page)
    if not anchors:
        raise LahmanError(
            f"No Box shared links found on {SABR_URL} — the SABR page shape "
            f"has changed. {_REVERIFY_HINT}"
        )

    for shared_name, label in anchors:
        if "comma" in label.lower():
            return shared_name

    raise LahmanError(
        f"Box shared links found on {SABR_URL}, but none labeled as the "
        f"comma-delimited (CSV) version. {_REVERIFY_HINT}"
    )


def fetch_table_index(shared_name: str) -> dict[str, str]:
    """Map table names to Box file ids from the shared-folder listing.

    Walks every page of the Box folder (the embedded JSON carries
    ``"pageCount"``; absent means a single page) and keeps the ``.csv``
    entries, keyed by filename stem (``People.csv`` -> ``People``).

    Args:
        shared_name: The folder's shared-link hash from
            :func:`discover_shared_name`.

    Returns:
        ``{table_name: file_id}``, e.g. ``{"People": "f_2084263017537"}``.

    Raises:
        LahmanError: If a folder page yields no parseable file entries, or
            the listing contains no ``.csv`` files.
        RequestError: On transport failure fetching a folder page.
    """
    files: dict[str, str] = {}
    page_num = 1
    page_count = 1

    while page_num <= page_count:
        page = http.request_bytes(
            f"{BOX_BASE_URL}/s/{shared_name}",
            params={"page": page_num},
        ).decode("utf-8", errors="replace")

        entries = _FILE_ENTRY_RE.findall(page)
        if not entries:
            raise LahmanError(
                f"No file entries parsed from Box folder page {page_num} of "
                f"shared link {shared_name!r} — Box's embedded folder JSON no "
                f"longer matches the expected shape. {_REVERIFY_HINT}"
            )

        for file_id, filename in entries:
            if filename.lower().endswith(".csv"):
                files[filename[:-4]] = file_id

        if page_num == 1:
            match = _PAGE_COUNT_RE.search(page)
            page_count = int(match.group(1)) if match else 1
        page_num += 1

    if not files:
        raise LahmanError(
            f"Box folder listing for shared link {shared_name!r} contains no "
            f".csv files — the SABR CSV folder layout has changed. "
            f"{_REVERIFY_HINT}"
        )

    return files


#####################################################################
# Download
#####################################################################


def download_table(shared_name: str, file_id: str, table: str) -> bytes:
    """Download one table's CSV bytes via Box's shared-file download route.

    Args:
        shared_name: The folder's shared-link hash.
        file_id: The Box file id (``f_``-prefixed) from
            :func:`fetch_table_index`.
        table: Table name, used only in error messages.

    Returns:
        The raw CSV bytes (a UTF-8 BOM may lead; :func:`fungo.http.parse_csv`
        strips it).

    Raises:
        LahmanError: If the response is empty or is HTML instead of CSV (Box
            serves an HTML error/login page with HTTP 200 when a shared file
            is gone or the download route changes).
        RequestError: On transport failure.
    """
    raw = http.request_bytes(
        f"{BOX_BASE_URL}/index.php",
        params={
            "rm": "box_download_shared_file",
            "shared_name": shared_name,
            "file_id": file_id,
        },
        timeout=120,
    )

    if not raw.strip():
        raise LahmanError(
            f"Empty response downloading Lahman table {table!r} "
            f"(file id {file_id!r}). {_DOWNLOAD_HINT}"
        )

    head = raw.lstrip()[:512].lower()
    if head.startswith(b"<") or b"<html" in head:
        raise LahmanError(
            f"Download for Lahman table {table!r} (file id {file_id!r}) "
            f"returned HTML, not CSV — the shared link is gone or Box's "
            f"download route has changed. {_DOWNLOAD_HINT}"
        )

    return raw
