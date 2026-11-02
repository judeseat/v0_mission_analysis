"""Basic import and package-verification tests."""

import v0_tool


def test_package_import() -> None:
    """Verify that v0_tool is importable and exposes __version__."""
    assert hasattr(v0_tool, "__version__")
    assert v0_tool.__version__ == "0.1.0"
