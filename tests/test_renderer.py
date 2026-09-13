"""Value rendering for generated tools.

Every generated tool prepends the ``__desc`` helper to its script inside FMOD.
That helper is JavaScript, so these tests run the real thing under node against
stand-in values shaped like the ones the API actually returns.

The shapes and the expected text come from probing a live FMOD Studio 2.03.13
terminal, not from reading the code:

    studio.version                      object, no getPath, no id,
                                        String() -> "Version 2.03.13, 64-bit, ..."
    Event.properties                    object, String() -> "[object Object]",
                                        JSON -> 450 chars
    Event.relationships                 object, JSON -> 1911 chars
    Event.properties['note']            object, JSON -> 39 chars
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from fmod_studio_mcp.generation import _DESC

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is needed to execute the generated JavaScript")

VERSION_OBJECT = '{ toString: function () { return "Version 2.03.13, 64-bit, Qt 6.5.3 under LGPL, Build #162576"; } }'
MANAGED_OBJECT = '{ getPath: function () { return "event:/SFX/Hit"; } }'
# What studio.project.lookup("event:/") actually returns: a folder, which has an
# id and an entity but NO getPath. getPath() is defined on Event, Bank,
# MixerStrip and ParameterPreset only, so the helper must not assume it.
FOLDER_OBJECT = '{ id: "{a1935f59-5c41-439f-a224-d6517b1fa236}", entity: "MasterEventFolder" }'
# An object that answers getPath with something that is not a function.
NOT_A_FUNCTION = '{ getPath: 42, id: "{b}" }'

CASES = {
    # a managed object still reports its path, which is what makes results chain
    "managed": (MANAGED_OBJECT, "event:/SFX/Hit"),
    "managed_array": (f"[{MANAGED_OBJECT}, 2]", '["event:/SFX/Hit","2"]'),
    "id_only": ('{ id: "{1234-5678}" }', "{1234-5678}"),
    # the regression: a folder has no getPath, and asking for one used to throw
    # "TypeError: not a function" on a live 2.03.13 terminal.
    "folder_without_getpath": (FOLDER_OBJECT, "{a1935f59-5c41-439f-a224-d6517b1fa236}"),
    "folder_in_array": (f"[{FOLDER_OBJECT}]", '["{a1935f59-5c41-439f-a224-d6517b1fa236}"]'),
    # a getPath that is not callable must fall through, not throw
    "non_callable_getpath": (NOT_A_FUNCTION, "{b}"),
    # an object with its own toString, like studio.version, keeps that text
    "custom_tostring": (VERSION_OBJECT, "Version 2.03.13, 64-bit, Qt 6.5.3 under LGPL, Build #162576"),
    # a plain object has no useful String(), so its contents are the answer
    "plain_object": ('{ note: "hello", color: "0,0,0" }', '{"note":"hello","color":"0,0,0"}'),
    "nested_object": ('{ a: { b: 2 } }', '{"a":{"b":2}}'),
    "empty_object": ("{}", "{}"),
    # Array members go through the same rule as a single value, so they come out
    # as strings. That is the existing contract, kept here deliberately.
    "primitive_array": ("[1, 2.5, true, false, null, \"hi\"]", '["1","2.5","true","false","null","hi"]'),
}

# A getPath that is *present but throws* is not a shape FMOD produces: of the 63
# model classes, 53 have no getPath and 0 of the 63 throw when it is called. The
# helper therefore does not paper over one. Swallowing the throw would hand back
# the object's id as if it were the path, which is a wrong answer; letting it
# out means the call fails where the caller can see it.
THROWING_GETPATH = '{ getPath: function () { throw new Error("boom"); }, id: "{c}" }'


def render_raw(cases_js: str):
    """Run the helper and hand back the raw result, so a failure can be seen."""
    script = _DESC + "\n" + f"""
var __cases = {cases_js};
var __out = {{}};
Object.keys(__cases).forEach(function (k) {{ __out[k] = __desc(__cases[k]); }});
console.log(JSON.stringify(__out));
"""
    return subprocess.run([NODE, "-e", script], capture_output=True, text=True)


def render(cases_js: str) -> dict:
    proc = render_raw(cases_js)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.parametrize("name", sorted(CASES))
def test_values_render_as_observed(name):
    js, expected = CASES[name]
    assert render(f"{{ v: {js} }}")["v"] == expected


def test_undefined_and_null_are_named_not_blank():
    assert render("{ a: undefined, b: null }") == {"a": "undefined", "b": "null"}


def test_a_huge_object_is_truncated_and_says_so():
    """An unbounded dump would pour into the model's context; it must be bounded."""
    out = render('{ v: (function () { var o = {}; for (var i = 0; i < 5000; i++) o["k" + i] = i; return o; })() }')["v"]
    assert out.startswith('{"k0":0')
    assert "chars total" in out
    assert len(out) < 6000


def test_a_getpath_that_throws_is_reported_not_hidden():
    """Silently falling back to the id would report a path that does not exist,
    which is worse than failing. The typeof guard covers every real shape; a
    getPath that exists and throws is a genuine fault and must surface."""
    proc = render_raw(f"{{ v: {THROWING_GETPATH} }}")
    assert proc.returncode != 0, f"the throw was swallowed: {proc.stdout!r}"
    assert "boom" in proc.stderr


def render_result(value_js: str) -> str:
    """Render one value the way a tool returns it.

    ``__render`` is the single entry point every generated and generic tool
    uses, so this exercises the same path the server does rather than a
    copy of it.
    """
    script = _DESC + "\n" + f"console.log(__render({value_js}));"
    proc = subprocess.run([NODE, "-e", script], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.rstrip("\n")


def test_a_large_list_is_bounded_not_only_a_large_object():
    """The bound has to cover the whole result. It used to sit inside the object
    branch, and the array branch maps over its members with no total limit, so a
    list of 50 large objects rendered to 243,351 characters."""
    big = "[" + ",".join('{ a: "%s" }' % ("x" * 500) for _ in range(50)) + "]"
    out = render_result(big)
    assert "chars total" in out, "the list was not bounded"
    assert len(out) < 4200, f"rendered {len(out)} characters"


def test_a_small_result_is_not_truncated():
    """A bound that mangles ordinary answers is worse than none: results are
    chained back in as a `target`, so they have to stay usable."""
    assert render_result('"event:/SFX/Hit"') == "event:/SFX/Hit"
    assert render_result("42") == "42"