"""``fungo`` command-line interface.

A single ``fungo`` entry point with six subcommands — ``lookup``, ``search``,
``leaderboard``, ``mlb``, ``fangraphs``, and ``bbref`` — that parse arguments
and delegate straight to the library, then render the result as CSV or JSON.
The CLI holds no business logic: each subcommand maps flags onto an existing
public function and prints what comes back.

Expected library errors (the ``FungoError`` family — ``ValidationError``,
``SavantError``, ``RequestError``, ``MLBStatsError``, ``FangraphsError``,
``BBRefError``) are caught at the ``main`` boundary and reported as a one-line
``error:`` message on stderr with exit code 1; argparse handles usage errors.
Unexpected exceptions (i.e. bugs) are left to propagate so they surface a full
traceback.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from typing import Any

from fungo import bbref, fangraphs, mlb
from fungo.exceptions import FungoError
from fungo.lookup import lookup
from fungo.statcast.leaderboards import get_leaderboard, list_leaderboards
from fungo.statcast.search import search_pitches

#####################################################################
# Passthrough argument parsing
#####################################################################


def _parse_extras(extras: list[str], *, pipe_join: bool) -> dict[str, Any]:
    """Turn leftover ``--key value`` / ``--key=value`` tokens into kwargs.

    Keys are normalized by stripping the leading ``--`` and converting ``-`` to
    ``_`` so they line up with Python parameter names (e.g. ``--game-pk`` ->
    ``game_pk``). When ``pipe_join`` is set (Statcast search only), a
    comma-separated value is joined with ``"|"`` to match Savant's multi-value
    convention; otherwise values pass through verbatim.

    Args:
        extras: Unrecognized tokens from ``parse_known_args``.
        pipe_join: Join comma-separated values with ``"|"`` (Savant convention).

    Returns:
        ``dict[str, Any]`` of forwarded keyword arguments.

    Raises:
        SystemExit: Via ``argparse``-style error if a token is malformed.
    """
    out: dict[str, Any] = {}
    i = 0
    while i < len(extras):
        token = extras[i]
        if not token.startswith("--"):
            raise SystemExit(f"fungo: unexpected argument: {token!r}")
        if "=" in token:
            raw_key, value = token[2:].split("=", 1)
            i += 1
        else:
            raw_key = token[2:]
            if i + 1 >= len(extras) or extras[i + 1].startswith("--"):
                raise SystemExit(f"fungo: missing value for {token!r}")
            value = extras[i + 1]
            i += 2
        key = raw_key.replace("-", "_")
        if pipe_join and "," in value:
            value = "|".join(value.split(","))
        out[key] = value
    return out


def _parse_seasons(value: str | None) -> int | list[int] | None:
    """Parse a ``--season`` value: a single year -> ``int``, a comma list ->
    ``list[int]`` (passed straight to ``get_leaderboard`` as ``year=``)."""
    if value is None:
        return None
    parts = [int(p) for p in value.split(",")]
    return parts[0] if len(parts) == 1 else parts


#####################################################################
# Output rendering
#####################################################################


def _render(result: Any, fmt: str) -> str:
    """Render a library result as a CSV or JSON string.

    CSV expects a ``list[dict]`` (tabular); fieldnames are the union of keys
    across all rows. An empty list renders to ``""`` (the caller notes it on
    stderr). JSON serializes any structure with ``default=str``.

    Args:
        result: The library return value.
        fmt: ``"csv"`` or ``"json"``.

    Returns:
        The rendered text.

    Raises:
        SystemExit: If ``fmt`` is ``"csv"`` but ``result`` is not a ``list[dict]``.
    """
    if fmt == "json":
        return json.dumps(result, indent=2, default=str)

    if not isinstance(result, list) or not all(isinstance(r, dict) for r in result):
        raise SystemExit("fungo: result is not tabular; rerun with --format json")

    if not result:
        return ""

    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in result:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(result)
    return buf.getvalue()


def _emit(result: Any, fmt: str, output: str | None) -> None:
    """Render ``result`` and write it to ``output`` (a file) or stdout."""
    text = _render(result, fmt)
    if isinstance(result, list) and not result:
        print("fungo: no rows returned", file=sys.stderr)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
        if text and not text.endswith("\n"):
            sys.stdout.write("\n")


#####################################################################
# Subcommand handlers
#####################################################################


def _run_lookup(args: argparse.Namespace, extras: list[str]) -> Any:
    if extras:
        raise SystemExit(f"fungo lookup: unexpected arguments: {extras}")
    return lookup(name=args.name, mlbam=args.mlbam, mlb_only=args.mlb_only)


def _run_search(args: argparse.Namespace, extras: list[str]) -> Any:
    filters = _parse_extras(extras, pipe_join=True)
    return search_pitches(
        args.start,
        args.end,
        player_type=args.player_type,
        player_id=args.player_id,
        level=args.level,
        **filters,
    )


def _run_leaderboard(args: argparse.Namespace, extras: list[str]) -> Any:
    if args.list:
        return [{"slug": s} for s in list_leaderboards(category=args.category)]
    if not args.slug:
        raise SystemExit("fungo leaderboard: a slug is required (or use --list)")
    params = _parse_extras(extras, pipe_join=False)
    if args.type is not None:
        params["type"] = args.type
    if args.player_id is not None:
        params["player_id"] = args.player_id
    return get_leaderboard(args.slug, year=_parse_seasons(args.season), **params)


def _run_module_function(
    module: Any, module_name: str, args: argparse.Namespace, extras: list[str]
) -> Any:
    """Shared handler for the function-passthrough subcommands (mlb,
    fangraphs, bbref): dispatch ``FUNCTION --key=value ...`` onto a public
    function listed in the module's ``__all__``."""
    if args.list:
        return [
            {"function": name}
            for name in sorted(module.__all__)
            if callable(getattr(module, name))
        ]
    if not args.function:
        raise SystemExit(
            f"fungo {module_name}: a function name is required (or use --list)"
        )
    if args.function not in module.__all__ or not callable(
        getattr(module, args.function)
    ):
        raise SystemExit(
            f"fungo {module_name}: unknown function {args.function!r}; "
            "use --list for options"
        )
    kwargs = _parse_extras(extras, pipe_join=False)
    return getattr(module, args.function)(**kwargs)


def _run_mlb(args: argparse.Namespace, extras: list[str]) -> Any:
    return _run_module_function(mlb, "mlb", args, extras)


def _run_fangraphs(args: argparse.Namespace, extras: list[str]) -> Any:
    return _run_module_function(fangraphs, "fangraphs", args, extras)


def _run_bbref(args: argparse.Namespace, extras: list[str]) -> Any:
    return _run_module_function(bbref, "bbref", args, extras)


#####################################################################
# Parser construction
#####################################################################


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level ``fungo`` parser with its four subcommands."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-o", "--output", help="Write output to FILE (default: stdout)."
    )
    common.add_argument(
        "--format",
        choices=["csv", "json"],
        default=None,
        help="Output format (default: csv; json for the mlb subcommand).",
    )

    parser = argparse.ArgumentParser(
        prog="fungo", description="Acquire baseball data from public web sources."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_lookup = sub.add_parser(
        "lookup", parents=[common], help="Chadwick player ID cross-reference."
    )
    p_lookup.add_argument("--name", help="Name substring (case-insensitive).")
    p_lookup.add_argument("--mlbam", help="MLBAM (Savant) player ID.")
    p_lookup.add_argument(
        "--mlb-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Restrict to MLB players (default on; --no-mlb-only for all).",
    )

    p_search = sub.add_parser(
        "search", parents=[common], help="Pitch-level Statcast search."
    )
    p_search.add_argument("--start", required=True, help="Start date YYYY-MM-DD.")
    p_search.add_argument("--end", required=True, help="End date YYYY-MM-DD.")
    p_search.add_argument("--player-type", default="pitcher", help="pitcher or batter.")
    p_search.add_argument("--player-id", help="MLBAM player ID.")
    p_search.add_argument("--level", default="mlb", help="mlb or milb.")

    p_lb = sub.add_parser(
        "leaderboard", parents=[common], help="Baseball Savant leaderboards."
    )
    p_lb.add_argument("slug", nargs="?", help="Leaderboard slug.")
    p_lb.add_argument(
        "--season",
        "--year",
        dest="season",
        help="Season(s); comma-separated for multi.",
    )
    p_lb.add_argument("--type", help="Leaderboard 'type' param (batter/pitcher/...).")
    p_lb.add_argument("--player-id", help="MLBAM player ID.")
    p_lb.add_argument(
        "--list", action="store_true", help="List available leaderboards."
    )
    p_lb.add_argument("--category", help="Filter --list by category.")

    p_mlb = sub.add_parser(
        "mlb", parents=[common], help="MLB Stats API (statsapi.mlb.com)."
    )
    p_mlb.add_argument("function", nargs="?", help="An mlb function name.")
    p_mlb.add_argument("--list", action="store_true", help="List available functions.")

    p_fg = sub.add_parser(
        "fangraphs",
        parents=[common],
        help="FanGraphs (leaderboards, player stats, RosterResource, Guts!).",
    )
    p_fg.add_argument("function", nargs="?", help="A fangraphs function name.")
    p_fg.add_argument("--list", action="store_true", help="List available functions.")

    p_br = sub.add_parser(
        "bbref",
        parents=[common],
        help="Baseball-Reference (rate-limited single-page fetchers).",
    )
    p_br.add_argument("function", nargs="?", help="A bbref function name.")
    p_br.add_argument("--list", action="store_true", help="List available functions.")

    return parser


_HANDLERS = {
    "lookup": _run_lookup,
    "search": _run_search,
    "leaderboard": _run_leaderboard,
    "mlb": _run_mlb,
    "fangraphs": _run_fangraphs,
    "bbref": _run_bbref,
}


#####################################################################
# Entry point
#####################################################################


def main(argv: list[str] | None = None) -> int:
    """Parse ``argv``, run the chosen subcommand, and emit its result.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``).

    Returns:
        ``0`` on success, ``1`` if a ``FungoError`` was raised (reported as a
        one-line ``error:`` message on stderr). Unexpected exceptions propagate.
    """
    parser = _build_parser()
    args, extras = parser.parse_known_args(argv)
    fmt = args.format or (
        "json" if args.command in ("mlb", "fangraphs", "bbref") else "csv"
    )

    try:
        result = _HANDLERS[args.command](args, extras)
    except FungoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _emit(result, fmt, args.output)
    return 0
