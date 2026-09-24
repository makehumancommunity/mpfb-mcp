"""
The parameter contract, checked against the failures it exists to prevent.

Every case in the table below is one that fails *silently* without the check
being tested. That is the rule these rules were written under on mpfb-mcp's
side of the socket, and the reason they are duplicated here rather than trusted
to the caller: this socket is reachable by anything on the machine.

The table is the test. One list of (parameters, expectation) pairs read by one
loop, because twenty near-identical test functions would be twenty places for a
case to go missing and one place is enough.
"""

from .. import dynamic_import

_ACCEPTED = object()


def _specs():
    """A specification exercising every knob a Param has."""
    param = dynamic_import("validation", "Param")

    return (
        param("name", "string", required=True),
        param("limit", "integer", default=10, minimum=0, maximum=100),
        param("refresh", "boolean", default=False),
        param("weight", "number", minimum=-1.0, maximum=1.0, nullable=True),
        param("mode", "string", default="one", choices=("one", "two")),
        param("rows", "array", default=None, nullable=True),
        param("options", "object", default=None, nullable=True),
    )


# (params, expected) - _ACCEPTED, or a fragment the error message must contain.
# The fragment is checked rather than the whole sentence because the slug is the
# contract and the wording is not, but a message that fails to name the offending
# parameter is useless, so the parameter's name is always part of the fragment.
_CASES = (
    ({"name": "x"}, _ACCEPTED),
    ({}, "'name' is required"),
    ({"name": 1}, "'name' must be a string"),
    ({"name": None}, "'name' may not be null"),

    # bool is a subclass of int. Without the explicit exclusion, limit=True is
    # an integer and pages one entry at a time.
    ({"name": "x", "limit": True}, "'limit' must be an integer"),
    ({"name": "x", "limit": 1.5}, "'limit' must be an integer"),
    ({"name": "x", "limit": -1}, "'limit' must be at least 0"),
    ({"name": "x", "limit": 101}, "'limit' must be at most 100"),
    ({"name": "x", "limit": 0}, _ACCEPTED),
    ({"name": "x", "limit": 100}, _ACCEPTED),

    # "false" is a true value. Anything but a real bool must be refused, or
    # refresh="false" rescans the disk.
    ({"name": "x", "refresh": "false"}, "'refresh' must be a boolean"),
    ({"name": "x", "refresh": 0}, "'refresh' must be a boolean"),
    ({"name": "x", "refresh": True}, _ACCEPTED),

    ({"name": "x", "weight": -1.0}, _ACCEPTED),
    ({"name": "x", "weight": 1}, _ACCEPTED),
    ({"name": "x", "weight": 1.01}, "'weight' must be at most 1.0"),
    ({"name": "x", "weight": True}, "'weight' must be a number"),
    ({"name": "x", "weight": float("nan")}, "'weight' must be a finite number"),
    ({"name": "x", "weight": float("inf")}, "'weight' must be a finite number"),
    # Nullable, so an explicit null is a request rather than a mistake.
    ({"name": "x", "weight": None}, _ACCEPTED),

    ({"name": "x", "mode": "three"}, "'mode' must be one of"),
    ({"name": "x", "mode": "two"}, _ACCEPTED),

    ({"name": "x", "rows": {}}, "'rows' must be an array"),
    ({"name": "x", "rows": [1, 2]}, _ACCEPTED),
    ({"name": "x", "options": []}, "'options' must be an object"),
    ({"name": "x", "options": {"a": 1}}, _ACCEPTED),

    # The whole point of refusing rather than ignoring: a misspelling must fail
    # loudly instead of producing a call that succeeds and does nothing.
    ({"name": "x", "lmit": 5}, "Unknown parameter 'lmit'"),
    ({"name": "x", "code": "1 + 1"}, "Unknown parameter 'code'"),
)


def test_every_validation_case():
    """validation.validate_params()"""
    validate_params = dynamic_import("validation", "validate_params")
    invalid_params = dynamic_import("validation", "InvalidParams")
    specs = _specs()

    for params, expected in _CASES:
        try:
            validate_params(specs, params)
        except invalid_params as error:
            assert expected is not _ACCEPTED, \
                "{!r} should have been accepted but was refused: {:s}".format(params, str(error))
            assert expected in str(error), \
                "{!r} should have been refused with a message containing {!r}, got {!r}".format(
                    params, expected, str(error))
        else:
            assert expected is _ACCEPTED, \
                "{!r} should have been refused with {!r}, but was accepted".format(params, expected)


def test_defaults_are_filled_in_for_what_was_not_supplied():
    """validation.validate_params() defaulting"""
    # A handler must never have to ask whether an optional parameter is there.
    validate_params = dynamic_import("validation", "validate_params")
    validated = validate_params(_specs(), {"name": "x"})

    assert validated["limit"] == 10, "An omitted parameter should arrive as its declared default"
    assert validated["refresh"] is False, "A declared default of False should survive as False"
    assert validated["weight"] is None, "A parameter with no declared default should be None"
    assert validated["mode"] == "one", "A defaulted choice should arrive as that choice"
    assert sorted(validated) == ["limit", "mode", "name", "options", "refresh", "rows", "weight"], \
        "Every declared parameter should be present after validation, supplied or not"


def test_the_callers_dict_is_not_modified():
    """validation.validate_params() does not mutate its input"""
    # The dispatcher hands a handler the validated dict and keeps the request
    # around for logging. Filling defaults into the caller's dict would make the
    # two disagree about what was actually sent.
    validate_params = dynamic_import("validation", "validate_params")
    params = {"name": "x"}
    validate_params(_specs(), params)

    assert params == {"name": "x"}, "validate_params should not modify the dict it was given"


def test_a_parameter_describes_itself_as_json():
    """validation.Param.as_dict()"""
    # This is what `list_commands` hands out, so it has to be JSON and it has to
    # carry what a caller needs to construct a valid request.
    param = dynamic_import("validation", "Param")
    described = param("limit", "integer", default=10, minimum=0, maximum=100,
                      description="How many").as_dict()

    assert described["name"] == "limit", "A described parameter should name itself"
    assert described["type"] == "integer", "A described parameter should carry its JSON type"
    assert described["required"] is False, "A described parameter should say whether it is required"
    assert described["default"] == 10, "An optional parameter should report its default"
    assert described["minimum"] == 0 and described["maximum"] == 100, \
        "A bounded parameter should report both bounds"

    bare = param("name", "string", required=True).as_dict()
    assert "default" not in bare, "A required parameter has no meaningful default to report"
    assert "minimum" not in bare, "Bounds that were not declared should not be reported as null"


def test_an_unknown_type_is_refused_where_it_is_declared():
    """validation.Param() rejects an unknown type"""
    # A typo in a command's own specification is a bug in this add-on, not a bad
    # request, so it must fail at import rather than become an error envelope
    # the first time somebody calls that command.
    param = dynamic_import("validation", "Param")
    raised = False
    try:
        param("limit", "int")
    except ValueError:
        raised = True

    assert raised, "Declaring a parameter with an unknown type should raise where it is declared"
