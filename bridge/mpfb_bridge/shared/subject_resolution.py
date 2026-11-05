"""
Which object a command is about, and which character that object belongs to.

**One implementation, imported by all twenty commands that take a subject.**
See [`__init__.py`](__init__.py) for why this directory exists beside
``commands/``. Every tool that takes a subject promises the same three things
about it, and a promise made twenty times is kept only if it is written once:

- **The active object is the view layer's**, not ``bpy.context.active_object``.
  A command runs from a timer or from the headless loop, never from a viewport
  operator, and the view-layer form does not depend on which UI area happens to
  be current. It is ``None`` whenever nothing is active, which is an answer.
- **A name is looked up in the file, not the scene.** Object names are unique
  across the whole ``.blend``, and an object outside the current scene is still
  a character whose answers can be read.
- **Any object in the character's family will do.** The caller may be holding
  the name of the rig or of a garment, since that is what ``list_objects`` hands
  out, so the basemesh is found the way MPFB's own macro and rig panels find it:
  ``ObjectService.find_object_of_type_amongst_nearest_relatives()``. The object
  actually acted on is reported back, never the argument echoed.

It also says **how the subject was resolved**, ``"active"`` or ``"name"``, so
that no command computes ``subject_resolved_by`` on a line of its own. All
twenty report it under that key; ``get_object_info`` said
``resolved_from: "active_object"`` until FR 037.

**The condition is here; the wording is not**, as in
[`refit_blocker.py`](refit_blocker.py). The three sentences share their shape,
and the phrases that differ are passed in by each command, so a reader of
``set_skin.py`` can see that it says "no skin was applied" without opening this
file. ``not_done`` says what did not happen, and is ``None`` for a command that
only reads. ``not_a_character`` finishes the sentence said when the subject has
no basemesh among its relatives, the one part of a miss that depends on what was
being asked.

**Nothing here raises, and nothing short-circuits.** Every function returns its
answer, a miss included, because the order in which a command reports its
refusals is part of that command's contract. ``save_preset`` and
``save_expression`` record a subject miss and go on to judge the file name;
``add_rig`` judges the rig identifier first. A resolver that raised would decide
that order for them.

**A mesh being authored belongs to nobody yet**, so :func:`resolve_asset_body`
looks further than a family, in a fixed order: a named ``basemesh``; one among the
mesh's nearest relatives, which is how the macro and rig panels find one; the one
selected, which is how MakeClothes' own panel does; the only one in the file. Several
at the last two is a refusal, because a fit against the wrong body reads as a bad fit.
``check_mesh_asset`` and ``write_mesh_asset`` share it, since the write must be about
the body the check measured.

``resolve_subject`` reads nothing out of MPFB, and takes no ``services``. The other
two take ``services`` first, for the reason the rest of this directory does.
"""

__all__ = (
    "resolve_asset_body",
    "resolve_basemesh",
    "resolve_subject",
    "so_clause",
)

import bpy


def so_clause(not_done):
    """``", so <not_done>"``, or nothing: how a refusal's sentence says what was not done.

    Public because :mod:`pose_controls`' posing refusals finish their sentences
    the same way, and two copies of a clause are two places for it to drift.
    """
    return "" if not_done is None else ", so {:s}".format(not_done)


def resolve_subject(requested_name, not_done=None, select="a MakeHuman object"):
    """The object asked about, how it was found, and the sentence on a miss.

    Returns ``(subject, resolved_by, message)``, where ``message`` is ``None``
    exactly when ``subject`` is not. ``select`` is what the caller is told to
    select when nothing is active: ``get_object_info`` accepts any object at
    all, and says so.
    """
    resolved_by = "active" if requested_name is None else "name"
    if requested_name is None:
        subject = bpy.context.view_layer.objects.active
        if subject is None:
            return (None, resolved_by,
                    "No object name was given and no object is active in this Blender "
                    "session{:s}. Select {:s}, or call mpfb_list_objects and pass one of its "
                    "names.".format(so_clause(not_done), select))
        return (subject, resolved_by, None)

    subject = bpy.data.objects.get(requested_name)
    if subject is None:
        # str() although the parameter contract already refuses a name that
        # is not a string: the socket is reachable by clients other than
        # mpfb-mcp, and if that check is ever loosened, the sentence that
        # refuses the name must not be what fails.
        return (None, resolved_by,
                "No object named '{:s}' exists in this .blend file{:s}. Call mpfb_list_objects "
                "to see what the current scene holds.".format(str(requested_name),
                                                              so_clause(not_done)))
    return (subject, resolved_by, None)


def resolve_basemesh(services, requested_name, not_a_character, not_done=None):
    """The basemesh, the object asked about, how it was found, and the sentence on a miss.

    Returns ``(basemesh, subject, resolved_by, message)``. On a miss
    ``basemesh`` is ``None``; ``subject`` is ``None`` too unless the object
    exists and merely belongs to no character, in which case it is returned so
    the command can name it in its answer.
    """
    subject, resolved_by, message = resolve_subject(requested_name, not_done=not_done)
    if subject is None:
        return (None, None, resolved_by, message)

    basemesh = services["ObjectService"].find_object_of_type_amongst_nearest_relatives(
        subject, "Basemesh")
    if basemesh is None:
        return (None, subject, resolved_by,
                "'{:s}' has no MakeHuman basemesh among its nearest relatives, so {:s}. Call "
                "mpfb_get_object_info to see what it is related to.".format(
                    subject.name, not_a_character))
    return (basemesh, subject, resolved_by, None)


def resolve_asset_body(services, requested, subject, purpose, not_done):
    """``(basemesh, resolved_by, refusal)``, in the order this module's docstring gives.

    ``refusal`` is ``(blocked_by, sentence, candidates)``, or ``None``. ``purpose``
    finishes "there is no body ..." and ``not_done`` says what did not happen.
    """
    object_service = services["ObjectService"]
    if requested is not None:
        body, _resolved_by, message = resolve_subject(requested)
        if body is None:
            return (None, None, ("basemesh_not_found", message, []))
        if not object_service.object_is_basemesh(body):
            return (None, None, (
                "not_a_basemesh",
                "'{:s}' is not a MakeHuman basemesh, so there is no body {:s}. "
                "Call mpfb_list_objects with 'Basemesh' to see which there are.".format(
                    body.name, purpose),
                []))
        return (body, "argument", None)

    relative = object_service.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")
    if relative is not None:
        return (relative, "relative", None)

    # From the view layer: selected_objects exists only in a screen's context, so under
    # --command it raises.
    selected = [blender_object for blender_object in bpy.context.view_layer.objects
                if blender_object.select_get() and object_service.object_is_basemesh(blender_object)]
    if len(selected) == 1:
        return (selected[0], "selection", None)
    candidates = selected or [blender_object for blender_object in bpy.data.objects
                              if object_service.object_is_basemesh(blender_object)]
    if len(candidates) == 1:
        return (candidates[0], "only_basemesh", None)
    if not candidates:
        return (None, None, (
            "basemesh_not_found",
            "'{:s}' has no MakeHuman basemesh among its relatives and this file holds none, so "
            "there is no body {:s}.".format(subject.name, purpose), []))
    return (None, None, (
        "basemesh_ambiguous",
        "'{:s}' has no basemesh among its relatives and {:d} could be meant, so {:s}. "
        "Pass 'basemesh' naming one of 'candidates'.".format(
            subject.name, len(candidates), not_done),
        sorted(blender_object.name for blender_object in candidates)))
