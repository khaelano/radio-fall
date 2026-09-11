"""Regression checks for the ODT filter download, without external networking."""

import importlib.util
import io
import urllib.error
from pathlib import Path
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "build_draft_odt", Path(__file__).resolve().parents[1] / "tools/build_draft_odt.py"
)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def test_download_filter_server_rejects_default_python_user_agent():
    """Reproduce the server rejecting an unidentified urllib request."""
    body = b"-- test Lua filter"

    def server(request, timeout):
        if isinstance(request, str) or not request.get_header("User-agent"):
            raise urllib.error.HTTPError(builder.FILTER_URL, 403, "Forbidden", {}, None)
        return io.BytesIO(body)

    with patch.object(builder.urllib.request, "urlopen", side_effect=server):
        assert builder.download_filter() == body


def test_ensure_bibliography_preserves_existing_placeholder():
    document = {"blocks": [{"t": "Div", "c": [["refs", [], []], []]}]}
    builder.ensure_bibliography(document)
    assert len(document["blocks"]) == 1


def test_ensure_bibliography_adds_filter_placeholder():
    document = {"blocks": []}
    builder.ensure_bibliography(document)
    assert document["blocks"] == [{"t": "Div", "c": [["refs", [], []], []]}]
