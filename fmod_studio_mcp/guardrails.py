"""Safety guardrails on the calls that can move or destroy data.

A wrong handle on a mutating call is silent. That is not hypothetical. An agent
passed a `{guid}` it had never read to `Asset.setAssetPath`; the wrong file moved
on disk, the result looked like a stray duplicate, the duplicate was deleted, and
an event lost its sound. Nothing in the reply said which object had moved.

The guardrail is a read-back, not a permission check. Before the call the target
is identified from the object itself, and for a write the old value is captured
too. The reply then names what was touched and what changed, so a wrong target is
visible in the answer rather than discovered later.

Only the read-back is built here. An earlier design also refused the call when
the target resolved but carried no address, on the grounds that it could not then
be named back. Measuring the live model killed that idea: of 4492 objects across
15 classes, **zero** lack an `id`, so the condition is unreachable and the branch
would have been dead code. The reachable protection is that a target which does
not resolve answers `not found` and the call never happens, and that is tested.

Scope, measured against the spec: of 148 generated members, exactly three can
move real data or destroy it. Everything else that writes is `project.save`,
`project.build` or `project.exportGUIDs`, none of which lose anything.

The fourth guarded entry, `fmod_set_property`, is a generic tool rather than a
generated one. It is the wide door: it writes any property on any object, so it
can change a path without going through `setAssetPath` at all.
"""

from __future__ import annotations

import json

from .generation import _DESC, embed_value


def _q(value: object) -> str:
    return json.dumps(str(value))


def generated_script(tool, args: dict) -> str | None:
    """Return a guarded script for a generated tool, or None to leave it alone.

    None means the member cannot damage anything, so the tool keeps its ordinary
    script and its ordinary reply.
    """
    name = tool.name

    if name == "fmod_Asset_setAssetPath":
        # The call that destroyed an asset. Name the object first, then show the
        # path it had and the path it now has. If the target does not resolve,
        # answer `not found` and never call the member.
        target = _q(args.get("target"))
        new_path = embed_value(args.get("filePath"))
        return "".join([
            _DESC,
            f"var __t=studio.project.lookup({target});",
            "if(!__t){'not found'}else{",
            "var __i=__desc(__t);",
            "var __b=__desc(__t.assetPath);",
            f"__t.setAssetPath({new_path});",
            "var __a=__desc(__t.assetPath);",
            "'moved '+__i+'; assetPath: '+__b+' -> '+__a;}",
        ])

    if name == "fmod_project_deleteObject":
        # Identity has to be read before the call. After it there is nothing left.
        target = _q(args.get("managedObject"))
        return "".join([
            _DESC,
            f"var __t=studio.project.lookup({target});",
            "if(!__t){'not found'}else{",
            "var __i=__desc(__t);",
            "studio.project.deleteObject(__t);",
            "'deleted '+__i;}",
        ])

    if name == "fmod_project_importAudioFile":
        # Nothing is destroyed. The read-back names the asset just created, so a
        # caller can see what it got rather than assuming.
        path = args.get("filePath")
        return "".join([
            _DESC,
            f"var __a=studio.project.importAudioFile({embed_value(path)});",
            f"'imported '+(__a?__desc(__a):{_q(path)});",
        ])

    return None


def generic_script(name: str, a: dict) -> str | None:
    """Return a guarded script for a generic tool, or None to leave it alone."""
    if name != "fmod_set_property":
        return None

    target = _q(a.get("target"))
    prop = _q(a.get("property"))
    value = embed_value(a["value"])
    return "".join([
        _DESC,
        f"var __o=studio.project.lookup({target});",
        "if(!__o){'not found'}else{",
        "var __i=__desc(__o);",
        f"var __p={prop};",
        "var __b=__desc(__o[__p]);",
        f"__o[__p]={value};",
        "var __a=__desc(__o[__p]);",
        "'set '+__i+'; '+__p+': '+__b+' -> '+__a;",
        "}",
    ])
