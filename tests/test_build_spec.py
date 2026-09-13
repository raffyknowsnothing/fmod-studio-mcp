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
