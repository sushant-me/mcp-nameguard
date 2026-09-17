"""The release version is written in two places, so pin them together.

`--version` reported one release while the installed distribution reported
another, and the client identity sent to every server on `initialize` disagreed
with both. A test is the only thing that keeps hand-copied strings in step.
"""

import tomllib
from pathlib import Path

import pytest

from nameguard import __version__
from nameguard._version import __version__ as single_source

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_the_package_version_comes_from_one_place():
    assert __version__ == single_source


def test_the_package_version_matches_pyproject():
    if not PYPROJECT.exists():
        pytest.skip("no pyproject.toml beside the installed package")
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    assert __version__ == declared, (
        f"nameguard/_version.py says {__version__}, pyproject.toml says {declared}"
    )


def test_the_client_identity_uses_the_package_version():
    """This string goes out on the wire, so a stale one misreports the client to
    every server it checks."""
    from nameguard.mcp_stdio import CLIENT_INFO

    assert CLIENT_INFO["version"] == __version__
