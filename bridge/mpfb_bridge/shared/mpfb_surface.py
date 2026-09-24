"""
What MPFB does not publish as a service, read the one way it may be read.

**One implementation, imported by every command that reads past ``SERVICES``.**
See [`__init__.py`](__init__.py) for why this directory exists beside
``commands/``. MPFB keeps some of what the commands need at module level rather
than on a service: the ``BlenderConfigSet`` entities ``GeneralObjectProperties``
and ``HumanObjectProperties``, which are how custom properties such as
``object_type`` and ``asset_source`` are actually stored; the object type
vocabulary ``_MESH_ASSET_TYPES`` and ``_SKELETON_TYPES``; the ``Mhclo`` and
``MakeSkinMaterial`` entities; ``LOWEST_FUNCTIONAL_BLENDER_VERSION``; and
``FaceService``'s ``ARKIT_FACEUNITS`` and ``FACEUNIT_REGIONS``.

[architecture.md](../../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish)
sets three rules for reading them, and :func:`module_level` is where they live:

- **Through a service's module, never a fresh import.** ``sys.modules`` is
  necessarily populated for a service that resolved, and reading it re-executes
  nothing. Several MPFB submodules create directories when imported.
- **Always with a fallback.** These names are private or merely undocumented,
  and MPFB may rename one without notice. A renamed name degrades the answer; it
  does not fail the call.
- **From the service whose module actually imports the name.** This is the rule
  that fails silently, which is why it is worth a module: ``HumanObjectProperties``
  is on ``HumanService``'s module and *not* on ``ObjectService``'s, and a read
  from the wrong one takes the fallback, answers with less, and raises nothing.
  The two config sets, read by fifteen call sites between them, therefore have
  accessors of their own here - :func:`general_object_properties` and
  :func:`human_object_properties` - so the choice is made once. For every other
  name the caller names the service, at the call site where a reader can check
  it.

**One exception to the second rule, decided rather than inherited.** Four reads
of ``FaceService``'s vocabulary had no fallback, and a face command without it
has nothing it could answer: ``get_face_units`` reports the 52 units on every
answer, ``set_face_units`` validates against them, and the divergence check
compares them. A made-up fallback would be a stale copy of MPFB's vocabulary
presented as MPFB's. So :func:`required_module_level` raises
:class:`MissingFromMpfb`, which the dispatcher turns into a ``command_failed``
envelope naming what is missing - the outcome those four reads always had, with
a sentence instead of an ``AttributeError``
([FR 036](../../../feature-requests/done/036-subject-resolver-and-duplication/README.md)).

Two helpers go with it, because they are how a value read off that surface gets
into an answer. :func:`property_value` turns an unset ``BlenderConfigSet``
string, which reads back as ``""``, into ``None``, so that two commands cannot
report ``""`` and ``None`` for the same object. :func:`as_path` turns the
``pathlib.Path`` MPFB's path getters have been caught returning into a ``str``,
since one ``Path`` in a response fails the whole call with
``result_not_serializable``.

Like the rest of this directory, the functions that read MPFB take ``services``
first; the two helpers take the value they coerce.
"""

__all__ = (
    "MissingFromMpfb",
    "as_path",
    "general_object_properties",
    "human_object_properties",
    "module_level",
    "property_value",
    "required_module_level",
)

import sys


class MissingFromMpfb(RuntimeError):
    """A name a command cannot answer without is not where MPFB used to keep it."""


def _module_of(services, service_name):
    return sys.modules[services[service_name].__module__]


def module_level(services, service_name, name, *, fallback):
    """``name`` off the module ``services[service_name]`` was defined in, or ``fallback``.

    ``fallback`` has no default so that every call site says what it degrades
    to, which is the second rule written where a reader of the command sees it.
    """
    return getattr(_module_of(services, service_name), name, fallback)


def general_object_properties(services):
    """MPFB's ``GeneralObjectProperties``, which objectservice.py imports, or ``None``."""
    return module_level(services, "ObjectService", "GeneralObjectProperties", fallback=None)


def human_object_properties(services):
    """MPFB's ``HumanObjectProperties``, or ``None``.

    On humanservice.py's module, and **not** on objectservice.py's, which is the
    read that would take the fallback silently if it were made from the wrong one.
    """
    return module_level(services, "HumanService", "HumanObjectProperties", fallback=None)


def required_module_level(services, service_name, name):
    """``name`` off the service's module, or :class:`MissingFromMpfb` saying which.

    Only for a name without which the command has nothing to answer. Everything
    else goes through :func:`module_level` and degrades.
    """
    module = _module_of(services, service_name)
    if not hasattr(module, name):
        raise MissingFromMpfb(
            "MPFB's {:s} module ({:s}) no longer defines {:s}, and this command cannot answer "
            "without it. The installed MPFB is probably newer than this add-on; check "
            "mpfb_get_status and upgrade the MPFB Bridge.".format(
                service_name, module.__name__, name))
    return getattr(module, name)


def property_value(config_set, property_name, blender_object):
    """One ``BlenderConfigSet`` string property, or ``None`` when it was never set.

    ``config_set`` may itself be ``None``, since it was read with a fallback. An
    unset string property reads back as ``""``, which means "nothing was
    recorded" and must not be reported as a fragment.
    """
    if config_set is None or blender_object is None:
        return None
    try:
        value = config_set.get_value(property_name, entity_reference=blender_object)
    except Exception:  # pylint: disable=broad-except
        return None
    if not value:
        return None
    return str(value)


def as_path(path):
    """A path as a ``str``, coerced at the point it enters an answer, or ``None``.

    MPFB's path getters are annotated as returning ``str``, but
    ``LocationService.get_mpfb_root()`` hands back a ``pathlib.Path`` when called
    with no sub-path, and several ``AssetService`` helpers do too (commit
    631989c).
    """
    if not path:
        return None
    return str(path)
