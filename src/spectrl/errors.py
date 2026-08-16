"""spectrl exception types."""


class SpectrlError(Exception):
    """Base class for all spectrl errors."""


class SpectrlDecodeError(SpectrlError, ValueError):
    """A token could not be decoded: malformed, corrupted, or unsupported.

    Subclasses ValueError so callers following the original documented contract
    (``except ValueError``) keep working.
    """
