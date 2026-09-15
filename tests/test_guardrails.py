"""Safety guardrails on the calls that can move or destroy data.

Four members can change something a caller cannot get back:

    Asset.setAssetPath          moves the real file on disk
    project.deleteObject        deletes an object
    project.importAudioFile     brings a file into the project
    fmod_set_property           writes any property on any object

A wrong handle on one of these is silent. That is not hypothetical: an agent
passed a `{guid}` it had never read to `setAssetPath`, the wrong file moved, the
result looked like a stray duplicate, and an event lost its sound.

The guardrail is a read-back. Before the call the target is identified from the
object itself, and for a replacement the old value is captured too. The reply
then names what was touched and what changed, so a wrong target is visible in
the answer rather than discovered later. Two of them also refuse outright when
the target has no address at all.

These tests run the real generated JavaScript under node against a stand-in
studio, the same way tests/test_renderer.py and tests/test_generic_tools.py do.
"""

from __future__ import annotations

import json

import pytest

from conftest import requires_node
from fmod_studio_mcp import guardrails
from fmod_studio_mcp.generation import build_generated_tools

pytestmark = requires_node

TOOLS = {t.name: t for t in build_generated_tools()}

ASSET_GUID = "{aec43b2f-448f-4840-8620-e603ddf8c110}"
EVENT_GUID = "{2d2fff6a-0eff-46e6-97b6-83630487be49}"

# A stand-in for the slice of the FMOD model these tools touch. It records the
# mutating calls it receives, so a test can prove whether the call happened.
FAKE_STUDIO = """
var __calls = [];
function __mk(path, entity, id) {
  return {
    entity: entity,
    id: id,
    _path: path,
    getPath: function () { return this._path; },
    get assetPath() { return this._path; },
    set assetPath(v) { this._path = v; },
    setAssetPath: function (p) { __calls.push('setAssetPath ' + p); this._path = p; return true; },
    deleteObject: function (o) { __calls.push('deleteObject ' + o.id); return true; }
  };
}
var ASSET = __mk('sfx/SFX_Respawn.ogg', 'Asset', '{aec43b2f-448f-4840-8620-e603ddf8c110}');
// An object with no address at all: no path that resolves, and no id.
var ORPHAN = { entity: 'Asset', setAssetPath: function (p) { __calls.push('setAssetPath ' + p); return true; } };
var EVENT = __mk('event:/SFX/footstep', 'Event', '{2d2fff6a-0eff-46e6-97b6-83630487be49}');
EVENT.color = 'Yellow';
var OBJS = [ASSET, EVENT, ORPHAN];
var studio = {
  project: {
    lookup: function (p) {
      for (var i = 0; i < OBJS.length; i++) {
        if (OBJS[i]._path === p || OBJS[i].id === p) return OBJS[i];
      }
      return undefined;
    },
    importAudioFile: function (p) {
      __calls.push('importAudioFile ' + p);
      var a = __mk(p, 'Asset', '{imported-guid}');
      OBJS.push(a);
      return a;
    },
    deleteObject: function (o) { __calls.push('deleteObject ' + o.id); return true; }
  }
};
"""


def run(script: str, run_node) -> str:
    """Run a guarded script under node and return its reply."""
    source = FAKE_STUDIO + f"\nconsole.log(JSON.stringify(eval({json.dumps(script)})));"
    return json.loads(run_node(source))


def calls(script: str, run_node) -> list[str]:
    """Run a guarded script and report which mutating calls it made."""
    source = FAKE_STUDIO + f"\neval({json.dumps(script)});\nconsole.log(JSON.stringify(__calls));"
    return json.loads(run_node(source))


def guarded(name: str, args: dict) -> str:
    script = guardrails.generated_script(TOOLS[name], args)
    assert script, f"{name} is not guarded"
    return script


# -- the guardrail exists at all --------------------------------------------


def test_the_four_dangerous_members_are_guarded():
    """A rename must not silently drop a guardrail."""
    for name in (
        "fmod_Asset_setAssetPath",
        "fmod_project_deleteObject",
        "fmod_project_importAudioFile",
    ):
        assert name in TOOLS, f"{name} no longer exists in the spec"
        assert guardrails.generated_script(TOOLS[name], {k: "x" for k in ("target", "filePath", "managedObject", "name", "soundType", "start", "length")}), (
            f"{name} lost its guardrail"
        )


def test_a_harmless_tool_is_left_alone():
    """The guardrail must not change tools that cannot damage anything."""
    assert guardrails.generated_script(TOOLS["fmod_Event_getPath"], {"target": "event:/A"}) is None


# -- setAssetPath: the call that actually destroyed an asset ----------------


def test_set_asset_path_names_the_object_it_moved(run_node):
    """The reply must identify the target, so a wrong handle is visible.

    Identity is read from the object itself. `__desc` prefers a path that
    resolves and falls back to the id, so a pathable object is named by path.
    """
    reply = run(guarded("fmod_Asset_setAssetPath",
                        {"target": ASSET_GUID, "filePath": "sfx/Ambient_Sci-Fi.ogg"}), run_node)
    assert "sfx/SFX_Respawn.ogg" in reply, f"reply does not name the object it moved: {reply!r}"


def test_set_asset_path_shows_the_old_path_and_the_new_one(run_node):
    reply = run(guarded("fmod_Asset_setAssetPath",
                        {"target": ASSET_GUID, "filePath": "sfx/Ambient_Sci-Fi.ogg"}), run_node)
    assert "sfx/SFX_Respawn.ogg" in reply, f"the path before the move is missing: {reply!r}"
    assert "sfx/Ambient_Sci-Fi.ogg" in reply, f"the path after the move is missing: {reply!r}"


def test_set_asset_path_makes_no_call_when_the_target_does_not_resolve(run_node):
    """An unresolvable target must not move anything.

    The read-back cannot name an object that does not exist, so `not found` is
    the honest answer and the member is never reached.
    """
    script = guarded("fmod_Asset_setAssetPath", {"target": "{no-such-object}", "filePath": "sfx/x.wav"})
    assert "not found" in run(script, run_node).lower()
    assert calls(script, run_node) == [], "the move went ahead on a target that does not exist"


# -- deleteObject: irreversible, so identify before you delete --------------


def test_delete_object_names_what_it_deleted(run_node):
    """Identity has to be read BEFORE the call; afterwards there is nothing left."""
    reply = run(guarded("fmod_project_deleteObject", {"managedObject": EVENT_GUID}), run_node)
    assert "event:/SFX/footstep" in reply, f"reply does not name what it deleted: {reply!r}"


def test_delete_object_makes_no_call_when_the_target_does_not_resolve(run_node):
    script = guarded("fmod_project_deleteObject", {"managedObject": "{no-such-object}"})
    assert "not found" in run(script, run_node).lower()
    assert calls(script, run_node) == [], "the delete went ahead on a target that does not exist"


# -- importAudioFile --------------------------------------------------------


def test_import_audio_file_names_the_asset_it_created(run_node):
    reply = run(guarded("fmod_project_importAudioFile", {"filePath": "sfx/New.wav"}), run_node)
    assert "sfx/New.wav" in reply, f"reply does not name the imported file: {reply!r}"


# -- set_property: the wide door --------------------------------------------


def test_set_property_shows_the_value_before_and_after(run_node):
    script = guardrails.generic_script("fmod_set_property",
                                       {"target": "event:/SFX/footstep", "property": "color", "value": "Green"})
    assert script, "fmod_set_property is not guarded"
    reply = run(script, run_node)
    assert "Yellow" in reply, f"the value before the write is missing: {reply!r}"
    assert "Green" in reply, f"the value after the write is missing: {reply!r}"


def test_set_property_on_a_missing_target_reads_as_not_found(run_node):
    script = guardrails.generic_script("fmod_set_property",
                                       {"target": "{no-such-object}", "property": "color", "value": "Green"})
    assert "not found" in run(script, run_node).lower()


# -- the wiring: the guardrail must actually be reached ---------------------
#
# Testing the guardrail module alone proves the module. These prove the server
# routes a dangerous call through it, which is the thing that protects anyone.


class FakeTerminal:
    """Stands in for the socket-backed terminal, recording the script it ran."""

    def __init__(self):
        self.scripts: list[str] = []

    def run(self, script: str, **kwargs) -> str:
        self.scripts.append(script)
        return "ok"


def test_the_server_routes_set_asset_path_through_its_guardrail(monkeypatch):
    from fmod_studio_mcp import server

    fake = FakeTerminal()
    monkeypatch.setattr(server, "TERMINAL", fake)
    server._run_generated(TOOLS["fmod_Asset_setAssetPath"],
                          {"target": ASSET_GUID, "filePath": "sfx/x.wav"})
    assert fake.scripts, "no script ran"
    assert "assetPath: " in fake.scripts[0], "the plain script ran, not the guarded one"


def test_the_server_routes_delete_object_through_its_guardrail(monkeypatch):
    from fmod_studio_mcp import server

    fake = FakeTerminal()
    monkeypatch.setattr(server, "TERMINAL", fake)
    server._run_generated(TOOLS["fmod_project_deleteObject"], {"managedObject": EVENT_GUID})
    assert "'deleted '" in fake.scripts[0], "the plain script ran, not the guarded one"


def test_the_server_routes_set_property_through_its_guardrail(monkeypatch):
    from fmod_studio_mcp import server

    fake = FakeTerminal()
    monkeypatch.setattr(server, "TERMINAL", fake)
    server._generic_dispatch("fmod_set_property",
                             {"target": "event:/A", "property": "color", "value": "Green"})
    assert " -> " in fake.scripts[0], "the plain script ran, not the guarded one"


def test_the_server_leaves_a_harmless_tool_on_its_plain_script(monkeypatch):
    from fmod_studio_mcp import server

    fake = FakeTerminal()
    monkeypatch.setattr(server, "TERMINAL", fake)
    server._run_generated(TOOLS["fmod_Event_getPath"], {"target": "event:/A"})
    assert "assetPath: " not in fake.scripts[0]
    assert "'deleted '" not in fake.scripts[0]
