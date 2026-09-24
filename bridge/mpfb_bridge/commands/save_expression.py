"""
``save_expression``: keep a character's face as a named expression file.

The only way across from the composer to the library. A face composed with
``set_face_units`` lives in shape keys and nowhere else, and the next library
change rebuilds the face from the stack and destroys it (see
[`shared/expression_divergence.py`](../shared/expression_divergence.py)). Saving
it as an expression file makes it something the stack can reference, and once
``apply_expressions`` has put that file on the stack in ``replace`` mode, the
library's rebuilds reproduce the face rather than erase it - and a preset,
which serializes the stack, carries it.

**It saves the shape keys, not MPFB's composer sliders, and that is a choice.**
MPFB's own save operator (``makeexpression/operators/save.py``) builds the file
from the composer panel's scene properties, ``MPFB_EX_<unit>`` - which
``set_face_units`` never writes, since it goes through
``FaceService.set_expression`` directly. Reproducing the operator would save the
panel's stale sliders rather than the face the agent composed. The live face is
read with ``FaceService.read_current_expression()`` and written with
``FaceService.save_expression()``, which drops zero units, drops names outside
``ARKIT_FACEUNITS`` and rounds to four decimals. One consequence is stated in
the answer: the live face includes whatever the stack contributed, so what is
saved is **the whole face**, and the call that makes it durable is
``apply_expressions`` in ``replace`` mode - merging would count the stack twice.
This is a case of
[MPFB's own code paths disagreeing](../../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it).

**It writes outside the ``.blend``, so it owes what ``save_preset`` owes**
([mutating-tools.md](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more)):
every precondition is settled before the file is opened, the absolute ``path``
and the ``fragment`` are in every answer, and an existing file is replaced only
when ``overwrite`` says so. The name is a name and never a path - the rule is
[`shared/artifact_names.py`](../shared/artifact_names.py)'s, shared with the
preset commands and checked first on mpfb-mcp's side. The file is always
``<name>.json`` directly in ``LocationService.get_user_data("expressions")``,
and this command builds that absolute path itself, so that
``save_expression``'s bare-name branch - which appends ``.json`` only when it is
absent - never decides what the file is called. The name is saved **as given**:
the composer's ``expression_name`` property says names are "lowercased and
dash-separated when saved", which nothing in MPFB does.

**It refuses a name the library would never find.** ``user_data`` is third in
MPFB's root priority. A file saved there while ``mpfb_data`` or ``mh_data`` holds
one with the same basename would be written and then never listed, never
applied and never restored from a preset - ``list_available_expressions`` keeps
the first root's copy of a path, and ``find_asset_absolute_path`` matches by
basename and falls back to the first match. MPFB's composer panel says the
opposite ("user-saved expressions take priority over system-shipped ones"), and
FR 027's live check confirmed the code rather than the panel. So this is
``blocked_by: "name_shadowed"``, naming the file that would win.

**``license`` defaults to ``"CC0"``**, the composer panel's default, rather than
``save_expression``'s empty string, per the rule in
[mpfb-integration.md](../../../specifications/mpfb-integration.md) for where
MPFB's UI re-defaults a service argument.
The metadata actually written is read back from the file and reported.

**It changes nothing on the character.** It does make the new file visible in
MPFB's expressions-library panel, as MPFB's save operator does, by calling
``refresh_expression_sliders()`` - see
[`shared/expression_panel.py`](../shared/expression_panel.py). ``panel_synced``
reports the outcome.
"""

# The local bindings below are spelled with MPFB's own capitalisation.
# pylint: disable=invalid-name,protected-access

__all__ = (
    "PARAMS",
    "SUMMARY",
    "save_expression",
)

import json
import os

from ..log import get_logger
from ..shared import expression_panel
from ..shared import subject_resolution
from ..shared.artifact_names import file_facts
from ..shared.artifact_names import name_rejection
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.saveexpression")

PARAMS = (
    Param("name", TYPE_STRING, required=True,
          description="The expression's name, never a path. Letters, digits, underscore, "
                      "hyphen and dot only; it becomes <user data>/expressions/<name>.json."),
    Param("subject", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("overwrite", TYPE_BOOLEAN, default=False,
          description="Replace an existing expression file of this name. False by default: "
                      "there is no undo for a file across this socket."),
    Param("description", TYPE_STRING, default="",
          description="The file's description field: a sentence suitable for a tooltip."),
    Param("tags", TYPE_ARRAY, default=(),
          description="The file's tags: a list of strings, conventionally lowercase."),
    Param("author", TYPE_STRING, default="",
          description="The file's author field."),
    Param("copyright", TYPE_STRING, default="",
          description="The file's copyright field."),
    Param("license", TYPE_STRING, default="CC0",
          description="The file's license field. CC0 is the composer panel's default."),
    Param("homepage", TYPE_STRING, default="",
          description="The file's homepage field."),
)

SUMMARY = "Save a character's live face as a named expression file in MPFB's user data."

METADATA_KEYS = ("description", "tags", "author", "copyright", "license", "homepage")


class _Request:
    """One call's resolved state, so the refusals can be read in one place."""

    __slots__ = ("expressions_dir", "file_path", "fragment", "name_rejection", "previous_file",
                 "subject", "subject_resolved_by", "subject_message", "basemesh")


def _resolve(services, params):
    """Everything that has to be true before a byte is written."""
    request = _Request()
    request.expressions_dir = str(services["LocationService"].get_user_data("expressions"))
    request.name_rejection = name_rejection(params["name"], "expression")
    request.file_path = None
    request.fragment = None
    request.previous_file = None
    if request.name_rejection is None:
        request.fragment = params["name"] + ".json"
        request.file_path = os.path.join(request.expressions_dir, request.fragment)
        facts = file_facts(request.file_path)
        request.previous_file = facts if facts["exists"] else None

    # A miss is recorded, not returned: _refusal() judges the name and the file
    # too, and decides which refusal comes first.
    (request.basemesh, request.subject, request.subject_resolved_by,
     request.subject_message) = subject_resolution.resolve_basemesh(
         services, params["subject"],
         not_done="nothing was saved",
         not_a_character="there is no face to save")
    return request


def _higher_priority_roots(services):
    """The expressions roots MPFB searches **before** user data, in its own order.

    ``AssetService.get_available_data_roots()`` orders its roots ``mpfb_data``,
    ``mh_data``, ``user_data``, ``second_root``; the two before ``user_data``
    are the ones that can hide a file saved there.
    """
    LocationService = services["LocationService"]
    user_data = os.path.abspath(str(LocationService.get_user_data()))
    roots = []
    for root in (LocationService.get_mpfb_data(), LocationService.get_mh_user_data()):
        if not root:
            continue
        root = os.path.abspath(str(root))
        if root == user_data:
            continue
        expressions = os.path.join(root, "expressions")
        if os.path.isdir(expressions):
            roots.append(expressions)
    return roots


def _shadowing_file(services, fragment):
    """The file that would win over ``<user data>/expressions/<fragment>``, or None.

    Walked the way ``find_asset_absolute_path`` walks, because that is how every
    application and every rebuild resolves a stack row: by basename, across the
    roots in priority order, taking the first match. A same-named file anywhere
    under a higher-priority root wins - which covers the listing's own rule
    (same library-relative path) as its narrowest case.
    """
    for root in _higher_priority_roots(services):
        for dirpath, _dirs, files in os.walk(root):
            if fragment in files:
                path = os.path.abspath(os.path.join(dirpath, fragment))
                relative = os.path.relpath(path, root).replace(os.sep, "/")
                return dict(path=path, fragment=relative,
                            same_fragment=relative == fragment)
    return None


def _blocked(params, request, reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    answer = dict(
        found=request.basemesh is not None,
        ready=False,
        saved=False,
        blocked_by=reason,
        name=params["name"],
        subject_name=None if request.subject is None else request.subject.name,
        subject_resolved_by=request.subject_resolved_by,
        basemesh_name=None if request.basemesh is None else request.basemesh.name,
        expressions_dir=request.expressions_dir,
        # Always present, on a refusal as much as on a success: the caller
        # cannot see the directory, and "which file would this have been" is the
        # first thing they need in order to fix a name or pass overwrite.
        path=request.file_path,
        fragment=request.fragment,
        overwrote=False,
        previous_file=request.previous_file,
        message=message,
    )
    answer.update(extra)
    return with_performed(answer, False)


def _metadata(params):
    metadata = {key: params[key] for key in METADATA_KEYS}
    metadata["tags"] = [str(tag) for tag in (params["tags"] or [])]
    metadata["name"] = params["name"]
    return metadata


def _read_back(path):
    """What the written file holds, parsed from it rather than assembled from the request."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def save_expression(params, resolution):  # pylint: disable=too-many-return-statements
    """Write one face to one file, having settled everything else first."""
    services = resolution.services
    FaceService = services["FaceService"]
    request = _resolve(services, params)

    def blocked(reason, text, **extra):
        return _blocked(params, request, reason, text, **extra)

    if request.basemesh is None:
        return blocked("subject_not_found", request.subject_message)
    if request.name_rejection is not None:
        # Defence in depth: mpfb-mcp refuses this before a request is built (see
        # mpfbmcp/artifact_names.py), so reaching it here means something else
        # spoke to this socket. It is the last statement before a path is
        # assembled.
        return blocked(
            "invalid_name",
            request.name_rejection + " An expression is always <name>.json in the "
            "expressions directory of MPFB's user data, so a name that could become a path is "
            "refused rather than resolved.")
    tags = params["tags"] or []
    if not all(isinstance(tag, str) for tag in tags):
        return blocked("invalid_tags", "tags must be a list of strings, so nothing was saved.")
    previous_file = request.previous_file
    if previous_file is not None and not params["overwrite"]:
        return blocked(
            "expression_exists",
            "An expression file '{:s}' already exists, written {!s}, and overwrite is false, so "
            "nothing was written. Pass overwrite=true to replace it, or choose another name - "
            "there is no undo for a file across this socket. The directory is shared with "
            "installed asset packs, so the existing file may not be one you wrote.".format(
                # pylint cannot see past the None check two lines up.
                request.fragment, previous_file["modified"]))  # pylint: disable=unsubscriptable-object
    shadowing = _shadowing_file(services, request.fragment)
    if shadowing is not None:
        return blocked(
            "name_shadowed",
            "A file named '{:s}' already exists in a data root MPFB searches before user data "
            "('{:s}'), so an expression saved under this name would be written and then never "
            "listed, applied or restored from a preset - MPFB resolves expression files by "
            "basename, first root first. Nothing was written. Choose another name.".format(
                request.fragment, shadowing["path"]),
            shadowed_by=shadowing)

    live = FaceService.read_current_expression(request.basemesh)
    non_zero = {name: float(value) for name, value in live.items() if float(value) != 0.0}
    if not non_zero:
        return blocked(
            "empty_expression",
            "Every face unit on '{:s}' is 0.0, and an expression with no non-zero face unit is "
            "not a valid expression file - MPFB's own save refuses one too. Nothing was "
            "written. Compose a face with mpfb_set_face_units first.".format(
                request.basemesh.name))

    # Everything above is settled, so this is the first statement that changes
    # anything. The directory is created here, as MPFB's save operator creates
    # it, rather than being a refusal: on a fresh install it simply has not been
    # needed yet.
    os.makedirs(request.expressions_dir, exist_ok=True)
    try:
        FaceService.save_expression(request.file_path, live, _metadata(params))
    except Exception as error:  # pylint: disable=broad-except
        now = file_facts(request.file_path)
        return blocked(
            "save_failed",
            "MPFB raised while writing '{:s}': {:s}. current_file reports what is at that path "
            "now.".format(request.file_path, str(error)),
            current_file=now if now["exists"] else None)

    written = file_facts(request.file_path)
    contents = _read_back(request.file_path) or {}
    panel_synced, panel_sync_reason, sliders_added = expression_panel.refresh_sliders(
        resolution.module.__name__)
    stack = FaceService._read_applied_expressions(request.basemesh)

    parts = ["Saved the face of '{:s}' as '{:s}' ({:d} face unit(s)).".format(
        request.basemesh.name, request.file_path, len(contents.get("face_units") or {}))]
    if previous_file is not None:
        parts.append(" It replaced an existing file of {!s} bytes written {!s}; that file is "
                     "gone and cannot be restored from here.".format(
                         previous_file["size_bytes"], previous_file["modified"]))
    if stack:
        parts.append(" The saved face includes what the character's {:d} applied "
                     "expression(s) contributed.".format(len(stack)))
    parts.append(
        " Nothing on the character changed: to make this face survive the next library change "
        "and a preset, call mpfb_apply_expressions with mode 'replace' and fragment '{:s}' at "
        "1.0 - replace, not merge, since the file already holds the whole face.".format(
            request.fragment))
    if not panel_synced:
        parts.append(" MPFB's expressions-library panel was not updated; see panel_sync_reason.")

    result = dict(
        found=True,
        ready=True,
        saved=True,
        blocked_by=None,
        name=params["name"],
        subject_name=request.subject.name,
        subject_resolved_by=request.subject_resolved_by,
        basemesh_name=request.basemesh.name,
        expressions_dir=request.expressions_dir,
        path=request.file_path,
        fragment=request.fragment,
        size_bytes=written["size_bytes"],
        modified=written["modified"],
        overwrote=request.previous_file is not None,
        previous_file=request.previous_file,
        face_units=contents.get("face_units") or {},
        metadata={key: contents.get(key) for key in ("name",) + METADATA_KEYS},
        stack_contributed=bool(stack),
        apply_with=dict(expressions=[dict(fragment=request.fragment, weight=1.0)],
                        mode="replace"),
        panel_synced=panel_synced,
        panel_sync_reason=panel_sync_reason,
        panel_sliders_added=sliders_added,
        message="".join(parts),
    )
    _LOG.debug("save_expression: wrote %r", request.file_path)
    return with_performed(result, True)
