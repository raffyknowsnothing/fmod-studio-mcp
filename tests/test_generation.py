"""Script generation for the spec-driven tools.

Every documented member must produce a runnable script, and how a member is
reached has to follow its ``target_kind``. This walks the whole committed spec,
so it covers all 148 generated tools rather than a sample.
"""

from __future__ import annotations

from fmod_studio_mcp.generation import build_generated_tools, embed_value
from fmod_studio_mcp.server import _GENERATED


def args_for(tool) -> dict:
    """Minimal arguments that satisfy a tool's required inputs."""
    args = {}
    for name in tool.input_schema().get("required", []):
        args[name] = {"target": "event:/SFX/Hit", "className": "Event"}.get(name, "0")
    return args


def test_every_member_in_the_spec_generates_a_script():
    tools = build_generated_tools()
    assert len(tools) == 148
    for tool in tools:
        script = tool.build_js(args_for(tool))
        assert script.strip(), tool.name
        assert "__desc(" in script, tool.name


def test_every_tool_name_is_unique_and_namespaced():
    names = [tool.name for tool in build_generated_tools()]
    assert len(names) == len(set(names))
    assert all(name.startswith("fmod_") for name in names)


def test_a_module_member_is_reached_on_its_fixed_receiver():
    script = _GENERATED["fmod_project_filePath"].build_js({})
    assert "studio.project.filePath" in script


def test_an_instance_member_is_reached_by_lookup():
    script = _GENERATED["fmod_Bank_getPath"].build_js({"target": "bank:/Master"})
    assert 'studio.project.lookup("bank:/Master")' in script


def test_an_entity_member_is_reached_through_the_model():
    script = _GENERATED["fmod_entity_findInstances"].build_js({"className": "Event"})
    assert 'studio.project.model["Event"]' in script


def test_a_property_reads_when_no_value_is_given():
    script = _GENERATED["fmod_project_filePath"].build_js({})
    assert script.endswith("__desc(studio.project.filePath);")


def test_a_settable_property_writes_when_a_value_is_given():
    script = _GENERATED["fmod_project_distanceRolloffType"].build_js({"value": 1})
    assert "studio.project.distanceRolloffType = 1" in script


def test_embedding_turns_paths_and_guids_into_object_references():
    assert embed_value("event:/SFX/Hit") == 'studio.project.lookup("event:/SFX/Hit")'
    assert embed_value("bank:/Master") == 'studio.project.lookup("bank:/Master")'
    assert embed_value("{1234-5678}") == 'studio.project.lookup("{1234-5678}")'


def test_embedding_keeps_numbers_booleans_and_strings_typed():
    assert embed_value(2.5) == "2.5"
    assert embed_value(True) == "true"
    assert embed_value("hello") == '"hello"'
