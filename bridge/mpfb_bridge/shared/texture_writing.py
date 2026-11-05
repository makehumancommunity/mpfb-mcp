"""
Getting a texture to a destination without touching where it came from.

**This replaces MPFB's ``check_that_all_textures_are_saved()``, on purpose.** That
function calls ``image.save()`` on every texture, and so re-encodes each source
file in place: it took the gi's diffuse map from 2.5 to 3.2 MB and its normal map
from 17.0 to 18.2 MB, with nothing saying so. A file somebody generated, or keeps
under version control, should not change because a material was stored. So:

- **An image with a file and nothing unsaved is copied byte for byte.** Its source
  is opened for reading and that is all.
- **An image with unsaved changes, or no file, or packed pixels** is written with
  ``image.save(filepath=..., save_copy=True)``, which leaves the image's own path,
  format and dirty flag alone.

``export_to_disk()`` is then pointed at the copy, finds its source and its
destination equal and copies nothing. The panel's docstring warns only that images
are saved "alongside the MHMAT file", so this follows
[its stated intent](../../../specifications/mpfb-integration.md#where-a-service-falls-short-of-what-its-own-code-says-it-does-follow-the-stated-intent).

**Everything is decided before anything is written.** :func:`plan` opens nothing
for writing, which is what lets ``dry_run`` be an honest answer, and what lets a
texture that has no pixels to give be a refusal before a directory exists.

**Written to a directory beside the destination, then moved.** A failure half way
through a set of textures then leaves no half of a material: :func:`staging`
removes what it made however it ends. The move is ``os.replace``, which is atomic
on one filesystem and why the staging directory is a sibling and not a temporary
directory somewhere else.

Takes no ``services``: this is plain Blender and plain files. Shared with
[FR 050](../../../feature-requests/done/050-writing-mesh-assets/README.md), which writes
a garment's own material the same way.
"""

__all__ = (
    "COPIED",
    "ALREADY_IN_PLACE",
    "SAVED_FROM_BLENDER",
    "IMAGE_EXTENSIONS",
    "TexturePlan",
    "has_pixels",
    "image_file_path",
    "is_in_sync_with_its_file",
    "made_directories",
    "move_into_place",
    "plan",
    "reload_stale_images",
    "remove_directories",
    "staging",
    "write_staged",
)

import contextlib
import os
import shutil
import tempfile

import bpy

COPIED = "copied"
SAVED_FROM_BLENDER = "saved_from_blender"
ALREADY_IN_PLACE = "already_in_place"

# What a path argument may end in. Every format Blender both reads and can save,
# in the spellings MPFB's assets use. mpfbmcp's set_makeskin_material tool carries
# a copy, which its test module holds to this one by reading this as data.
IMAGE_EXTENSIONS = (".bmp", ".exr", ".hdr", ".jpeg", ".jpg", ".png", ".tga", ".tif", ".tiff",
                    ".webp")

# Which extension an image with no file of its own is saved under.
_EXTENSION_OF_FORMAT = {
    "BMP": ".bmp",
    "HDR": ".hdr",
    "JPEG": ".jpg",
    "OPEN_EXR": ".exr",
    "OPEN_EXR_MULTILAYER": ".exr",
    "PNG": ".png",
    "TARGA": ".tga",
    "TARGA_RAW": ".tga",
    "TIFF": ".tif",
    "WEBP": ".webp",
}

# A movie, an image sequence, UDIM tiles and the viewer are not one file's worth
# of pixels, and an MHMAT names one file.
_STORABLE_SOURCES = ("FILE", "GENERATED")


def image_file_path(image):
    """The absolute, normalised path an image was loaded from or will save to, or ``None``."""
    if image is None or not image.filepath:
        return None
    return os.path.normpath(bpy.path.abspath(image.filepath, library=image.library))


def has_pixels(image):
    """Whether Blender can read pixels from this image.

    ``size`` first, since asking it is what makes Blender load them: ``has_data``
    alone reads false on a good image nothing has looked at yet, and an image of
    no size is what ``images.load()`` returns for a file it could not decode.
    """
    return image.size[0] > 0 and image.has_data


def is_in_sync_with_its_file(image):
    """Whether the file on disk holds exactly what this image holds, as far as Blender knows.

    Packed pixels count as out of step even with a file beside them: nothing says
    the two are the same, and a packed image is what renders.
    """
    path = image_file_path(image)
    return (path is not None and os.path.isfile(path) and image.source == "FILE"
            and not image.is_dirty and image.packed_file is None)


class TexturePlan:
    """One texture's way to its destination, or why it has none.

    ``how`` is :data:`COPIED`, :data:`SAVED_FROM_BLENDER` or
    :data:`ALREADY_IN_PLACE`; ``refusal`` is a sentence when there is no way, and
    the rest of the plan is then meaningless.
    """

    __slots__ = ("slot", "image", "image_name", "source_path", "how", "filename", "destination",
                 "refusal")

    def __init__(self, slot, image):
        self.slot = slot
        self.image = image
        self.image_name = None if image is None else str(image.name)
        self.source_path = None
        self.how = None
        self.filename = None
        self.destination = None
        self.refusal = None


def _extension_for(image, path):
    extension = os.path.splitext(path)[1] if path else ""
    if extension:
        return extension
    return _EXTENSION_OF_FORMAT.get(str(image.file_format))


def plan(slot, image, directory, base_name):
    """How ``image`` reaches ``<directory>/<base_name>_<slot>.<ext>``. Writes nothing."""
    planned = TexturePlan(slot, image)
    if image is None:
        planned.refusal = "The {:s} image node holds no image.".format(slot)
        return planned
    if image.source not in _STORABLE_SOURCES:
        planned.refusal = ("'{:s}' is a {:s} image, which is not one file's worth of pixels, so "
                           "an MHMAT cannot name it.".format(planned.image_name, str(image.source)))
        return planned

    path = image_file_path(image)
    planned.source_path = path
    extension = _extension_for(image, path)
    if extension is None:
        planned.refusal = ("'{:s}' has no file, and its format {!s} is not one this can choose an "
                           "extension for. Set its file format in Blender.".format(
                               planned.image_name, image.file_format))
        return planned
    planned.filename = "{:s}_{:s}{:s}".format(base_name, slot, extension)
    planned.destination = os.path.normpath(os.path.join(directory, planned.filename))

    if is_in_sync_with_its_file(image):
        planned.how = ALREADY_IN_PLACE if path == planned.destination else COPIED
        return planned
    if not has_pixels(image):
        planned.refusal = (
            "'{:s}' has no pixels Blender can read{:s}, so there is nothing to store.".format(
                planned.image_name,
                "" if path is None else ": its file '{:s}' does not exist or cannot be read".format(
                    path)))
        return planned
    planned.how = SAVED_FROM_BLENDER
    return planned


@contextlib.contextmanager
def staging(beside):
    """A directory next to ``beside``, removed however the block ends."""
    directory = tempfile.mkdtemp(prefix=".mpfb-bridge-", dir=beside)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def write_staged(planned, directory):
    """Write one planned texture into ``directory``, returning the file, or ``None`` if none is due."""
    if planned.how == ALREADY_IN_PLACE:
        return None
    target = os.path.join(directory, planned.filename)
    if planned.how == COPIED:
        # copyfile rather than MPFB's shutil.copy: the bytes are the point, and a
        # read-only source should not produce a read-only asset.
        shutil.copyfile(planned.source_path, target)
    else:
        planned.image.save(filepath=target, save_copy=True)
    return target


def move_into_place(staged_file, directory):
    """Move one staged file into ``directory``, replacing what is there, and return its path."""
    target = os.path.join(directory, os.path.basename(staged_file))
    os.replace(staged_file, target)
    return target


def reload_stale_images(plans):
    """MPFB reuses a loaded image by basename, so a replaced file must reach the loaded one.

    Returns a sentence for each image of a written file's name that it could not bring
    in step.
    """
    warnings = []
    for planned in plans:
        image = bpy.data.images.get(planned.filename)
        if image is None or image == planned.image:
            continue
        if image_file_path(image) == planned.destination and not image.is_dirty:
            image.reload()
        else:
            warnings.append(
                "An image named '{:s}' is already loaded from elsewhere, and MPFB reuses a loaded "
                "image by name, so applying this material in this session shows that image's "
                "pixels.".format(planned.filename))
    return warnings


def made_directories(path):
    """``os.makedirs(path)``, returning each directory it had to make, outermost first."""
    missing = []
    current = os.path.normpath(path)
    while not os.path.exists(current):
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    os.makedirs(path, exist_ok=True)
    return list(reversed(missing))


def remove_directories(directories):
    """Remove directories :func:`made_directories` made, innermost first, if they are empty."""
    for directory in reversed(directories):
        try:
            os.rmdir(directory)
        except OSError:
            return
