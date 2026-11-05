# Auto-starting the bridge

**Status:** Accepted

**A windowed Blender has to be told to serve, by hand, every session.** Until somebody opens
Preferences → Add-ons → MPFB Bridge and clicks the button, every tool answers with a connection
error. For someone who installed the bridge in order to use it, that is a chore that repeats forever.
A checkbox would end it, and blender lab's add-on has one.

**This reverses a documented decision, on purpose.**
[FR 029](../done/029-bridge-transport-and-skeleton/README.md#out-of-scope-deliberately) refused
autostart because "a listening socket that appears because software was installed" is what the pivot
claims to improve on, and said that adding it "means reversing a documented decision, which is a
request of its own and not a panel tweak". This is that request. What FR 029 protected survives if
the box is **off by default and only a human can tick it**: installing still opens nothing, and
ticking the box is the second, separate act that FR 029 asked starting to be. What does change is
the sentence "off until started from a preferences panel", in three places.

**A headless Blender already has a way to ask, and it is the right one.** Analysis below:
`blender --background --command mpfb_bridge` is Blender's own mechanism, and an environment variable,
an argument after `--` and the preference itself all fail for one structural reason, which is that a
background Blender gives an add-on nothing to wait on. **Checking this found two defects in the
existing route**, and those are the headless half of this effort:

- **Ctrl+C does not stop it.** Blender installs its own `SIGINT` handler in background mode, so
  `except KeyboardInterrupt` and the `finally` in `cli.py` never run. The first press prints "Sent an
  internal break event" and the bridge **keeps answering requests**. The second is "Blender killed",
  exit 2, with a leak report.
- **The "listening" line never reaches a pipe.** It is unflushed, so a process that started Blender
  and reads its output sees nothing while it serves, and on `SIGTERM` the line is lost altogether. A
  pipe had nothing to read a full second after the first request had been answered, and a redirected
  file was just as empty.

## Goals

**Primary:** a person who wants the bridge on in every windowed session ticks one box once; and a
person or a pipeline starting a headless Blender has one well-behaved way to ask for a server,
which can be supervised: it says when it is ready and stops when told.

**Secondary:** the two ways of starting agree about the address, and the documented posture stays
true after it has been reworded.

## Non-goals

- **An environment variable, or an argument after `--`.** See the analysis. Neither is a smaller
  version of this request; both are worse than what exists.
- **Honouring the checkbox in a background Blender.** See the analysis: this is the requirement most
  worth keeping.
- **A per-launch request for a windowed Blender**, without changing the preference. Nobody has asked,
  and here an environment variable would actually work, since a window has an event loop. It is easy
  to add later.
- **Telling a client which Blender answered.** With the box ticked, the first Blender started gets
  the port and a second one works without a bridge, so an agent may be changing a file other than the
  one on the screen. The panel in the second says so, and nothing tells the agent. That exists today
  but will be commoner after this. It would be a field on `get_status`, in a request of its own.
- **A delay preference.** blender lab's add-on has one, to avoid slowing startup. Binding a socket
  needs no such thing, and a one-shot timer is already after startup.
- **An indicator outside the preferences panel**, such as in the status bar. The bridge deliberately
  has no presence there ([ui.py](../../bridge/mpfb_bridge/ui.py)).

## Functional requirements

### The checkbox

1. The add-on's preferences have a checkbox, **"Start server when Blender starts"**, **off by
   default**, with the address settings. Its description says what it does, that any local process
   can drive Blender while the server runs, and that background mode ignores it.
2. With it ticked, a windowed Blender serves on the preferred host, port and poll interval without
   a click, whether or not a `.blend` was named on its command line.
3. **The box is a setting, not a switch.** Ticking it starts nothing now and unticking it stops
   nothing now; the Start and Stop buttons do that. It is saved like any other preference, so with
   Blender's auto-save off it needs Save Preferences, which [INSTALL.md](../../INSTALL.md) says.
4. **A failure to bind is quiet.** It raises nothing, shows no popup and does not stop Blender
   starting. It goes in the panel's error line and in the log at warning level. The Start button
   stays available. A second Blender finding the port taken is the expected case rather than a fault,
   as `command_server.start()`'s docstring already says.
5. Pressing Stop holds for the session. Opening a file neither starts nor stops the server.
   **Re-enabling the add-on or reloading scripts with the box ticked starts it**: that is the same
   `register()`, and telling them apart is not worth a second code path. The description need not say
   this, and [architecture.md](../../specifications/architecture.md#the-bridge) should.
6. The panel says when the running server was started automatically, so somebody who has forgotten
   ticking the box can see why a socket is open.
7. **No command reads or writes the box.** Like the export directory it belongs to the person who
   runs the bridge, and a socket must not be able to arrange for itself to open next time. No new tool,
   no new command, and `PROTOCOL_VERSION` does not change.

### In a background Blender

8. **The checkbox has no effect in a background Blender**: no socket, no timer, no message. With the
   box ticked, `blender --background file.blend --render-anim` still renders and exits,
   `blender --command extension build` still builds and the bridge's test harness still runs.
9. `--command mpfb_bridge` stays the one way to ask, with a `.blend` and `--python` scripts before it.

### The headless command

10. **Ctrl+C stops it at the first press**: the socket closes, the `finally` runs and the exit code
    is 0. `SIGTERM` does the same where the platform has it, since that is what a service manager
    sends. The previous handlers are put back when the loop ends.
11. **The "listening" line is flushed** as soon as the socket is bound, and it carries the real
    address, which `--port 0` needs. Its form becomes something a script may rely on, and INSTALL.md
    says so. A failure to bind stays one line and exit 1.
12. **`--host` and `--port` fall back to the preferences**, then to the defaults, as `--export-dir`
    already does. Today they skip the preference: somebody who set port 9900 and pointed their client
    at it gets a headless bridge on 9877. So the preference says *where*, and only the command line
    says *whether*.

### The words

13. The sentence "off until started" is true again wherever it is written: `ui.py`'s docstring (which
    also says autostart was refused), `blender_manifest.toml`'s comment, and architecture.md. So is
    `register()`'s docstring ("Starts no server"), and mpfb-mcp's refused-connection message, which
    should also name the checkbox while still naming the panel.

## Non-functional requirements

- **The posture is the point.** Nothing starts because of an install, a default, a `.blend` or
  anything arriving on the socket. Only a person's tick does, in preferences that only they edit.
- **One way to start.** The operator and the autostart must not each carry a copy of the start
  sequence, or they will drift on the idle-rate calculation, the error wording or the online-access
  hint.
- **Startup must not be able to break.** An exception escaping `register()` would disable the add-on
  and take the CLI command with it, and one escaping a timer callback is logged by Blender as a
  traceback nobody asked for. Neither may happen for any socket outcome.
- **Idle cost stays negligible.** Autostart means a poll in every session rather than in those that
  use the bridge. That poll is one non-blocking `accept` per second once idle, so this needs no work,
  but it is why the box is off by default even for a person who has installed the bridge.

## Architecture

### Which way to ask a headless Blender

Measured on Blender 5.1.0, with a startup module that registers a `@persistent` `load_post` handler
and a `persistent=True` timer at `first_interval=0`, against
`blender --background s.blend --python-expr ...`:

```
register(), background=True
load_post file=''
load_post file='s.blend'
python-expr
unregister
python atexit                (add-on already gone)
```

**The timer never fires**, as [architecture.md](../../specifications/architecture.md#the-bridge)
already records, and after the last argument Blender exits
(`blender/source/creator/creator.cc`, `WM_exit` straight after `ARG_PASS_FINAL`). The only exception
in that source is the deferred `--command`, which runs after
everything else on the command line and whose return value is the exit code. So anything the add-on
notices for itself has two options, and both are wrong: it blocks, in `register()` or `load_post`,
**in front of** the `.blend` and the `--python` scripts, which then never run; or it does not block,
and Blender exits.

| Way of asking | Result | Verdict |
|---|---|---|
| `--command mpfb_bridge` | File opened and script run first (3 objects seen, answered in 0.35 s). Blender's public mechanism, listed by `blender -c help` | **Keep** |
| Environment variable | No place to wait, as above. It is also inherited by every Blender started from that shell or by that process, including render workers and `--command extension build`, which would hang or collide. And it does not show in `ps`, so a process list no longer explains an open socket | Refuse |
| Argument after `--`, read from `sys.argv` | No place to wait, as above. Unlike an environment variable it shows in `ps` and is not inherited, but it adds nothing to `--command` and bypasses Blender's help and its error for an unknown command | Refuse |
| The checkbox, honoured in background | No place to wait, as above, **and** it would turn every background Blender on the machine into a server that never exits, for any purpose, from a setting made in a window | Refuse |
| `--python-expr` calling `cli_execute()` | Works, and [verification/](../../verification/README.md) records one run that needed it, on a machine with the add-on installed twice. It reaches into the add-on's internals for what `--command` offers publicly | Not for documenting |

What an environment variable can do that the command line cannot is reach a Blender whose command
line you do not write. A headless Blender is always started by something that writes its command
line, so that advantage is worth nothing here.

**Also measured, for the documentation:**

- `--command` consumes everything after it, so it goes last: `--command mpfb_bridge scene.blend` is
  `error: unrecognized arguments: scene.blend`, exit 2.
- With the add-on disabled it is `Unrecognized command: "mpfb_bridge"`, exit 1.
- `--addons bl_ext.user_default.mpfb_bridge` enables it for one process without touching any
  preference, which answers cli.py's "must be enabled" prerequisite. **`--factory-startup` does not
  carry a custom repository, though**: `--addons bl_ext.repo.mpfb,...` prints `Add-on not loaded:
  "bl_ext.repo.mpfb", cause: extension repository "repo" doesn't exist` and carries on, so the bridge
  came up, exit codes stayed clean and `get_status` said `absent`. So the recipe to document is
  `--addons` alone, not a clean profile.
- `--port 0` binds, and the line reports the real port (36797 in that run).
- A second bridge on a taken port exits 1 with one clear line.
- A Python handler installed before the loop fixes the signals. With `signal.signal` raising
  `KeyboardInterrupt`, `SIGINT` gave exit 0 in 0.09 s and "Interrupted.", and the port was closed;
  `SIGTERM` gave exit 0.

### The checkbox

- **A one-shot timer, registered in `register()` unless `bpy.app.background`, as blender lab's
  add-on does.** Timers run in the event loop, so it fires after startup, after the file named on the
  command line and after any `--python` script. It needs `persistent=True`, or the file load
  removes it.
- **Read the box when it fires, not in `register()`.** The context is restricted at registration and
  nothing is gained by reading early. Check `command_server.is_running()` too, because a `--python`
  script may have started it, and leave quietly if so.
- **`unregister()` cancels the one-shot first**, or disabling the add-on within that first moment
  leaves a callback into an unregistered add-on.
- **Extract the start sequence from `MPFB_BRIDGE_OT_server_start.execute`**, from clearing the error
  through to `timer.register_timer()`, into one function returning an error message or `None`. The
  operator reports what it returns; the one-shot only logs it. The `bpy.app.background` refusal stays
  in the operator. A small `autostart.py` beside `timer.py` holds the schedule, the cancel and the
  callback, and joins `__init__.py`'s list of modules.
- **`bpy.app.online_access` is not consulted**, as the operator does not consult it, for the reason
  [architecture.md](../../specifications/architecture.md#the-bridge) gives. blender lab's add-on
  refuses instead. An automatic start is a harder case for that reading than a click, but the
  tick is as explicit as the click, and two behaviours would be harder to explain. It should go to
  extension review with the rest of that reading.

### Pitfalls

- **Windows: `command_server.start()` sets `SO_REUSEADDR` unconditionally.** On Linux a second bind
  fails, as measured. Microsoft documents that on Windows two sockets with that option can both bind
  one port, with undefined delivery, so two Blenders would both "start" and a client would reach
  either. Rare with a button and routine with a checkbox. It should use `SO_EXCLUSIVEADDRUSE` there.
  **Not measured: no Windows machine was to hand.** If the effort has none either, the request must
  say so when it closes.
- **`cli.py` is the only place for the signal handlers.** They must not be installed at registration,
  since background Blender's own `SIGINT` behaviour is what stops a long render.
- **`--host` falling back to the preference is the human's choice applying where it was not applied
  before**, including a non-loopback one. That is right, and the help text must say it.
- **The fallback must tolerate there being no preference to read.** Measured on `--factory-startup
  --addons`: the bridge's CLI command is registered while `preferences.addons` has no entry for it.
  `export_directory.preference_value()` already guards this, and a read of host and port needs the
  same guard, or that recipe raises where it serves today.
- **`--factory-startup` means no box and no add-on**, which is correct and needs no code.
- **Not observed in a window.** Everything measured above was headless, because scoping did not open
  a window on the maintainer's desktop. The timer's shape is blender lab's, which is evidence rather
  than proof, and the live check below is what settles it.

## Affected specifications

- [architecture.md](../../specifications/architecture.md#the-bridge): the "off until started"
  defence is reworded; the two drive mechanisms gain the rule that the checkbox applies to the first
  only, and why the second cannot notice anything for itself; this request's measurements of the
  startup order go here.
- [vision.md](../../specifications/vision.md): "Installation is the consent" stays true and is not
  reworded. Check it still reads so.
- [testing.md](../../specifications/testing.md): only if the live check finds something a bridge test
  should have.

Beyond the specifications: [INSTALL.md](../../INSTALL.md) (the start instructions, the signals, the
ready line, `--addons`, and the `MPFB_BRIDGE_PORT` row, which says a headless bridge does not read
the preference) and the root [CLAUDE.md](../../CLAUDE.md)'s commands and its `bridge/` table row. No
tool is added, so neither the tool table nor the count changes.

## Tests

**`bridge/test/tests/aaa_addon/`**, since this is the add-on's own machinery rather than a command:

- The preference exists and defaults to off.
- With the box ticked, the decision to start is no in a background Blender, which the suite can
  assert for real because `bpy.app.background` is true there. Keep that decision a small function of
  its inputs, so that the windowed answers can be asserted too.
- The extracted start function binds and reports `None`; on a held port it returns the message, sets
  the panel's error and raises nothing. The one-shot obeys the same and returns `None`, whatever the
  socket did.
- `unregister()` removes a pending one-shot.
- The fallback order of `--host` and `--port`: command line, preference, default.

**`tests/`**: nothing, unless `test_bridge_connection.py` pins the wording that requirement 13
changes.

**Live, against a real Blender, in `live_check.py` in this subdir**, since the suite cannot reach the
event loop or a real signal. It must run with a **temporary `BLENDER_USER_CONFIG`**, holding a copy
of `userpref.blend` so that a custom extension repository still resolves, and it must never write to
the real one. It needs a display for the windowed half, and says so rather than passing without one.

| Case | Expected |
|---|---|
| Windowed, box off | Nothing listens |
| Windowed, box on | Answers without a click; on a file named on the command line, that file is the one open |
| Windowed, box on, second instance | The first still answers; the second reports it in its panel error state and is otherwise normal |
| Windowed, box on, Stop, then open a file | Stays stopped |
| Background, box on, no `--command` | Exits on its own, nothing ever listening |
| Background, box on, `--command` | Exactly one server, on the address asked for |
| `--port 0`, stdout a pipe | The line arrives before any request, and its port answers |
| `SIGINT`, once; then `SIGTERM` | Exit 0 each, port free at once |
| Port set in preferences, no `--port` | Serves on the preference |

No smoke item: no tool is introduced, and `verification/` drives the bridge rather than starting it.

## Decisions taken while scoping

- **The request is worth reversing FR 029 for**, off by default, as the maintainer asked. Vision and
  architecture rest on a person's explicit act, and the tick is one.
- **The preference is ignored in background rather than honoured with a warning**: a warning would be
  on a process that then hangs.
- **`--command` is kept rather than joined by anything.** Two ways to ask would mean two sets of
  documentation and no new ability.
- **Fixing the signals and the flush belongs here**, not in a defect entry of their own. A server
  started by a script is what "request to start it in a headless Blender" means, and it is not usable
  without them. **Exit 0 on a signal**, since a process that stops as asked has succeeded.
- **`--host` and `--port` follow the preference** because the checkbox makes it more likely that
  someone has set one.

## References

- [FR 029](../done/029-bridge-transport-and-skeleton/README.md#out-of-scope-deliberately): the
  refusal this reverses. [FR 028](../done/028-pivot-to-specific-addon/README.md): the posture.
- [FR 039](../done/039-exporting-characters/README.md): the command line, preference, default order
  that requirement 12 copies, and the argument for a setting no socket can reach.
- [FR 057](../057-install-selftest/README.md): what can be told from outside Blender. An autostart
  that failed looks like every other "nothing is listening".
- `blender_mcp/addon/blender_mcp_addon/__init__.py`: `use_autostart` (default **on** there),
  `_autostart_timer`, and the same background gate.
- `blender/source/creator/creator.cc` (the exit after the final argument pass),
  `creator_args.cc` (`arg_handle_command_set`), `creator_signals.cc` (`sig_handle_blender_esc`, the
  handler behind the Ctrl+C defect).
- Microsoft, "Using SO_REUSEADDR and SO_EXCLUSIVEADDRUSE", for the Windows pitfall.
