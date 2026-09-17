"""The package version, in one place.

It used to be written out three times - here as `__version__`, in the client
identity sent to every server on `initialize`, and in `pyproject.toml` - and the
three had drifted apart, so `--version` and the name the server saw both
misreported the release. `tests/test_version.py` keeps this file and
`pyproject.toml` in step.
"""

__version__ = "0.4.7"
