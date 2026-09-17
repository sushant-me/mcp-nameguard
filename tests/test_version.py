"""The release version is written in more than one place, so pin the copies.

`--version` reported one release, the installed distribution reported another,
and the client identity sent to every server on `initialize` disagreed with
both. A test is the only thing that keeps hand-copied strings in step.
"""

import pytest

from nameguard import __version__
from nameguard._version import __version__ as single_source
from nameguard.mcp_stdio import CLIENT_INFO


def _installed_version():
    """The distribution's version, or None when running from a bare checkout."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("mcp-nameguard")
    except PackageNotFoundError:
        return None


def test_the_package_version_comes_from_one_place():
    assert __version__ == single_source


def test_the_package_version_matches_the_installed_distribution():
    """`pip install .` takes the version from pyproject.toml, so this ties the
    copy in `_version.py` to the one the packaging metadata carries."""
    installed = _installed_version()
    if installed is None:
        pytest.skip("mcp-nameguard is not installed as a distribution")
    assert __version__ == installed, (
        f"nameguard/_version.py says {__version__}, the installed distribution "
        f"says {installed}"
    )


def test_the_client_identity_uses_the_package_version():
    """This string goes out on the wire, so a stale one misreports the client to
    every server it checks."""
    assert CLIENT_INFO["version"] == __version__
