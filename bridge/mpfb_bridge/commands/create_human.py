"""
``create_human``: MPFB's ``HumanService.create_human()``, and nothing else.

The smallest command in the table and the first **mutating** one, which makes it
where the conventions the other twelve inherit get settled rather than where
anything interesting happens. Three of them, all visible in the last four lines:

- **The answer is stamped with ``performed``**, from
  [`shared/performed.py`](../shared/performed.py), which is the uniform flag a
  caller branches on whatever tool it called. Every mutating command keeps its
  own verb beside it; this one has none, because creation either returns a
  basemesh or raises.
- **The verb argument is written at the call site**, not guessed from the
  answer. Here it is the literal ``True``, and the comment above it says why
  that is safe rather than leaving a reader to work it out.
- **The before/after report is what the payload's was**: the object's name, its
  vertex count, its location and the macro dict that was applied. Blender
  uniquifies a name that is already taken, so ``object_name`` is read off the
  created object and is the address every later command needs.

**This reproduces ``codegen/payloads/create_human.py`` rather than tidying it
up**, including its silences. ``create_human()``'s own defaults are used for
``mask_helpers``, ``detailed_helpers``, ``extra_vertex_groups`` and
``feet_on_ground``; none is exposed, here or on the generated path.

**One asymmetry with the rest of this table, and it is deliberate.** The eleven
macro sliders are 0.0-1.0, and that rule is enforced on *mpfb-mcp's* side of the
socket rather than in :data:`PARAMS` below. The reason is that
``macro_detail_dict`` arrives as MPFB's own nested shape - eight numbers and a
``race`` sub-object - and a :class:`..validation.Param` constrains one value,
not the inside of one. Adding a nested check here would be a behaviour this
command has and the payload it is replacing does not, which is exactly what
[FR 032](../../../feature-requests/032-creation-and-modification-migrated/README.md)
forbids during a migration: a tidy-up is indistinguishable from a defect in the
comparison the migration rests on. It is written down here rather than left to
be rediscovered, and if the nested contract should be declared rather than
trusted, that is a line in NEXT_STEPS.md and not a change folded into this one.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "create_human",
)

from ..log import get_logger
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_NUMBER
from ..validation import TYPE_OBJECT

_LOG = get_logger("commands.createhuman")

# create_human()'s own default scale (0.1 = decimeters). Spelled out rather than
# left to MPFB so that the declared default and the one a caller gets are the
# same number whatever MPFB does next.
_DEFAULT_SCALE = 0.1

PARAMS = (
    Param("macro_detail_dict", TYPE_OBJECT, default=None, nullable=True,
          description="The phenotype, in MPFB's own nested shape: gender, age, muscle, weight, "
                      "proportions, height, cupsize and firmness as 0.0-1.0 numbers, plus a "
                      "'race' object of asian/caucasian/african weights. Omit or pass null for "
                      "create_human()'s own defaults."),
    Param("scale", TYPE_NUMBER, default=_DEFAULT_SCALE,
          description="Basemesh scale factor. 0.1 = decimeters, which is MPFB's own default and "
                      "what its enhanced skin types read to pick subsurface radii."),
)

SUMMARY = "Create a new MakeHuman character - a basemesh with a phenotype."


def create_human(params, resolution):
    """Build one character, and report what was built."""
    human_service = resolution.services["HumanService"]

    macro_detail_dict = params["macro_detail_dict"]
    basemesh = human_service.create_human(
        scale=params["scale"],
        macro_detail_dict=macro_detail_dict,
    )

    _LOG.debug("create_human: built %r with %d vertices",
               basemesh.name, len(basemesh.data.vertices))

    result = dict(
        object_name=basemesh.name,
        vertex_count=len(basemesh.data.vertices),
        location=list(basemesh.location),
        macro_detail_dict=macro_detail_dict,
    )

    # Nothing here can succeed by halves: create_human() either returns a
    # basemesh or raises, and a raise becomes a `command_failed` envelope rather
    # than this dict. See shared/performed.py.
    return with_performed(result, True)
