"""
What a command takes, declared as data, and the checks that enforce it.

A command's parameters are a tuple of :class:`Param` records rather than
something each handler picks apart for itself. Three things follow from that,
and the third is the one worth the module.

**A handler that runs has already been given parameters of the right shape.** No
handler begins with twenty lines of ``isinstance``; none of them phrases the same
error twenty different ways; and a missing optional parameter arrives as its
declared default rather than as a ``KeyError`` waiting to happen.

**The rules are the ones mpfb-mcp already applies on its side of the socket**,
and they are duplicated deliberately rather than by oversight. A listening socket
is reachable by anything on this machine, not only by mpfb-mcp, so the add-on
cannot assume its caller already checked. Each rule below exists because the
alternative fails *silently*:

- ``True`` is an ``int`` in Python, so an integer check that does not exclude
  ``bool`` accepts ``limit=True`` and pages one entry at a time.
- ``"false"`` is a true value, so a boolean check that accepts anything truthy
  turns ``refresh="false"`` into a disk rescan.
- A number outside its range is not refused by MPFB. Its macro properties carry
  a default but no ``min``/``max``, and the clamping a user gets from a slider
  comes from a scene-level proxy property that neither this add-on nor an MCP
  tool
  alike go nowhere near.

**An unknown key is an error, not something to ignore.** A misspelled
``catagory`` that is quietly dropped produces a call that succeeds and does
nothing, which is the most expensive kind of failure to diagnose from the far
side of a socket. Note the asymmetry with the request *envelope*, which does
tolerate unknown keys: the envelope belongs to the protocol and is versioned, so
a client may carry a key this bridge has not heard of, while ``params`` belongs
to one command whose contract is declared right here.

``bpy`` is not imported here and must not be. This module is ordinary Python over
ordinary data, and being readable without a running Blender is most of its value.
"""

__all__ = (
    "TYPE_STRING",
    "TYPE_INTEGER",
    "TYPE_NUMBER",
    "TYPE_BOOLEAN",
    "TYPE_ARRAY",
    "TYPE_OBJECT",
    "KNOWN_TYPES",
    "InvalidParams",
    "Param",
    "is_number",
    "validate_params",
)

import math

TYPE_STRING = "string"
TYPE_INTEGER = "integer"
TYPE_NUMBER = "number"
TYPE_BOOLEAN = "boolean"
TYPE_ARRAY = "array"
TYPE_OBJECT = "object"

# The names are JSON Schema's rather than Python's, because a specification
# leaves this add-on over the wire - `list_commands` reports it - and the reader
# on the other end is describing JSON, not Python.
KNOWN_TYPES = (
    TYPE_STRING,
    TYPE_INTEGER,
    TYPE_NUMBER,
    TYPE_BOOLEAN,
    TYPE_ARRAY,
    TYPE_OBJECT,
)

# What each type is called in a sentence addressed to whoever sent the request.
_TYPE_ARTICLES = {
    TYPE_STRING: "a string",
    TYPE_INTEGER: "an integer",
    TYPE_NUMBER: "a number",
    TYPE_BOOLEAN: "a boolean",
    TYPE_ARRAY: "an array",
    TYPE_OBJECT: "an object",
}


class InvalidParams(ValueError):
    """One parameter is wrong, and the message says which one and why.

    Raised by :func:`validate_params` and turned into an ``invalid_params``
    envelope by the dispatcher. It is a plain exception carrying a sentence
    rather than a structured report because the envelope's contract is a slug
    plus a human sentence: a caller branches on the slug, and reads the sentence.
    """


class Param:  # pylint: disable=too-many-instance-attributes
    """One parameter a command accepts.

    Nine fields, which is two past what pylint likes. Every one of them is a
    thing some command genuinely needs to declare, and the alternative - nesting
    the bounds and the choices inside a sub-object - would make the declarations
    at the top of each command module harder to read to satisfy a counter.

    The fields beyond ``name`` and ``value_type`` are all optional and all
    narrowing. ``required`` and ``default`` are mutually exclusive in practice -
    a required parameter's default is never reached - and a parameter that is
    neither required nor given arrives as ``default``, which is ``None`` unless
    something else was declared.

    ``nullable`` is separate from ``default`` on purpose. "Not mentioned" and
    "explicitly null" are different requests: mpfb-mcp's ``mpfb_set_macro_details``
    defaults every slider to ``None`` precisely so that omitting one means *leave
    it alone* rather than *set it to the middle*, and a parameter whose absence
    means one thing and whose ``null`` means another needs both knobs.
    """

    __slots__ = (
        "name",
        "value_type",
        "required",
        "default",
        "nullable",
        "minimum",
        "maximum",
        "choices",
        "description",
    )

    def __init__(self, name, value_type, required=False, default=None, nullable=False,
                 minimum=None, maximum=None, choices=None, description=""):
        if value_type not in KNOWN_TYPES:
            # A programming error in this add-on rather than a bad request, so it
            # raises where it is declared instead of becoming an error envelope.
            raise ValueError("Unknown parameter type {!r} for parameter {!r}. Known types: "
                             "{:s}".format(value_type, name, ", ".join(KNOWN_TYPES)))
        self.name = name
        self.value_type = value_type
        self.required = required
        self.default = default
        self.nullable = nullable
        self.minimum = minimum
        self.maximum = maximum
        self.choices = tuple(choices) if choices is not None else None
        self.description = description

    def as_dict(self):
        """This parameter as the JSON ``list_commands`` hands out.

        Keys whose value would be ``None`` are omitted rather than reported as
        null, so a caller reading the specification sees what is declared rather
        than a uniform shape mostly filled with nothing.
        """
        described = {
            "name": self.name,
            "type": self.value_type,
            "required": self.required,
        }
        if not self.required:
            described["default"] = self.default
        if self.nullable:
            described["nullable"] = True
        if self.minimum is not None:
            described["minimum"] = self.minimum
        if self.maximum is not None:
            described["maximum"] = self.maximum
        if self.choices is not None:
            described["choices"] = list(self.choices)
        if self.description:
            described["description"] = self.description
        return described


def _type_matches(value, value_type):
    """Whether one value is of one declared type, with Python's traps closed."""
    if value_type == TYPE_BOOLEAN:
        # Strictly a bool. Truthiness is not the question and never was.
        return isinstance(value, bool)
    if value_type == TYPE_INTEGER:
        # bool is a subclass of int, so the second half is the whole point.
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == TYPE_NUMBER:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        # NaN and the infinities survive `json.loads` and compare false against
        # every bound, so a range check alone would let them through.
        return math.isfinite(value)
    if value_type == TYPE_STRING:
        return isinstance(value, str)
    if value_type == TYPE_ARRAY:
        return isinstance(value, list)
    return isinstance(value, dict)


def is_number(value):
    """A finite ``int`` or ``float`` that is not a ``bool``: what ``TYPE_NUMBER`` accepts.

    Public for the batched commands, whose entries are objects inside one array
    parameter and so are checked by the command rather than by
    :func:`validate_params`; one rule, so that an entry and a parameter cannot
    disagree about whether ``true`` or ``NaN`` is a number.
    """
    return _type_matches(value, TYPE_NUMBER)


def _describe(value):
    """A value's type, named the way the sender would recognise it."""
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, int):
        return "an integer"
    if isinstance(value, float):
        return "a number"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, list):
        return "an array"
    if isinstance(value, dict):
        return "an object"
    if value is None:
        return "null"
    return "a {:s}".format(type(value).__name__)


def _check_one(spec, value):
    """Check one supplied value against one specification, or raise."""
    if value is None:
        if spec.nullable:
            return None
        raise InvalidParams(
            "Parameter {!r} may not be null; it must be {:s}.".format(
                spec.name, _TYPE_ARTICLES[spec.value_type]))

    if not _type_matches(value, spec.value_type):
        if spec.value_type == TYPE_NUMBER and isinstance(value, float):
            # Reached only by NaN and the infinities, which json.loads produces
            # happily and which compare false against every bound - so "must be
            # a number, got a number" is what the generic message would say.
            raise InvalidParams(
                "Parameter {!r} must be a finite number, got {}.".format(spec.name, value))
        raise InvalidParams(
            "Parameter {!r} must be {:s}, got {:s}.".format(
                spec.name, _TYPE_ARTICLES[spec.value_type], _describe(value)))

    if spec.minimum is not None and value < spec.minimum:
        raise InvalidParams(
            "Parameter {!r} must be at least {}, got {}.".format(spec.name, spec.minimum, value))

    if spec.maximum is not None and value > spec.maximum:
        raise InvalidParams(
            "Parameter {!r} must be at most {}, got {}.".format(spec.name, spec.maximum, value))

    if spec.choices is not None and value not in spec.choices:
        raise InvalidParams(
            "Parameter {!r} must be one of {:s}, got {!r}.".format(
                spec.name, ", ".join(repr(choice) for choice in spec.choices), value))

    return value


def validate_params(specs, params):
    """Check ``params`` against ``specs`` and return them with defaults filled in.

    Raises :class:`InvalidParams` naming the offending parameter. Returns a new
    dict; the caller's is not modified, and a handler therefore cannot be handed
    a dict something else still holds a reference to.
    """
    by_name = {spec.name: spec for spec in specs}

    unknown = sorted(key for key in params if key not in by_name)
    if unknown:
        raise InvalidParams(
            "Unknown parameter{:s} {:s}. This command accepts {:s}.".format(
                "" if len(unknown) == 1 else "s",
                ", ".join(repr(key) for key in unknown),
                ", ".join(sorted(by_name)) if by_name else "no parameters"))

    validated = {}
    for spec in specs:
        if spec.name not in params:
            if spec.required:
                raise InvalidParams(
                    "Parameter {!r} is required and was not supplied.".format(spec.name))
            validated[spec.name] = spec.default
            continue
        validated[spec.name] = _check_one(spec, params[spec.name])

    return validated
