"""
The shape of a tool's arguments, checked before anything is sent.

Every rule here is one [validate before crossing the socket](../../specifications/tool-interface.md#validate-before-crossing-the-socket)
states, and each exists because the alternative fails silently: ``True`` is an
``int``, ``"false"`` is a true value, and an empty string is not the same
mistake as an omitted argument. They were written once per tool until
[FR 036](../../feature-requests/done/036-subject-resolver-and-duplication/README.md),
eighteen times for a subject name and sixteen for a flag, and are written once
here now. A module beside ``tools/`` rather than inside it, since a module in
``tools/`` is a tool and has a ``register()``.

**The rule is shared; the wording a tool owns is passed at its call site.** The
refusal sentences are the ones the copies gave, word for word, and where a tool
said something of its own - which asset it means and why the name is required,
what an empty filter should have been instead - that phrase is an argument, so
a reader of the tool can see it without opening this file. Why truthiness would
do harm *for a given flag* is a comment at that flag's call site, where it is
true.

**An argument a tool does not declare is refused**, by ``refuse_undeclared()``.
It is the one rule here no tool calls: FastMCP drops an unknown key before the
tool function runs, so the check is made once for every tool, by the server
``build_server()`` builds, against the arguments as they arrived.
``RETIRED_ARGUMENTS`` is what makes a rename safe - a caller still using the old
spelling is told the new one, rather than getting the default the old spelling
used to override
([FR 037](../../feature-requests/done/037-one-word-per-concept/README.md)).

**Shape only, never vocabulary.** Whether a name is an object, a section a
section, or a fragment a file is answered inside Blender. The two narrow
exceptions, ``skin_type`` and ``meta_rig_action``, are checked by their own
tools, since each is one tool's vocabulary.

Nothing here imports anything from this package, so a tool importing it cannot
pull in the wire or the record.
"""

from __future__ import annotations

__all__ = (
    "MODES",
    "RETIRED_ARGUMENTS",
    "refuse_undeclared",
    "validated_asset_name",
    "validated_count",
    "validated_flag",
    "validated_mode",
    "validated_subject",
    "validated_text",
)


def validated_subject(value: object, argument: str = "name") -> str | None:
    """The optional name of the object a tool is about; ``None`` means the active one.

    An explicitly empty name is refused rather than read as "use the active
    object": the two come from different mistakes, and quietly answering about
    whatever happens to be selected, when the caller believed they had named
    something, is worse than failing here. ``argument`` is the argument's name
    in the refusal, which is ``name`` in every tool today.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("{:s} must be a string or omitted, got {!r}".format(argument, value))
    if not value.strip():
        raise ValueError(
            "{:s} must not be empty or whitespace; omit it to use the active object".format(
                argument))
    return value


def validated_asset_name(value: object, what: str, because: str) -> str:
    """The required ``name`` of an equipped asset, which is never the active object.

    Three tools act on one asset object and will not guess it. ``what`` names the
    asset in that tool's terms, and ``because`` is the tool's own sentence on why
    the name is required.
    """
    if not isinstance(value, str):
        raise ValueError("name must be a string, got {!r}".format(value))
    if not value.strip():
        raise ValueError(
            "name must be the Blender object name of {:s}, as mpfb_list_objects or "
            "mpfb_add_asset reports it. {:s}".format(what, because))
    return value


def validated_flag(value: object, argument: str) -> bool:
    """A real ``bool``, not merely a truthy value.

    ``"false"`` and ``0`` are how a caller signals a bool it did not manage to
    build, and ``"false"`` is a true value.
    """
    if not isinstance(value, bool):
        raise ValueError("{:s} must be a bool, got {!r}".format(argument, value))
    return value


def validated_count(value: object, argument: str, maximum: int | None = None) -> int:
    """A non-negative ``int`` that is not a ``bool``, and at most ``maximum``."""
    if isinstance(value, bool) or not isinstance(value, int):
        # bool is a subclass of int, so `limit=True` would otherwise page one
        # entry at a time rather than fail.
        raise ValueError("{:s} must be an int, got {!r}".format(argument, value))
    if value < 0:
        raise ValueError("{:s} must not be negative, got {!r}".format(argument, value))
    if maximum is not None and value > maximum:
        raise ValueError("{:s} must be at most {}, got {!r}".format(argument, maximum, value))
    return value


# Adding to what is there, or making it exactly this. This package's own
# vocabulary, not MPFB's - no MPFB function sees it - so it is a shape like any
# other and cannot drift. Two tools offer the choice (FR 037, R6), which is why
# it is here rather than in either of them.
MODES = ("merge", "replace")


def validated_mode(value: object) -> str:
    """``"merge"`` or ``"replace"``; there is no reading of an unknown one that is safe to guess."""
    if value not in MODES:
        raise ValueError("mode must be one of {}, got {!r}".format(", ".join(MODES), value))
    return value  # type: ignore[return-value]

def validated_text(value: object, argument: str, hint: str) -> str | None:
    """Optional non-empty text, returned as given; ``hint`` says what to do instead.

    An explicitly empty value and an omitted one arise from different mistakes,
    so the empty one is never quietly treated as the omission - which matters
    most where "omitted" means something, such as half of an exactly-one-of rule.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("{:s} must be a string or omitted, got {!r}".format(argument, value))
    if not value.strip():
        raise ValueError("{:s} must not be empty or whitespace; {:s}".format(argument, hint))
    return value


# A spelling a tool no longer takes, per tool, and the one that replaced it.
# Per tool rather than one set: a spelling retired from one tool can still be
# declared by another, where it means something else. An entry stays for as long
# as a caller might still send the old spelling, which in a proof of concept with
# no released users is until nobody remembers it.
RETIRED_ARGUMENTS: dict[str, dict[str, str]] = {
    # FR 037, R1: `name` is the object a tool operates on. The file became
    # `preset_name`/`expression_name`, and the character, which was `subject`,
    # became `name` - so in the save tools `name` changed meaning rather than
    # being retired, and the command's subject_not_found sentence covers it.
    "mpfb_create_human_from_preset": {
        "name": "preset_name",
        # R7: the glossary over MPFB's spelling. MPFB's settings keep theirs,
        # and settings_used reports them as MPFB read them.
        "material_instances": "material_instances_policy",
        "override_clothes_model": "override_clothes_material_type",
        "override_eyes_model": "override_eyes_material_type",
        "override_skin_model": "override_skin_type",
    },
    # R2: the argument names an object that does not exist yet, as a basename
    # Rigify may uniquify; rig_object_name reports what it became.
    "mpfb_generate_rigify_rig": {"rig_name": "generated_rig_name"},
    # R6: MPFB's type string is object_type everywhere, as the catalogue
    # reports it, rather than add_mhclo_asset()'s own name for it.
    "mpfb_add_asset": {"asset_type": "object_type"},
    # R6: adding versus replacing is `mode` in both tools that offer the choice.
    "mpfb_set_face_units": {"clear_first": "mode"},
    "mpfb_save_expression": {"subject": "name"},
    "mpfb_save_preset": {"subject": "name"},
}


def refuse_undeclared(tool: str, declared: object, supplied: object) -> None:
    """Refuse any argument in ``supplied`` that ``tool``'s signature does not declare.

    Worded as the bridge words an unknown parameter, and for the same reason: a
    misspelled ``topc`` that is quietly dropped is a call that succeeds with the
    default instead, which is the hardest failure there is to see from the caller's
    side. A spelling in ``RETIRED_ARGUMENTS`` is named with what it became.
    """
    accepted = sorted(declared)
    unknown = sorted(key for key in supplied if key not in accepted)
    if not unknown:
        return
    retired = RETIRED_ARGUMENTS.get(tool, {})
    raise ValueError("Unknown argument{:s} {:s}. This tool accepts {:s}.".format(
        "" if len(unknown) == 1 else "s",
        ", ".join(
            "{!r} (now called {!r})".format(key, retired[key]) if key in retired
            else repr(key)
            for key in unknown),
        ", ".join(accepted) if accepted else "no arguments"))
