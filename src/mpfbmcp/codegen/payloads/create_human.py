"""
Payload for ``mpfb_create_human``: MPFB's ``HumanService.create_human()``.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag two names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``scale`` and
  ``macro_detail_dict``.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.

Uses ``create_human()``'s own defaults for ``mask_helpers``,
``detailed_helpers``, ``extra_vertex_groups`` and ``feet_on_ground``; only
``scale`` and ``macro_detail_dict`` are parameterized.
"""

HumanService = _MPFB_SERVICES["HumanService"]

basemesh = HumanService.create_human(
    scale=PARAMS["scale"],
    macro_detail_dict=PARAMS["macro_detail_dict"],
)

result = {
    "object_name": basemesh.name,
    "vertex_count": len(basemesh.data.vertices),
    "location": list(basemesh.location),
    "macro_detail_dict": PARAMS["macro_detail_dict"],
}
