"""The generic tools, tested by running the JavaScript they generate.

``_generic_script`` builds the script; node runs it against a stand-in FMOD
object graph. That keeps the test on real generated code rather than on a string
that merely looks right.
"""

from __future__ import annotations

import json

from fmod_studio_mcp.server import _generic_script

from conftest import requires_node

pytestmark = requires_node

# A stand-in for the slice of the FMOD model these tools touch. It records the
# calls it receives, so a test can prove which method actually ran.
FAKE_STUDIO = """
var __calls = [];
function __obj(path) {
  return {
    path: path,
    getPath: function () { return path; },
    relationships: { banks: {
      add: function (o) { __calls.push("add " + o.path); },
      remove: function (o) { __calls.push("remove " + o.path); }
    } }
  };
}
var studio = { project: { lookup: function (path) {
  return path === "event:/missing" ? undefined : __obj(path);
} } };
"""


def run_script(run_node, script: str):
    source = FAKE_STUDIO + f"\nconsole.log(JSON.stringify(eval({json.dumps(script)})));"
    return json.loads(run_node(source))


def run_generic(run_node, name: str, **args):
    return run_script(run_node, _generic_script(name, args))


def test_adding_a_relationship_reports_added(run_node):
    assert run_generic(run_node, "fmod_add_relationship",
                       target="event:/A", relationship="banks", other="bank:/Master") == "added"


def test_removing_a_relationship_reports_removed(run_node):
    """The reply used to read 'removeed'."""
    assert run_generic(run_node, "fmod_remove_relationship",
                       target="event:/A", relationship="banks", other="bank:/Master") == "removed"


def test_removing_a_relationship_calls_remove(run_node):
    """The wording follows the call, so check the call itself too."""
    script = _generic_script("fmod_remove_relationship",
                             {"target": "event:/A", "relationship": "banks", "other": "bank:/Master"})
    source = FAKE_STUDIO + f"\neval({json.dumps(script)});\nconsole.log(JSON.stringify(__calls));"
    assert json.loads(run_node(source)) == ["remove bank:/Master"]


def test_adding_a_relationship_calls_add(run_node):
    script = _generic_script("fmod_add_relationship",
                             {"target": "event:/A", "relationship": "banks", "other": "bank:/Master"})
    source = FAKE_STUDIO + f"\neval({json.dumps(script)});\nconsole.log(JSON.stringify(__calls));"
    assert json.loads(run_node(source)) == ["add bank:/Master"]


def test_a_missing_object_is_reported_not_guessed(run_node):
    assert run_generic(run_node, "fmod_add_relationship",
                       target="event:/missing", relationship="banks", other="bank:/Master") == "not found"


def test_an_unknown_tool_builds_no_script():
    assert _generic_script("fmod_nonexistent", {}) is None
