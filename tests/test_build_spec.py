"""The crawler that builds api_spec.json.

``tools/build_spec.py`` is a script rather than an installed module, so it is
loaded from its path. The expectations for ``parse_params`` are hand-written from
the bracketed-argument convention the FMOD reference uses, not read back out of
the spec the crawler produced.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def load_build_spec():
    module_spec = importlib.util.spec_from_file_location("build_spec", ROOT / "tools" / "build_spec.py")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


build_spec = load_build_spec()


class FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_a_successful_fetch_returns_the_page(monkeypatch):
    monkeypatch.setattr(build_spec.subprocess, "run",
                        lambda *a, **k: FakeCompleted(0, "<html>ok</html>"))
    assert build_spec.fetch("globals") == "<html>ok</html>"


def test_a_failed_fetch_is_an_error_not_an_empty_page(monkeypatch):
    """Silently crawling nothing would drop members from the spec without a word."""
    monkeypatch.setattr(build_spec.subprocess, "run",
                        lambda *a, **k: FakeCompleted(22, "", "curl: (22) 404"))
    with pytest.raises(RuntimeError) as caught:
        build_spec.fetch("globals")
    assert "globals" in str(caught.value)


@pytest.mark.parametrize("signature, expected", [
    ("system.getText(msg[, defaultText])", [("msg", False), ("defaultText", True)]),
    ("f(a, b)", [("a", False), ("b", False)]),
    ("f()", []),
    ("f([a, b])", [("a", True), ("b", True)]),
    ("project.importAudioFile(filePath)", [("filePath", False)]),
])
def test_optional_arguments_follow_the_bracket_nesting(signature, expected):
    parsed = build_spec.parse_params(signature)
    assert [(p["name"], p["optional"]) for p in parsed] == expected
