"""
``shared/texture_writing.py``: a source is never changed.

Proved by hash and modification time, with a real file, a dirty image and an unsaved one,
because the function it replaces took a real diffuse map from 2.5 to 3.2 MB without a word.
"""

import hashlib
import os

import bpy
import pytest

from .. import bridge_module
from .._fixtures import write_png


def _module():
    return bridge_module("shared.texture_writing")


def _digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


@pytest.fixture(name="loaded")
def _loaded(tmp_path):
    path = write_png(str(tmp_path / "source.png"), (1.0, 0.0, 0.0, 1.0))
    image = bpy.data.images.load(path, check_existing=False)
    yield (image, path)
    bpy.data.images.remove(image)


def test_a_clean_image_is_copied_byte_for_byte(loaded, tmp_path):
    texture_writing = _module()
    image, path = loaded
    digest = _digest(path)
    mtime = os.stat(path).st_mtime_ns
    out = tmp_path / "out"
    out.mkdir()
    planned = texture_writing.plan("diffuse", image, str(out), "belt")
    assert planned.refusal is None
    assert planned.how == texture_writing.COPIED
    assert planned.source_path == path
    assert planned.filename == "belt_diffuse.png"
    staged = texture_writing.write_staged(planned, str(out))
    assert _digest(staged) == digest
    assert _digest(path) == digest and os.stat(path).st_mtime_ns == mtime
    assert not image.is_dirty and bpy.path.abspath(image.filepath) == path


def test_a_dirty_image_is_saved_as_a_copy_and_stays_dirty(loaded, tmp_path):
    texture_writing = _module()
    image, path = loaded
    digest = _digest(path)
    image.pixels[0] = 0.0
    assert image.is_dirty
    out = tmp_path / "out"
    out.mkdir()
    planned = texture_writing.plan("diffuse", image, str(out), "belt")
    assert planned.how == texture_writing.SAVED_FROM_BLENDER
    staged = texture_writing.write_staged(planned, str(out))
    assert os.path.isfile(staged)
    assert _digest(path) == digest
    assert image.is_dirty and bpy.path.abspath(image.filepath) == path
    reread = bpy.data.images.load(staged, check_existing=False)
    try:
        assert reread.pixels[0] == pytest.approx(0.0)
    finally:
        bpy.data.images.remove(reread)


def test_an_unsaved_image_takes_its_extension_from_its_format(tmp_path):
    texture_writing = _module()
    image = bpy.data.images.new("bridge_test_unsaved", 4, 4)
    try:
        planned = texture_writing.plan("normalmap", image, str(tmp_path), "belt")
        assert planned.how == texture_writing.SAVED_FROM_BLENDER
        assert planned.source_path is None
        assert planned.filename == "belt_normalmap.png"
        staged = texture_writing.write_staged(planned, str(tmp_path))
        assert os.path.isfile(staged)
        assert image.filepath == "" and image.source == "GENERATED"
    finally:
        bpy.data.images.remove(image)


def test_a_packed_image_is_saved_rather_than_copied_from_a_file_it_may_not_match(loaded, tmp_path):
    texture_writing = _module()
    image, _path = loaded
    image.pack()
    planned = texture_writing.plan("diffuse", image, str(tmp_path), "belt")
    assert planned.how == texture_writing.SAVED_FROM_BLENDER
    image.unpack(method="REMOVE")


def test_an_image_already_at_its_destination_writes_nothing(loaded, tmp_path):
    texture_writing = _module()
    image, _path = loaded
    target = tmp_path / "belt_diffuse.png"
    os.rename(image.filepath, target)
    image.filepath = str(target)
    planned = texture_writing.plan("diffuse", image, str(tmp_path), "belt")
    assert planned.how == texture_writing.ALREADY_IN_PLACE
    assert texture_writing.write_staged(planned, str(tmp_path)) is None


def test_nothing_to_store_is_a_refusal(tmp_path):
    texture_writing = _module()
    assert "no image" in texture_writing.plan("diffuse", None, str(tmp_path), "b").refusal
    image = bpy.data.images.load(write_png(str(tmp_path / "gone.png")), check_existing=False)
    try:
        os.remove(image.filepath)
        image.reload()
        planned = texture_writing.plan("diffuse", image, str(tmp_path), "b")
        assert "no pixels" in planned.refusal
    finally:
        bpy.data.images.remove(image)


def test_an_image_that_is_not_one_file_is_refused(tmp_path):
    texture_writing = _module()
    image = bpy.data.images.new("bridge_test_tiled", 4, 4, tiled=True)
    try:
        planned = texture_writing.plan("diffuse", image, str(tmp_path), "b")
        assert "not one file" in planned.refusal
    finally:
        bpy.data.images.remove(image)


def test_staging_is_beside_and_goes_away(tmp_path):
    texture_writing = _module()
    with texture_writing.staging(str(tmp_path)) as directory:
        assert os.path.dirname(directory) == str(tmp_path)
        (tmp_path / os.path.basename(directory) / "x").write_text("x")
    assert os.listdir(str(tmp_path)) == []
    with pytest.raises(ValueError):
        with texture_writing.staging(str(tmp_path)):
            raise ValueError("provoked")
    assert os.listdir(str(tmp_path)) == []


def test_directories_it_made_are_the_ones_it_removes(tmp_path):
    texture_writing = _module()
    (tmp_path / "there").mkdir()
    made = texture_writing.made_directories(str(tmp_path / "there" / "a" / "b"))
    assert made == [str(tmp_path / "there" / "a"), str(tmp_path / "there" / "a" / "b")]
    texture_writing.remove_directories(made)
    assert os.listdir(str(tmp_path / "there")) == []
