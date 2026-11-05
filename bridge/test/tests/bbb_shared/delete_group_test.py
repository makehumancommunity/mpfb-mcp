"""
``shared/delete_group.py`` called directly, on meshes whose answers are known.

**A tube around a cylinder**, one end open, because everything the algorithm claims can be read
off it as arithmetic: a band of visible skin at the opening, full coverage beyond it, a collar of a
known number of rings. What a real character does is ``ddd_mutating/generate_delete_group_test.py``'s,
and the gi is the request's own live check.

The claims this module is for:

- **A loop is an opening only if it reaches skin and sees air**, the two questions the spike added.
- **A limb through it is what makes a cuff or a hem**, and a loop nothing passes through is neither.
- **The conservative rule is MPFB's**, held against its private function so that drift is noticed.
- **A turn changes nothing**, and a pose does, which is what the command's refusal rests on.
"""

import math

import bmesh
import bpy
import numpy
import pytest

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import rigged_character
from .._fixtures import services_or_skip

RADIUS = 0.1
RINGS = 60
SEGMENTS = 24
BODY_LOW = 0.0
BODY_HIGH = 1.2
TUBE_TOP = 1.0
GAP = 0.02


def _module():
    return bridge_module("shared.delete_group")


def _margins():
    return dict(_module().DEFAULT_MARGINS)


def _lathe(name, radius, low, high, rings, cap_low=True, cap_high=True):
    """A closed or open cylinder around Z, its faces outward, linked to the current scene."""
    mesh = bpy.data.meshes.new(name)
    builder = bmesh.new()
    rows = []
    for ring in range(rings + 1):
        height = low + (high - low) * ring / rings
        rows.append([builder.verts.new((radius * math.cos(2.0 * math.pi * step / SEGMENTS),
                                        radius * math.sin(2.0 * math.pi * step / SEGMENTS), height))
                     for step in range(SEGMENTS)])
    for below, above in zip(rows, rows[1:]):
        for step in range(SEGMENTS):
            following = (step + 1) % SEGMENTS
            builder.faces.new((below[step], below[following], above[following], above[step]))
    if cap_low:
        builder.faces.new(list(reversed(rows[0])))
    if cap_high:
        builder.faces.new(rows[-1])
    builder.to_mesh(mesh)
    builder.free()
    blender_object = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(blender_object)
    return blender_object


@pytest.fixture(name="made")
def _made():
    """What a test built, removed however it ends."""
    built = []
    yield built
    for blender_object in built:
        mesh = blender_object.data
        bpy.data.objects.remove(blender_object, do_unlink=True)
        bpy.data.meshes.remove(mesh)


def _body_and_tube(made, tube_radius=RADIUS + GAP):
    """A capped body, all skin, in a tube closed at the bottom and open at ``TUBE_TOP``."""
    body = _lathe("delete_group_body", RADIUS, BODY_LOW, BODY_HIGH, RINGS)
    body.vertex_groups.new(name="body").add(list(range(len(body.data.vertices))), 1.0, "REPLACE")
    tube = _lathe("delete_group_tube", tube_radius, BODY_LOW - 0.02, TUBE_TOP, RINGS, cap_high=False)
    made.extend((body, tube))
    bpy.context.view_layer.update()
    return (body, tube)


def _read(body, garment):
    reading, refusal = _module().read(body, garment)
    assert refusal is None, refusal
    return reading


def _no_members(reading):
    return numpy.zeros(len(reading.points), dtype=bool)


def _ring_of(point):
    """Which of the body's rings a vertex is on, counted from the bottom."""
    return int(round((point[2] - BODY_LOW) / (BODY_HIGH - BODY_LOW) * RINGS))


# ----------------------------------------------------------------------------
# Generating
# ----------------------------------------------------------------------------


def test_a_tube_covers_what_is_far_from_its_opening_and_leaves_a_band_at_it(made):
    reading = _read(*_body_and_tube(made))
    members, openings = _module().generate(reading, _no_members(reading), _margins())
    assert [opening.kind for opening in openings] == [_module().KIND_TRUNK]
    heights = reading.points[members][:, 2]
    assert heights.max() < TUBE_TOP, "skin above the opening is not under anything"
    well_below = reading.is_skin & (reading.points[:, 2] < TUBE_TOP - 0.3)
    side = well_below & (reading.points[:, 2] > BODY_LOW + 0.01)
    assert members[side].all(), "beyond what can be seen everything under the tube is covered"
    assert not members[(reading.points[:, 2] > TUBE_TOP - 0.05) & reading.is_skin].any(), (
        "skin just inside the opening can be seen, so it stays")


def test_the_collar_is_as_wide_as_the_constant_says(made, monkeypatch):
    reading = _read(*_body_and_tube(made))
    module = _module()
    monkeypatch.setattr(module, "_HOLE_FILL_PASSES", 0)
    monkeypatch.setattr(module, "_COLLAR_RINGS", 0)
    bare, _openings = module.generate(reading, _no_members(reading), _margins())
    monkeypatch.setattr(module, "_COLLAR_RINGS", 3)
    collared, _openings = module.generate(reading, _no_members(reading), _margins())
    assert (_ring_of((0.0, 0.0, reading.points[bare][:, 2].max()))
            - _ring_of((0.0, 0.0, reading.points[collared][:, 2].max()))) == 3


def test_a_vertex_a_margin_keeps_still_grows_a_collar(made, monkeypatch):
    # The margin covers everything that can be seen. Left untested, those vertices grew no collar,
    # and on the gi that opened black wedges on the chest beside the lapel.
    reading = _read(*_body_and_tube(made))
    module = _module()
    margins = dict(_margins(), trunk=0.06)
    monkeypatch.setattr(module, "_HOLE_FILL_PASSES", 0)
    monkeypatch.setattr(module, "_COLLAR_RINGS", 0)
    bare, _openings = module.generate(reading, _no_members(reading), margins)
    monkeypatch.setattr(module, "_COLLAR_RINGS", 3)
    collared, _openings = module.generate(reading, _no_members(reading), margins)
    assert reading.points[collared][:, 2].max() < reading.points[bare][:, 2].max()


def test_a_margin_keeps_skin_a_sight_line_would_not(made):
    reading = _read(*_body_and_tube(made))
    module = _module()
    wide = dict(_margins(), trunk=0.5)
    members, openings = module.generate(reading, _no_members(reading), wide)
    assert reading.points[members][:, 2].max() <= TUBE_TOP - 0.5
    assert openings[0].margin == 0.5
    assert openings[0].kept_by_margin > 0


def test_members_given_stay_and_only_skin_is_added(made):
    body, tube = _body_and_tube(made)
    body.vertex_groups.new(name="helper").add([0], 1.0, "REPLACE")
    skin = body.vertex_groups["body"]
    skin.remove([5])
    reading = _read(body, tube)
    base = _no_members(reading)
    top = len(reading.points) - 1
    base[top] = True
    members, _openings = _module().generate(reading, base, _margins())
    assert members[top], "a member from before stays, even where it is not under anything"
    assert not members[5], "a vertex that is not skin is never added"


def test_a_single_vertex_hole_is_filled_and_one_in_a_collar_is_not():
    module = _module()
    reading = module.Reading()
    # Vertex 2 is surrounded by covered vertices; vertex 4 too, but it is in a collar.
    reading.neighbours = [[1], [0, 2], [1, 3], [2, 4], [3], ]
    reading.is_skin = numpy.ones(5, dtype=bool)
    base = numpy.zeros(5, dtype=bool)
    under = numpy.array((True, True, False, True, False))
    filled = module._filled(reading, base, under, {4})  # pylint: disable=protected-access
    assert filled.tolist() == [True, True, True, True, False]


def test_a_closed_shell_has_no_openings_and_is_sight_tested_anyway(made):
    body, _tube = _body_and_tube(made)
    shell = _lathe("delete_group_shell", RADIUS + GAP, BODY_LOW - 0.02, TUBE_TOP, RINGS, cap_high=True)
    made.append(shell)
    bpy.context.view_layer.update()
    reading = _read(body, shell)
    assert reading.closed_component_sizes == [len(shell.data.vertices)]
    members, openings = _module().generate(reading, _no_members(reading), _margins())
    assert openings == []
    assert members.sum() > 0, "what the shell covers and nothing can see is hidden"


def test_the_same_mesh_gives_the_same_group(made):
    reading = _read(*_body_and_tube(made))
    first, _openings = _module().generate(reading, _no_members(reading), _margins())
    second, _openings = _module().generate(reading, _no_members(reading), _margins())
    assert (first == second).all()


def test_modifiers_are_read_around_and_put_back(made):
    body, tube = _body_and_tube(made)
    plain = _read(body, tube)
    subdivision = tube.modifiers.new("Subdivision", "SUBSURF")
    subdivision.levels = 2
    already_off = body.modifiers.new("Off", "MASK")
    already_off.show_viewport = False
    body_mask = body.modifiers.new("Hide helpers", "MASK")
    body_mask.vertex_group = "body"
    bpy.context.view_layer.update()
    reading = _read(body, tube)
    assert len(reading.garment_points) == len(plain.garment_points), "the stripped mesh"
    assert len(reading.points) == len(plain.points), "a group's indices are the mesh's"
    assert subdivision.show_viewport is True
    assert body_mask.show_viewport is True
    assert already_off.show_viewport is False, "one that was off stays off"


def test_a_modifier_that_changes_the_body_vertex_count_is_refused(made):
    body, tube = _body_and_tube(made)
    body.modifiers.new("Solid", "SOLIDIFY")
    bpy.context.view_layer.update()
    reading, refusal = _module().read(body, tube)
    assert reading is None
    assert refusal[0] == "body_topology_changed"


# ----------------------------------------------------------------------------
# Openings
# ----------------------------------------------------------------------------


def test_boundary_loops_are_found_and_an_ngon_has_no_inner_boundary():
    module = _module()
    # A square of two triangles has four boundary edges and one loop.
    edges = module.boundary_edges(numpy.array(((0, 1, 2), (0, 2, 3))))
    assert sorted(edges.tolist()) == [[0, 1], [0, 3], [1, 2], [2, 3]]
    loops = module.boundary_loops(edges)
    assert len(loops) == 1 and sorted(loops[0]) == [0, 1, 2, 3]
    assert len(module.boundary_loops(numpy.empty((0, 2), dtype=numpy.int64))) == 0


def _ring(radius, height, count=16):
    return numpy.array([(radius * math.cos(2.0 * math.pi * step / count),
                         radius * math.sin(2.0 * math.pi * step / count), height)
                        for step in range(count)])


def _arm_joints(start, end):
    return {"joint-l-shoulder": numpy.array(start), "joint-l-elbow": numpy.array(end)}


def test_a_limb_through_a_loop_is_found_and_one_beside_it_is_not():
    module = _module()
    through = _arm_joints((0.0, 0.0, 1.0), (0.0, 0.0, -1.0))
    assert module.limbs_through(_ring(0.1, 0.0), through) == ["left arm"]
    beside = _arm_joints((0.5, 0.0, 1.0), (0.5, 0.0, -1.0))
    assert module.limbs_through(_ring(0.1, 0.0), beside) == []
    short = _arm_joints((0.0, 0.0, 1.0), (0.0, 0.0, 0.5))
    assert module.limbs_through(_ring(0.1, 0.0), short) == [], "it ends before the loop's plane"


def test_a_limb_through_it_makes_a_cuff_or_a_hem(made):
    body, tube = _body_and_tube(made)
    reading = _read(body, tube)
    for joint, name, kind, margin_key in (("joint-l-shoulder", "joint-l-elbow", "cuff", "cuff"),
                                          ("joint-r-upper-leg", "joint-r-knee", "hem", "hem")):
        reading.joints = {joint: numpy.array((0.0, 0.0, BODY_HIGH)),
                          name: numpy.array((0.0, 0.0, BODY_LOW))}
        openings = _module().openings_of(reading, _margins())
        assert [opening.kind for opening in openings] == [kind]
        assert openings[0].margin == _margins()[margin_key]
        assert "passes through" in openings[0].reason


def test_a_loop_with_another_layer_between_it_and_the_skin_is_covered(made):
    body, outer = _body_and_tube(made, tube_radius=RADIUS + 3.0 * GAP)
    inner_and_outer = bmesh.new()
    inner_and_outer.from_mesh(outer.data)
    # An inner layer, closed and taller, between the outer tube's rim and the skin.
    inner = _lathe("delete_group_inner", RADIUS + GAP, BODY_LOW - 0.02, BODY_HIGH + 0.05, RINGS)
    made.append(inner)
    inner_and_outer.from_mesh(inner.data)
    inner_and_outer.to_mesh(outer.data)
    inner_and_outer.free()
    bpy.context.view_layer.update()
    reading = _read(body, outer)
    openings = _module().openings_of(reading, _margins())
    assert [opening.kind for opening in openings] == [_module().KIND_COVERED]
    assert "between" in openings[0].reason
    assert len(openings[0].edges) == 0, "and so it sets no margin and no sight zone"


def test_a_loop_under_another_layer_is_covered(made):
    body, inner = _body_and_tube(made)
    both = bmesh.new()
    both.from_mesh(inner.data)
    # An outer layer, closed and longer, over the inner tube's rim.
    outer = _lathe("delete_group_outer", RADIUS + 3.0 * GAP, BODY_LOW - 0.02, BODY_HIGH + 0.05, RINGS)
    made.append(outer)
    both.from_mesh(outer.data)
    both.to_mesh(inner.data)
    both.free()
    bpy.context.view_layer.update()
    openings = _module().openings_of(_read(body, inner), _margins())
    assert [opening.kind for opening in openings] == [_module().KIND_COVERED]
    assert "covers" in openings[0].reason


def test_distance_to_segments_is_arithmetic():
    module = _module()
    segments = numpy.array((((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),))
    points = numpy.array(((0.5, 2.0, 0.0), (-3.0, 0.0, 0.0), (4.0, 0.0, 0.0)))
    assert module.distance_to_segments(points, segments).tolist() == pytest.approx([2.0, 3.0, 3.0])
    assert (module.distance_to_segments(points, numpy.empty((0, 2, 3))) == numpy.inf).all()


# ----------------------------------------------------------------------------
# Measuring
# ----------------------------------------------------------------------------


def test_the_measures_stand_at_either_extreme(made):
    reading = _read(*_body_and_tube(made))
    module = _module()
    good, openings = module.generate(reading, _no_members(reading), _margins())
    empty_slits, empty_under, empty_here = module.measure(reading, _no_members(reading), openings)
    assert empty_slits == 0 and empty_here == 0, "nothing removed, so nothing removed can be seen"
    assert empty_under > 0, "and everything under the tube stands"

    everything = reading.is_skin.copy()
    all_slits, _all_under, all_here = module.measure(reading, everything, openings)
    assert all_slits > 0 and all_here > 0, "skin at the opening is removed and can be seen"

    good_slits, good_under, good_here = module.measure(reading, good, openings)
    assert good_slits == 0 and good_here == 0
    assert good_under < empty_under


def test_a_slit_only_this_bodys_mask_would_open_is_counted_as_that(made):
    # Members up to the ring below a seen one: its faces are removed here, where any face touching
    # a member goes, and stand once loaded, where a partly covered face's members go first.
    reading = _read(*_body_and_tube(made))
    module = _module()
    _good, openings = module.generate(reading, _no_members(reading), _margins())
    members = reading.is_skin & (reading.points[:, 2] <= TUBE_TOP - 0.04) & (
        reading.points[:, 2] > BODY_LOW + 0.01)
    slits, _under, here = module.measure(reading, members, openings)
    assert here > slits


def test_skin_in_front_of_the_garment_is_not_a_slit(made):
    # The garment inside the body, so all of the skin has poked through and sees air, and
    # removing it shows the garment. On the gi this was most of what sight lines alone counted.
    body, tube = _body_and_tube(made, tube_radius=RADIUS - GAP)
    reading = _read(body, tube)
    openings = _module().openings_of(reading, _margins())
    measured = _module().measure(reading, reading.is_skin.copy(), openings)
    assert measured[0] == 0 and measured[2] == 0


def test_the_conservative_rule_is_mpfbs_with_a_written_files_duplicates():
    # What Mhclo.load() hands it: each run of consecutive indices with its first index twice. A
    # written file going onto a real character is ddd_mutating/generate_delete_group_test.py's.
    services = services_or_skip()
    module = _module()
    with Character() as character:
        # The Character removes this with itself, being new when it ends.
        tube = _lathe("delete_group_any", 1.0, 0.0, 1.0, 2)
        reading = _read(character.basemesh, tube)
        generator = numpy.random.default_rng(51)
        skin = numpy.flatnonzero(reading.is_skin)
        patch = numpy.flatnonzero(reading.is_skin & (numpy.linalg.norm(
            reading.points - reading.points[skin[1000]], axis=1) < 0.08))
        for chosen in (patch, generator.choice(skin, 300, replace=False)):
            members = numpy.zeros(len(reading.points), dtype=bool)
            members[chosen] = True
            theirs = []
            for vertex in sorted(int(vertex) for vertex in chosen):
                if vertex == 0 or not members[vertex - 1]:
                    theirs.append(vertex)
                theirs.append(vertex)
            # pylint: disable=protected-access
            services["ClothesService"]._conservative_mask(character.basemesh, theirs)
            assert numpy.flatnonzero(module.as_loaded(reading, members)).tolist() == sorted(set(theirs))


# ----------------------------------------------------------------------------
# The frame
# ----------------------------------------------------------------------------


def test_a_turned_and_moved_character_gets_the_same_group(made):
    body, tube = _body_and_tube(made)
    module = _module()
    reading = _read(body, tube)
    still, _openings = module.generate(reading, _no_members(reading), _margins())
    tube.parent = body
    body.rotation_euler = (0.0, 0.0, 1.1)
    body.location = (2.0, -1.0, 0.5)
    bpy.context.view_layer.update()
    turned_reading = _read(body, tube)
    assert turned_reading.points == pytest.approx(reading.points, abs=1e-5)
    turned, openings = module.generate(turned_reading, _no_members(turned_reading), _margins())
    assert (still == turned).all()
    # The centre reported is where it is in the world, which is where a caller would look.
    assert openings[0].centre[0] != pytest.approx(0.0, abs=0.5)


def test_a_posed_character_gets_a_different_group():
    # What the command's rig_not_at_rest rests on. The request asked for this to be provoked
    # rather than assumed from FR 050, where a pose was baked into a file.
    services = services_or_skip()
    module = _module()
    with Character() as character:
        rig = rigged_character(services, character, "default")
        garment = _lathe("delete_group_skirt", 0.25, 0.3, 1.0, 40)
        try:
            bpy.context.view_layer.update()
            rest = _read(character.basemesh, garment)
            at_rest, _openings = module.generate(rest, _no_members(rest), _margins())
            bone = rig.pose.bones["upperleg01.L"]
            bone.rotation_mode = "XYZ"
            bone.rotation_euler = (1.2, 0.0, 0.0)
            bpy.context.view_layer.update()
            posed = _read(character.basemesh, garment)
            when_posed, _openings = module.generate(posed, _no_members(posed), _margins())
            assert (at_rest != when_posed).sum() > 10
        finally:
            mesh = garment.data
            bpy.data.objects.remove(garment, do_unlink=True)
            bpy.data.meshes.remove(mesh)
