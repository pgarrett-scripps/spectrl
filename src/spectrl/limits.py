"""Optional application budgets, separate from the wire format's hard limits."""

from dataclasses import dataclass, fields

from ._format import MAGIC, MAX_ARRAY_LENGTH, MAX_SAFE_INTEGER, MAX_TOKEN_BYTES


@dataclass(frozen=True)
class DecodeLimits:
    """Budgets for one decode call, applied before array decompression.

    Token bytes include the ASCII framing and checksum. Decoded bytes count
    the sum of output array lengths times their declared element sizes. They
    do not bound metadata, temporary buffers, process memory, or CPU time.
    Zero is allowed. The format's hard ceilings still apply.
    """

    max_token_bytes: int = (MAX_TOKEN_BYTES * 4 + 2) // 3 + len(MAGIC) + 10
    max_peaks: int = MAX_ARRAY_LENGTH
    max_arrays: int = 64
    max_decoded_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER:
                raise ValueError(f"{field.name} must be a nonnegative safe integer")
