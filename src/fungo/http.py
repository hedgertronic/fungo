"""Shared HTTP transport and parsing for fungo — stdlib only.

No ``requests``, ``rich``, or third-party deps. Provides:

- :func:`request_bytes`: GET with exponential-backoff retry, raising
  :class:`~fungo.exceptions.RequestError` on permanent failure.
- :func:`request_json`: GET + JSON decode.
- :func:`parse_csv`: BOM-aware CSV -> ``list[dict]`` (no HTML detection; that is
  source-specific and lives in the Statcast layer).
- :func:`map_concurrent`: bounded thread pool preserving input order, with an
  optional inter-submit delay and opt-in silent ``rich`` progress.
"""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from typing import Any, cast

from fungo.exceptions import RequestError

USER_AGENT = "Mozilla/5.0 (compatible; fungo/1.0.1)"


#####################################################################
# HTTP transport
#####################################################################


def request_bytes(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    retries: int = 3,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
) -> bytes:
    """Fetch ``url`` and return the raw response body with retry/backoff.

    GET by default; passing ``data`` sends it as a POST body (the caller sets
    ``Content-Type`` via ``headers``). Query params are URL-encoded with
    ``safe="|"`` so pipe-delimited Savant parameters survive. ``None``-valued
    params are dropped, and boolean values serialize as lowercase
    ``true``/``false`` (the canonical query-param form; ``str(True)`` would
    send ``True``). 4xx responses raise immediately; 5xx / network / timeout
    errors retry with exponential backoff (``2 ** attempt`` seconds).

    Args:
        url: Target URL (with or without an existing query string).
        params: Optional query parameters to append.
        retries: Number of attempts before giving up.
        timeout: Per-request timeout in seconds.
        headers: Optional extra request headers (merged over the default UA).
        data: Optional request body; its presence switches the method to POST.

    Returns:
        The raw response body as ``bytes``.

    Raises:
        RequestError: On a 4xx status or after exhausting retries.
    """
    if params:
        encoded = urllib.parse.urlencode(
            {
                k: "true" if v is True else "false" if v is False else v
                for k, v in params.items()
                if v is not None
            },
            safe="|",
            doseq=True,
        )
        sep = "&" if "?" in url else "?"
        full_url = f"{url}{sep}{encoded}"
    else:
        full_url = url

    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(full_url, headers=req_headers, data=data)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return cast(bytes, resp.read())
        except urllib.error.HTTPError as e:
            if e.code < 500:
                raise RequestError(f"HTTP {e.code} for {full_url}: {e.reason}") from e
            last_err = e
            time.sleep(2**attempt)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            time.sleep(2**attempt)

    raise RequestError(f"Failed after {retries} retries for {full_url}: {last_err}")


def request_json(
    url: str,
    params: dict[str, Any] | None = None,
    **kw: Any,
) -> dict[str, Any] | list[Any]:
    """GET ``url`` and decode the body as JSON.

    Args:
        url: Target URL.
        params: Optional query parameters.
        **kw: Forwarded to :func:`request_bytes` (``retries``, ``timeout``,
            ``headers``).

    Returns:
        The parsed JSON value (``dict`` or ``list``).

    Raises:
        RequestError: On transport failure.
        json.JSONDecodeError: If the body is not valid JSON.
    """
    raw = request_bytes(url, params=params, **kw)
    try:
        return cast("dict[str, Any] | list[Any]", json.loads(raw.decode("utf-8")))
    except json.JSONDecodeError as exc:
        raise RequestError(f"Invalid JSON response: {exc}") from exc


#####################################################################
# CSV parsing
#####################################################################


def parse_csv(raw: bytes | str) -> list[dict[str, Any]]:
    """Parse CSV text into a list of row dicts.

    Decodes bytes as ``utf-8-sig`` so a leading BOM is stripped, strips any BOM
    left on the first column name, and preserves empty strings (``""`` stays
    ``""``). Returns ``[]`` for empty/whitespace-only input.

    Args:
        raw: CSV content as ``bytes`` (decoded as ``utf-8-sig``) or ``str``.

    Returns:
        One ``dict`` per data row; ``[]`` if there are no rows.
    """
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw

    if not text.strip():
        return []

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    if rows:
        first_key = next(iter(rows[0]))
        if first_key.startswith("﻿"):
            clean_key = first_key.lstrip("﻿")
            rows = [
                {(clean_key if k == first_key else k): v for k, v in row.items()}
                for row in rows
            ]

    return rows


#####################################################################
# Bounded concurrency
#####################################################################


def map_concurrent[T, R](
    func: Callable[[T], R],
    items: Sequence[T],
    *,
    max_workers: int = 4,
    delay: float = 0.0,
    progress: bool = False,
    label: str | None = None,
) -> list[R]:
    """Apply ``func`` to each item across a bounded thread pool, in order.

    Results are returned in the same order as ``items`` regardless of completion
    order. An optional ``delay`` is slept between submissions (gentle rate
    limiting). When ``progress`` is True and ``rich`` is importable, a progress
    bar is shown; otherwise progress is a silent no-op. The library never writes
    to stdout unless ``progress=True``.

    Args:
        func: Callable applied to each item.
        items: Input sequence.
        max_workers: Maximum concurrent worker threads.
        delay: Seconds to sleep between submitting tasks.
        progress: If True, show a ``rich`` progress bar when available.
        label: Optional description shown on the progress bar.

    Returns:
        ``list`` of results in input order.
    """
    from concurrent.futures import ThreadPoolExecutor

    items = list(items)
    if not items:
        return []

    bar = None
    task_id = None
    if progress:
        try:
            from rich.progress import Progress

            bar = Progress()
            bar.start()
            task_id = bar.add_task(label or "Working", total=len(items))
        except ImportError:
            bar = None

    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        futures = []
        for i, item in enumerate(items):
            futures.append(executor.submit(func, item))
            if delay and i < len(items) - 1:
                time.sleep(delay)

        results: list[R] = []
        for future in futures:
            results.append(future.result())
            if bar is not None and task_id is not None:
                bar.advance(task_id)
    except BaseException:
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)
    finally:
        if bar is not None:
            bar.stop()

    return results
