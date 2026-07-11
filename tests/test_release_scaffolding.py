"""Release-level scaffolding checks.

These tests protect packaging and public-surface decisions that unit coverage
does not exercise directly.
"""

from __future__ import annotations

import inspect
import tomllib
from pathlib import Path

import fungo
import fungo.bbref as bbref
import fungo.fangraphs as fangraphs
import fungo.lahman as lahman
import fungo.mlb as mlb
import fungo.retrosheet as retrosheet
import fungo.statcast as statcast
from fungo.statcast import leaderboards as lb

ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_package_version_matches_pyproject():
    assert fungo.__version__ == _pyproject()["project"]["version"]


def test_all_extra_is_runtime_only():
    project = _pyproject()
    # bbref needs bs4 (comment-deferred tables) and curl_cffi (Cloudflare TLS
    # impersonation); nothing else may creep into runtime deps.
    assert set(project["project"]["dependencies"]) == {
        "beautifulsoup4",
        "curl_cffi",
    }
    extras = project["project"]["optional-dependencies"]
    # No DataFrame extras: fungo returns list[dict]/dict and users wrap it in
    # whatever frame library they already have.
    assert extras["all"] == ["rich"]
    assert "dev" not in extras
    assert not {"polars", "pandas"} & set(extras["all"])
    assert not {"pytest", "pytest-cov", "ruff", "mypy"} & set(extras["all"])
    assert {
        "pytest",
        "pytest-cov",
        "ruff",
        "mypy",
        "pre-commit",
    } <= set(project["dependency-groups"]["dev"])


def test_project_classifiers_match_v1_package_shape():
    classifiers = set(_pyproject()["project"]["classifiers"])
    assert {
        "Development Status :: 5 - Production/Stable",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Programming Language :: Python :: 3 :: Only",
        "Typing :: Typed",
        "Topic :: Software Development :: Libraries :: Python Modules",
    } <= classifiers


def test_top_level_exports_exist():
    for name in fungo.__all__:
        assert hasattr(fungo, name), name


def test_statcast_exports_exist():
    for name in statcast.__all__:
        assert hasattr(statcast, name), name


def test_mlb_exports_exist():
    for name in mlb.__all__:
        assert hasattr(mlb, name), name


def test_fangraphs_exports_exist():
    for name in fangraphs.__all__:
        assert hasattr(fangraphs, name), name


def test_bbref_exports_exist():
    for name in bbref.__all__:
        assert hasattr(bbref, name), name


def test_retrosheet_exports_exist():
    for name in retrosheet.__all__:
        assert hasattr(retrosheet, name), name


def test_lahman_exports_exist():
    for name in lahman.__all__:
        assert hasattr(lahman, name), name


def test_leaderboard_registry_has_wrappers_for_html_boards():
    html_wrappers = {
        "statcast-park-factors": lb.get_park_factors,
        "hot-stove": lb.get_hot_stove,
        "rolling": lb.get_rolling_windows,
    }
    html_slugs = {
        slug
        for slug, meta in lb.LEADERBOARDS.items()
        if meta.get("csv_available") is False
    }
    assert html_slugs == set(html_wrappers)
    assert all(callable(func) for func in html_wrappers.values())


def test_public_leaderboard_wrappers_are_exported_from_statcast():
    for name, func in inspect.getmembers(lb, inspect.isfunction):
        if name.startswith("get_") and name not in {"get_leaderboard"}:
            assert name in statcast.__all__, name
            assert getattr(statcast, name) is func


def test_changelog_documents_v1_release():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [1.0.0]" in text
    assert "GitHub Actions CI across Python 3.12-3.14" in text
    assert "get_top_performers" in text
