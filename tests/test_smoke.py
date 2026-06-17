"""Smoke tests: the package imports and exposes a version. Real tests land during the build."""

import dugalaxy


def test_version_is_present() -> None:
    assert isinstance(dugalaxy.__version__, str)
    assert dugalaxy.__version__
