"""
Finding the add-on under test, which is not as simple as importing it.

Blender's extension format forbids absolute imports and prefixes the package name
with whichever repository the extension was installed into, so the add-on is
``bl_ext.user_default.mpfb_bridge`` on one machine and ``bl_ext.somerepo.mpfb_bridge``
on another. A test therefore cannot say ``import mpfb_bridge``.

This is the same problem MPFB solves in ``mpfb2/test/tests/__init__.py`` and it is
solved the same way, deliberately: scan ``sys.modules`` for the module whose name
ends in the package name, and hand the leaf tests something already resolved.
"""

__all__ = (
    "dynamic_import",
    "bridge_package",
)

import importlib
import sys

_PACKAGE_SUFFIX = "mpfb_bridge"


def bridge_package():
    """The loaded ``mpfb_bridge`` package, whatever it is called here."""
    for name in sys.modules:
        if name.endswith(_PACKAGE_SUFFIX):
            return importlib.import_module(name)
    raise ValueError(
        "No loaded module name ends in '{:s}'. The MPFB Bridge add-on must be installed and "
        "enabled in this Blender for these tests to run.".format(_PACKAGE_SUFFIX))


def dynamic_import(relative_module, key):
    """One name out of one of the add-on's submodules, resolved by suffix."""
    package = bridge_package()
    module = importlib.import_module("{:s}.{:s}".format(package.__name__, relative_module))
    if not hasattr(module, key):
        raise AttributeError("Module {:s} does not have attribute {:s}".format(module.__name__, key))
    return getattr(module, key)
