# fmod-studio-mcp

[![PyPI](https://img.shields.io/pypi/v/fmod-studio-mcp?color=3775A9&logo=pypi&logoColor=white)](https://pypi.org/project/fmod-studio-mcp/)
[![Buy me a coffee](https://img.shields.io/badge/%E2%98%95%20Buy%20me%20a%20coffee-support-FF813F)](https://buy.polar.sh/polar_cl_v4ZIuYffdbN9E9iVLmlHh1W5sxAmxvqNVqIn81048FX)

An [MCP](https://modelcontextprotocol.io) server that drives **FMOD Studio live**
through its built-in **scripting terminal** (TCP, default `127.0.0.1:3663`). Unlike
file-based approaches that edit a project's XML on disk (and require closing/reopening
Studio), this talks to the *running* editor: changes appear immediately, and Studio
itself writes them — so there's no clobbering and no reload dance.

It exposes the [FMOD Studio Scripting API](https://www.fmod.com/docs/2.02/studio/scripting-api-reference.html)
as **one MCP tool per API member** — generated from the crawled reference, not
hand-written — plus a few generic tools for the parts the static docs can't enumerate.
There is **no arbitrary-script / eval tool**: every capability is a named,
schema-validated operation over FMOD's object model.

> ⚠️ **Alpha.** Built for an AI agent (Claude Code) to author game audio. It edits the
> *live* project — call `fmod_project_save` to persist, and keep it version-controlled.

## How it works

FMOD Studio's **Script Server** exposes the scripting terminal over a TCP port: it
evaluates anything it receives as UTF-8 JavaScript and returns the result as text.
**It's disabled by default** — enable it once in Studio's preferences (see
[FMOD Studio setup](#fmod-studio-setup--enable-the-script-server)). Opening the console
with **Ctrl + 0** shows script output but does **not** start the server. This MCP keeps
one connection and uses *read-until-idle* framing, so it doesn't depend on a particular
prompt string.

Each tool generates the small piece of scripting-API JavaScript for its member, runs it,
and returns the result as a string. Anything that returns an object reports that object's
path or `{guid}`, so results chain straight back in as another tool's `target`.

## The tool set

**Generated — one per documented member (~148).** Named `fmod_<Owner>_<member>`, e.g.
`fmod_project_create`, `fmod_project_importAudioFile`, `fmod_Event_addGroupTrack`,
`fmod_GroupTrack_addSound`, `fmod_Bank_getPath`, `fmod_system_getText`. A member's
`target_kind` decides how it's reached:

| kind | reached as | tool inputs |
|---|---|---|
| `module` | `studio.project.*`, `studio.system.*`, `console.*` … | the member's args |
| `global` | `alert(...)` | the member's args |
| `entity` | `studio.project.model[<className>].*` (class introspection) | `className` + args |
| `instance` | `studio.project.lookup(target).*` | `target` (path or `{guid}`) + args |

Method args are auto-embedded: numbers/booleans as JS literals, a path
(`event:/…`, `bank:/Master`) or `{guid}` as an object reference (`lookup(...)`), else a
string. Settable properties take an optional `value` (omit to read).

**Generic — reach the dynamic, schema-defined members the static docs don't list**
(an event's `timeline`, an instrument's `audioFile`, a sound's `pitch`/`looping`, …):

| Tool | Purpose |
|---|---|
| `fmod_get_property` | Read any property of an object, including per-class managed properties. |
| `fmod_set_property` | Set any property (e.g. instrument `audioFile` = an asset). |
| `fmod_add_relationship` / `fmod_remove_relationship` | Edit a relationship (e.g. event `banks` → a bank). |
| `fmod_class_names` | List the project model's class names. |
| `fmod_describe_class` | List a class's schema-defined property + relationship names (discovery). |
| `fmod_create_event` | Composite: create event → import one-shot → add track/sound → assign bank. |

## Requirements

- **FMOD Studio 2.02+**, with a project open and the **Script Server enabled**
  (Preferences → *Interface* → *Script Server*, port **3663** — **requires a restart**; see
  [FMOD Studio setup](#fmod-studio-setup--enable-the-script-server) below). Opening the
  console (Ctrl+0) alone does **not** start it.
- Python 3.10+.

## FMOD Studio setup — enable the Script Server

The scripting terminal's TCP server (**Script Server**) is **off by default**, and opening
the console with **Ctrl + 0 is not enough** — that only shows script output. Enable it once:

1. Launch **FMOD Studio** and open your project (`File → Open Project…` → your `.fspro`).
2. Open **Preferences** — `FMOD Studio → Preferences…` (**⌘,**) on macOS, `Edit → Preferences…`
   on Windows.
3. Select the **Interface** tab — the **Script Server** section is at the top. Set:
   - ✅ **Enable Script Server (requires restart)**
   - **Port:** `3663` (must match `FMOD_STUDIO_PORT`, default `3663`).
4. **Quit and relaunch FMOD Studio**, then reopen the project. The setting only takes effect
   after a restart.
5. *(optional)* Open the console with **Ctrl + 0** to watch script output as tools run.

### Verify it's listening

```bash
# macOS / Linux
nc -z 127.0.0.1 3663 && echo "listening ✓"
lsof -nP -iTCP:3663 -sTCP:LISTEN          # shows the fmodstudio process bound to 3663
```

On every launch, FMOD records the Script Server state in its log:

```
[Scripting] ScriptServer started on 127.0.0.1 (3663)   ← enabled  ✅
[Scripting] ScriptServer is disabled.                  ← not enabled ❌
```

Log location: macOS `~/Library/Application Support/FMOD Studio/Logs/`,
Windows `%LOCALAPPDATA%\FMOD Studio\Logs\` (newest file).

### Troubleshooting

- **`Cannot reach FMOD Studio's scripting terminal…`** — the Script Server isn't running.
  Grep the newest log for `ScriptServer is disabled`; if present, enable it in Preferences
  and **restart** (the checkbox literally says *"requires restart"* — toggling without
  relaunching won't bind the port).
- **Enabled but still nothing on 3663** — confirm a **project is open** (the server won't
  bind on the start/welcome screen) and that no other app holds the port.
- **Port mismatch** — the Preferences port and `FMOD_STUDIO_PORT` must be the same value.

## Install

Run it straight from PyPI with [uv](https://docs.astral.sh/uv/) — no clone, no venv.
`uvx` downloads and launches it on demand:

```bash
claude mcp add fmod-studio -- uvx fmod-studio-mcp
```

Or add it to any MCP client's config (stdio):

```jsonc
"fmod-studio": { "command": "uvx", "args": ["fmod-studio-mcp"] }
```

Prefer a persistent install over on-demand? Install the package directly:

```bash
uv tool install fmod-studio-mcp   # exposes the `fmod-studio-mcp` command
# or, with pip:
pip install fmod-studio-mcp
```

Configure host/port if needed via env: `FMOD_STUDIO_HOST` (default `127.0.0.1`),
`FMOD_STUDIO_PORT` (default `3663`).

### From source (development)

```bash
git clone https://github.com/EYamanS/fmod-studio-mcp
cd fmod-studio-mcp
python3 -m venv .venv && ./.venv/bin/pip install -e .
claude mcp add fmod-studio -- "$(pwd)/.venv/bin/python" -m fmod_studio_mcp
```

## Regenerating for a new FMOD version

The tool set is generated from `fmod_studio_mcp/api_spec.json`, which is built by crawling
the official Scripting API reference:

```bash
python tools/build_spec.py fmod_studio_mcp/api_spec.json
```

A new FMOD release means re-running that crawler — not editing a tool registry by hand.

## Example

Create an event with a one-shot sound and route it to the Master bank, step by step
(or use the `fmod_create_event` composite to do it in one call):

```
fmod_project_create          { entityName: "Event" }            -> event:/New Event
fmod_set_property            { target: "event:/New Event", property: "name", value: "Hit" }
fmod_project_importAudioFile { filePath: "/abs/path/hit.wav" }  -> {asset-guid}
fmod_Event_addGroupTrack     { target: "event:/Hit", name: "Audio 1" } -> {track-guid}
fmod_get_property            { target: "event:/Hit", property: "timeline" } -> {tl-guid}
fmod_GroupTrack_addSound     { target: "{track-guid}", parameter: "{tl-guid}",
                               soundType: "SingleSound", start: 0, length: 2.5 } -> {inst-guid}
fmod_set_property            { target: "{inst-guid}", property: "audioFile", value: "{asset-guid}" }
fmod_add_relationship        { target: "event:/Hit", relationship: "banks", other: "bank:/Master" }
fmod_project_save            {}
```

## Safety

- Edits the **live** project. Run `fmod_project_save` to persist; commit the project to git.
- Avoid editing the same project in the Studio GUI and via this server simultaneously in
  conflicting ways.

## Support

Built this in the open. If it saved you time, a one-off tip keeps it maintained:

[![Buy me a coffee](https://img.shields.io/badge/%E2%98%95%20Buy%20me%20a%20coffee-support%20this%20project-FF813F?style=for-the-badge)](https://buy.polar.sh/polar_cl_v4ZIuYffdbN9E9iVLmlHh1W5sxAmxvqNVqIn81048FX)

## License

MIT — see [LICENSE](LICENSE).

---

<sub><b>Keywords:</b> FMOD Studio MCP server · FMOD scripting API automation · AI game-audio tooling · Model Context Protocol server for FMOD · Claude / LLM game-audio agent · programmatic FMOD Studio control · game sound-design automation.</sub>
