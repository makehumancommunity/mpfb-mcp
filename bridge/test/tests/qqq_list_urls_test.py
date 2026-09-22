"""
``list_urls`` against a real MPFB: the third command that does not need one.

**A flat module rather than one under ``ppp_mutating/``, and the placement is
the point.** FR 032 migrated fourteen tools; thirteen of them change a `.blend`
and live in that directory. This one is read-only and belongs out here with the
other read-only commands, which is also why its ``requires_mpfb`` is ``False``:
"where do I download MPFB" is asked most often by somebody whose MPFB is not
working.

Two claims live here:

- **MPFB's ``ui.weburls`` is read out of ``sys.modules`` and never imported.**
  Being an add-on makes importing it possible for the first time, so this
  asserts what is actually true of the module after a read: that it is the
  object that was already loaded, and that a Blender where it is *not* loaded is
  a successful answer with a reason rather than an import.
- **Enumeration is by prefix**, so a ``URL_`` constant MPFB adds later appears
  without a change to this add-on - and a ``URL_`` name holding something that
  is not a string is reported under ``skipped_keys`` rather than dropped.

The merge against mpfb-mcp's vendored table is **not** checked here, because it
does not happen here: it runs on the client, in all four states including the
one where this add-on is unreachable. ``tests/test_list_urls.py`` is where that
is tested.
"""

import sys

import pytest

from . import bridge_module
from ._fixtures import dispatch
from ._fixtures import result as _fixture_result
from ._fixtures import services_or_skip as _services_or_skip
from ._fixtures import supplied_resolution


def _result(params=None):
    return _fixture_result("list_urls", params)


def _weburls_module_name(services):
    """``<root>.ui.weburls`` for whatever MPFB is installed here."""
    root = services["ObjectService"].__module__.split(".services.")[0]
    return root + ".ui.weburls"


def test_the_live_addresses_are_read_out_of_mpfbs_own_module():
    """commands.list_urls against a running MPFB"""
    services = _services_or_skip()
    module_name = _weburls_module_name(services)
    if module_name not in sys.modules:
        pytest.skip("this MPFB did not import its UI, so there is nothing live to read")

    result = _result()

    assert result["state"] == "ok"
    assert result["weburls_read"] is True
    assert result["weburls_module"] == module_name
    assert result["reason"] is None
    assert result["urls"], "a real MPFB ships a dozen URL_ constants"
    for key, value in result["urls"].items():
        assert key.startswith("URL_"), "enumeration is by prefix, got {!r}".format(key)
        assert isinstance(value, str)
    assert result["package"], "the package name is part of the answer"


def test_the_values_are_mpfbs_own_and_nothing_was_imported():
    """commands.list_urls reads the module that was already loaded

    The rule the command's docstring restates now that importing is possible:
    reading ``sys.modules`` re-executes nothing, and an import would run MPFB
    code inside a Blender that may already be broken.
    """
    services = _services_or_skip()
    module_name = _weburls_module_name(services)
    if module_name not in sys.modules:
        pytest.skip("this MPFB did not import its UI, so there is nothing live to read")

    loaded = sys.modules[module_name]
    result = _result()

    for key, value in result["urls"].items():
        assert getattr(loaded, key) == value, \
            "{!r} should be the value on the module that was already loaded".format(key)


def test_a_url_constant_that_is_not_a_string_is_reported_rather_than_dropped():
    """commands.list_urls over a module carrying a non-string URL_ name

    An absent entry has to be explainable, so the skip is named.
    """
    services = _services_or_skip()
    module_name = _weburls_module_name(services)
    if module_name not in sys.modules:
        pytest.skip("this MPFB did not import its UI, so there is nothing live to read")

    loaded = sys.modules[module_name]
    setattr(loaded, "URL_NOT_A_STRING", 17)
    try:
        result = _result()

        assert "URL_NOT_A_STRING" in result["skipped_keys"]
        assert "URL_NOT_A_STRING" not in result["urls"]
    finally:
        delattr(loaded, "URL_NOT_A_STRING")


def test_a_url_constant_mpfb_adds_later_needs_no_change_here():
    """commands.list_urls over a module carrying a constant this add-on never heard of"""
    services = _services_or_skip()
    module_name = _weburls_module_name(services)
    if module_name not in sys.modules:
        pytest.skip("this MPFB did not import its UI, so there is nothing live to read")

    loaded = sys.modules[module_name]
    setattr(loaded, "URL_INVENTED_BY_A_TEST", "https://example.invalid/new")
    try:
        result = _result()

        assert result["urls"]["URL_INVENTED_BY_A_TEST"] == "https://example.invalid/new"
    finally:
        delattr(loaded, "URL_INVENTED_BY_A_TEST")


def test_mpfb_being_absent_is_a_successful_answer():
    """commands.list_urls against a Blender with no MPFB at all

    The state this command exists for. ``requires_mpfb=False`` is what keeps the
    dispatcher from refusing before the handler runs.
    """
    with supplied_resolution("absent"):
        envelope = dispatch("list_urls")

    assert envelope["status"] == "ok", \
        "a missing MPFB is the case this command is most useful in: {!r}".format(envelope)
    result = envelope["result"]
    assert result["state"] == "absent"
    assert result["weburls_read"] is False
    assert result["urls"] is None, "there is nothing live to report"
    assert result["reason"], "and the client needs to know why, to say so in its answer"
    assert "vendored copy" in result["reason"]


def test_mpfb_being_half_registered_is_also_a_successful_answer():
    """commands.list_urls against an MPFB that did not finish initializing"""
    with supplied_resolution("not_initialized"):
        envelope = dispatch("list_urls")

    assert envelope["status"] == "ok"
    assert envelope["result"]["state"] == "not_initialized"
    assert envelope["result"]["weburls_read"] is False
    assert envelope["result"]["reason"]


def test_the_command_takes_no_parameters_at_all():
    """commands.list_urls with a parameter it does not accept"""
    _services_or_skip()
    envelope = dispatch("list_urls", {"refresh": True})

    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params", \
        "a misspelled key that is quietly dropped is a call that succeeds and does the wrong " \
        "thing: {!r}".format(envelope)


def test_the_table_declares_this_command_as_not_needing_mpfb():
    """commands.table: requires_mpfb is False for exactly three commands

    Asserted against the table rather than inferred from behaviour, because the
    flag is what the dispatcher reads and what ``list_commands`` hands out.
    """
    commands = bridge_module("commands").COMMANDS

    assert commands["list_urls"].requires_mpfb is False
    without_mpfb = sorted(name for name, command in commands.items()
                          if not command.requires_mpfb)
    assert without_mpfb == ["get_mpfb_status", "get_status", "list_commands", "list_urls"], \
        "the set of commands that answer without MPFB should change deliberately, got " \
        "{!r}".format(without_mpfb)
