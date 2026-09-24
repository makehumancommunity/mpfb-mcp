# Installing MPFB MCP

How to get every part of this repository working from a source checkout. Nothing here has been
published: there is no package on PyPI and no listing on extensions.blender.org, so everything
below installs from the clone you are reading this in.

## What you are installing

Three pieces, in a chain. A call from your MCP client passes through all of them:

```
MCP client (Claude Code, Claude Desktop, ...)
    │  stdio, JSON-RPC
    ▼
mpfb-mcp            a Python process your MCP client starts   ← src/ in this repo
    │  TCP 127.0.0.1:9877
    ▼
MPFB Bridge         a Blender extension                       ← bridge/mpfb_bridge/ in this repo
    │  Python calls inside Blender
    ▼
MPFB                the MakeHuman Plugin For Blender           ← installed separately
```

- **mpfb-mcp** is the MCP server. It never imports Blender or MPFB; it only sends named commands
  over a socket.
- **The MPFB Bridge** is a Blender add-on of this project's own. It listens on the socket, looks
  each command up in a fixed table and calls MPFB. It runs no code a caller sends.
- **MPFB** is the actual character creator, and is not part of this repository.

The two halves in this repository check at connect time that they speak the same protocol version.
Install both from the **same checkout** and they always will.

## Prerequisites

| What | Why |
|------|-----|
| **Blender 5.0 or newer** | The bridge's floor (`blender_version_min` in [blender_manifest.toml](bridge/mpfb_bridge/blender_manifest.toml)). It is higher than MPFB's own floor on purpose. |
| **MPFB 2**, installed and enabled in that Blender | What every tool drives. |
| **The MakeHuman system assets pack**, installed into MPFB | Without it there are no skins, eyes or other base assets, and several tools have nothing to list or apply. |
| **Python 3.10 or newer**, with `venv` | For the mpfb-mcp process. This does *not* need to be Blender's Python. |
| An MCP client | Claude Code and Claude Desktop are covered below. Any stdio MCP client works the same way. |

Optional, needed only by specific tools:

- **Rigify** (bundled with Blender, disabled by default) — needed by `mpfb_generate_rigify_rig`
  and by adding a Rigify meta rig. Enable it under *Edit → Preferences → Add-ons*.
- **The `faceunits01` asset pack** — needed by `mpfb_set_face_units`. Without it the tool refuses
  with a message saying so; `mpfb_get_face_units` still answers.
- **Other asset packs** (clothes, hair, proxies and so on) — whatever you want the catalogue tools
  to find.

## 1. Clone the repository

If you do not already have a checkout, clone it from wherever you were given it:

```bash
git clone <repository-url> mpfb-mcp
```

```bash
cd mpfb-mcp
```

Every path below is relative to this directory unless it says otherwise. Where a step needs an
**absolute** path to the clone, it is written `/path/to/mpfb-mcp`.

## 2. Install MPFB in Blender

If you already use MPFB in Blender 5.0 or newer, skip to step 3.

1. In Blender, open *Edit → Preferences → Get Extensions*, search for **MPFB** and install it.
   (If you run MPFB from a source checkout of `mpfb2` instead, that works equally well; the bridge
   finds MPFB whatever repository it was installed into.)
2. Download the **MakeHuman system assets** pack, and any other packs you want, from the MakeHuman
   community site. Once everything below is running, the `mpfb_list_urls` tool will give you the
   addresses; it answers even when MPFB is not installed yet.
3. In MPFB's sidebar panel, go to *Apply assets → Library settings* and click
   **Load pack from zip file** for each pack.
4. Restart Blender.

See MPFB's own
[getting started guide](https://static.makehumancommunity.org/mpfb/docs/getting_started.html) for
screenshots of these steps.

## 3. Install the MPFB Bridge add-on in Blender

There are two ways. **Use the symlink if you will edit or update the checkout**, since Blender
then always runs the code in your clone. Use the zip if you just want it installed.

### Option A: symlink into an extension repository (recommended for a checkout)

Blender loads user extensions from a `user_default` repository whose location depends on the
platform and the Blender version (`5.1` below; use yours):

| Platform | Directory |
|----------|-----------|
| Linux | `~/.config/blender/5.1/extensions/user_default/` |
| macOS | `~/Library/Application Support/Blender/5.1/extensions/user_default/` |
| Windows | `%APPDATA%\Blender Foundation\Blender\5.1\extensions\user_default\` |

Link the add-on's directory into it, keeping the name `mpfb_bridge`. On Linux:

```bash
mkdir -p ~/.config/blender/5.1/extensions/user_default
```

```bash
ln -s "$PWD/bridge/mpfb_bridge" ~/.config/blender/5.1/extensions/user_default/mpfb_bridge
```

On macOS use the same `ln -s` with the macOS directory. On Windows, a directory junction does the
same job, from `cmd` and without administrator rights:
`mklink /J "%APPDATA%\Blender Foundation\Blender\5.1\extensions\user_default\mpfb_bridge" C:\path\to\mpfb-mcp\bridge\mpfb_bridge`.

Link the directory `bridge/mpfb_bridge`, **not** `bridge/`: the manifest is one level down, and
`bridge/` also holds the test harness and developer configuration, which are not part of the
add-on.

### Option B: build a zip and install it from disk

Blender can package the extension itself. The output directory has to exist first:

```bash
mkdir -p dist
```

```bash
blender --command extension build --source-dir bridge/mpfb_bridge --output-dir dist
```

This writes `dist/mpfb_bridge-<version>.zip` (`dist/` is gitignored). In Blender, open
*Edit → Preferences → Get Extensions*, use the drop-down in the top right and choose
**Install from Disk...**, and pick the zip. A zip install is a copy: after pulling new code you
have to build and install it again.

### Enable it

Restart Blender, open *Edit → Preferences → Add-ons*, find **MPFB Bridge** and tick it. Its
preferences panel should now say **MPFB is loaded and initialized**. If it says MPFB is not
loaded, fix that before going further; nothing else will work until it does.

The add-on declares a `network` permission because it opens a socket. It binds `127.0.0.1` only,
and it works with Blender's *Allow Online Access* setting either on or off.

## 4. Install the mpfb-mcp server

On most Linux distributions the system Python refuses `pip install` outside a virtual environment
(PEP 668), so make one in the clone:

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -e .
```

On Windows the two commands are `py -m venv .venv` and `.venv\Scripts\pip install -e .`.

This is an **editable** install: the `mpfb-mcp` command it creates runs the code in `src/`
directly, so a `git pull` takes effect the next time the server starts, with no reinstall. The one
exception is a change to the dependencies in [pyproject.toml](pyproject.toml), which needs the
`pip install -e .` again.

The command is now at `/path/to/mpfb-mcp/.venv/bin/mpfb-mcp` (Windows:
`.venv\Scripts\mpfb-mcp.exe`). **Your MCP client needs that absolute path**, because it will not
have the venv activated. You can confirm it exists without starting anything:

```bash
ls "$PWD/.venv/bin/mpfb-mcp"
```

Do not run it by hand to test it: it speaks JSON-RPC on stdin and stdout and will sit waiting for
a client.

## 5. Connect an MCP client

Any name works for the server; `mpfb` is used below. The tools then appear to the client as
`mpfb_get_status`, `mpfb_create_human` and so on (Claude Code shows them prefixed with the server
name, e.g. `mcp__mpfb__mpfb_get_status`).

### Claude Code

Register the server once, for every project:

```bash
claude mcp add --scope user mpfb -- /path/to/mpfb-mcp/.venv/bin/mpfb-mcp
```

Use `--scope local` (the default) instead to make it available only in the directory you run the
command from, or `--scope project` to write it into a `.mcp.json` there that can be committed. For
a bridge on a non-default port, pass the environment with `-e` before the name:

```bash
claude mcp add --scope user -e MPFB_BRIDGE_PORT=9900 mpfb -- /path/to/mpfb-mcp/.venv/bin/mpfb-mcp
```

Check it with:

```bash
claude mcp list
```

and inside a session with `/mcp`, which also reconnects the server after you have pulled new code.

### Claude Desktop

Open *Settings → Developer → Edit Config*, which opens `claude_desktop_config.json`:

| Platform | File |
|----------|------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

Add an entry under `mcpServers`, keeping any that are already there:

```json
{
  "mcpServers": {
    "mpfb": {
      "command": "/path/to/mpfb-mcp/.venv/bin/mpfb-mcp",
      "args": []
    }
  }
}
```

On Windows the command is `C:\\path\\to\\mpfb-mcp\\.venv\\Scripts\\mpfb-mcp.exe`, with the
backslashes doubled because this is JSON. To set any of the environment variables in the table
below, add an `"env": { "MPFB_BRIDGE_PORT": "9900" }` object beside `"args"`.

Quit Claude Desktop completely and start it again; it reads the file only at startup. The tools
then appear in the tools menu of a new chat.

### Other clients

Any MCP client that can start a stdio server works: give it the absolute path to
`.venv/bin/mpfb-mcp`, no arguments, and whichever environment variables you need.

### Environment variables

All optional. Set them in the client's configuration for the server, not in your shell.

| Variable | Default | What it does |
|----------|---------|--------------|
| `MPFB_BRIDGE_HOST` | `127.0.0.1` | Where the bridge is listening. |
| `MPFB_BRIDGE_PORT` | `9877` | Its port. Must match the bridge's preferences, or `--port` for a headless one. |
| `MPFB_MCP_LOG_LEVEL` | off | `INFO` or `DEBUG` logs each call to stderr, which most clients keep in their MCP server log. |
| `MPFB_MCP_RECORD_DIR` | off | A directory to keep the exact request and response of every call in. Diagnostic output about your machine: read it before sharing it, and do not point it inside this repository. |

`MPFB_MCP_BACKEND` is no longer read. If an old configuration still sets it, remove it; until you
do, the server logs one warning saying so.

## 6. Start the bridge's server

**The socket is off until you turn it on**, every time Blender starts. This is deliberate: an
installed add-on does not open a port by itself.

- **In a Blender with a window**: *Edit → Preferences → Add-ons → MPFB Bridge*, click
  **Start MPFB Bridge server**. The panel then says it is running, and counts requests as they
  arrive.
- **In a Blender with no window** (a server, a pipeline, a throwaway instance for testing):

  ```bash
  blender --background --command mpfb_bridge
  ```

  It serves until Ctrl+C. Add `--port 9900` to listen elsewhere, and put a `.blend` path before
  `--command` to open one first. The start button refuses in background mode, since a background
  Blender has no event loop to drive it; this command is the replacement, not a workaround.

Order does not matter. The MCP client can start mpfb-mcp before Blender is running; until the
bridge is up, each tool answers with an error naming the preferences panel, except
`mpfb_list_urls` and `mpfb_list_docs`, which answer anyway.

## 7. Check that it works

From your MCP client, ask for the MPFB status (the `mpfb_get_status` tool). A working install
answers with `state: "ok"`, MPFB's version and Blender's. Then ask it to create a human
(`mpfb_create_human`), and one should appear in the Blender scene.

From the checkout, two further checks are available.

The unit tests need no Blender at all:

```bash
.venv/bin/python -m unittest discover -s tests
```

The **smoke run** calls every tool once against a real Blender, in about two seconds. It builds
characters and leaves them in the scene, so point it at a Blender you will throw away — a headless
one is easiest:

```bash
blender --background --command mpfb_bridge --port 9900
```

and then, in another terminal:

```bash
MPFB_BRIDGE_PORT=9900 PYTHONPATH=. .venv/bin/python verification/smoke.py
```

It also writes one preset file into MPFB's config directory. See
[verification/README.md](verification/README.md) for what it checks and what it leaves behind.

## 8. For development on the bridge (optional)

Only needed to run the bridge's own tests, which run inside a headless Blender with pytest.

1. The add-on must be installed through a **symlink** to this checkout (option A above). It does
   not need to be enabled; the test runner enables it for its own process.
2. pytest must be installed into **Blender's** bundled Python: open
   [bridge/test/run_to_install_pytest.py](bridge/test/run_to_install_pytest.py) in Blender's
   *Scripting* workspace and run it once. It needs write permission to Blender's installation.

Then:

```bash
BLENDER_EXE=$(which blender) bridge/test/execute_tests_headless.bash
```

For static type checking of the add-on as MPFB does it, install
[bridge/requirements-dev.txt](bridge/requirements-dev.txt) into any venv and run `pyright` in
`bridge/`. Details are in [bridge/test/README.md](bridge/test/README.md).

## Updating

With the symlink and the editable install, `git pull` is the whole update, followed by:

- **restarting Blender** (or disabling and re-enabling MPFB Bridge) so it loads the new add-on
  code, and
- **restarting the MCP server** — `/mcp` in Claude Code, or quitting and restarting Claude Desktop.

Do both. A client and a bridge from different commits can disagree about the protocol version,
and every call then fails with a message saying which end to upgrade.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Every tool reports a refused connection | The bridge server is not started (step 6), or it is on a different host or port than `MPFB_BRIDGE_HOST` / `MPFB_BRIDGE_PORT` say. |
| **Start MPFB Bridge server** fails with "address already in use" | Something else holds port 9877 — often a second Blender with the bridge already running. Stop that one, or change the port in the preferences and in the client configuration together. |
| `mpfb_get_status` says `absent` | MPFB is not installed or not enabled in *that* Blender. The bridge's preferences panel says where it looked. |
| `mpfb_get_status` says `not_initialized` | MPFB is loaded but failed during startup. Blender's console (*Window → Toggle System Console* on Windows; the terminal Blender was started from elsewhere) has MPFB's error. |
| `blender --background --command mpfb_bridge` says the command is unknown | The add-on is installed but not enabled in that Blender's preferences. A disabled extension registers no command-line command. |
| MPFB Bridge is not in the add-on list | Blender older than 5.0, or the symlink points at `bridge/` rather than `bridge/mpfb_bridge/`, or Blender was not restarted after adding it. |
| The client shows the server as failed or disconnected | The path to `mpfb-mcp` in the configuration is not absolute, or points outside the venv. Run `claude mcp list`, or check Claude Desktop's MCP log, for the actual error. |
| Skins, clothes or rigs lists come back empty | The asset packs are not installed into MPFB (step 2), or Blender was not restarted after installing them. |
| `mpfb_generate_rigify_rig` fails | Rigify is not enabled in Blender's add-ons. |
| `mpfb_set_face_units` refuses | The optional `faceunits01` asset pack is not installed. |
