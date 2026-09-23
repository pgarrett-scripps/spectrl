"""Application budgets applied by default, separate from the wire format's hard limits."""

from dataclasses import dataclass, fields, replace

from ._format import MAGIC, MAX_ARRAY_LENGTH, MAX_CBOR_ITEMS, MAX_SAFE_INTEGER, MAX_TOKEN_BYTES

# Longest token the wire format can express: base64url of a 16 MiB payload plus
# framing. This is a ceiling, not a budget.
MAX_TOKEN_CHARS = (MAX_TOKEN_BYTES * 4 + 2) // 3 + len(MAGIC) + 10


@dataclass(frozen=True)
class DecodeLimits:
    """Budgets for one decode call, applied before array decompression.

    Token bytes include the ASCII framing and checksum. Decoded bytes count
    the sum of output array lengths times their declared element sizes. They
    do not bound metadata, temporary buffers, process memory, or CPU time.
    Zero is allowed. The format's hard ceilings still apply.

    The defaults are on. A token usually arrives from a URL or a message, and
    the wire ceilings alone permit a 21 kB token to expand into 128 MB of
    arrays. The values below sit roughly an order of magnitude above the
    largest spectrum in the reference corpus (217,009 peaks, a 1.05 MB token),
    so ordinary data is unaffected. Pass :meth:`unlimited` for a trusted
    producer, or a custom instance for anything in between.
    """

    max_token_bytes: int = 4 * 1024 * 1024
    max_peaks: int = 1_000_000
    max_arrays: int = 64
    max_decoded_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER:
                raise ValueError(f"{field.name} must be a nonnegative safe integer")

    @classmethod
    def unlimited(cls) -> "DecodeLimits":
        """Budgets raised to the format's hard ceilings, for a trusted producer."""
        return cls(
            max_token_bytes=MAX_TOKEN_CHARS,
            max_peaks=MAX_ARRAY_LENGTH,
            max_arrays=MAX_CBOR_ITEMS,
            max_decoded_bytes=MAX_ARRAY_LENGTH * 8 * MAX_CBOR_ITEMS,
        )

    def replace(self, **changes: int) -> "DecodeLimits":
        """Return a copy with individual budgets overridden."""
        return replace(self, **changes)


DEFAULT_DECODE_LIMITS = DecodeLimits()


def resolve_limits(limits: "DecodeLimits | None") -> "DecodeLimits":
    """Apply the safe defaults when a caller supplies none."""
    if limits is None:
        return DEFAULT_DECODE_LIMITS
    if not isinstance(limits, DecodeLimits):
        raise TypeError("limits must be a DecodeLimits instance")
    return limits
