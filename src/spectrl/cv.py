"""CV accession ↔ integer-tail mapping for the spectrl wire format.

Rules (§3.1):
- Accession tails default to MS: ontology.
- Unit tails default to UO: ontology.
- Any other ontology uses an explicit [ontology_id, tail] pair.

The tail for "MS:1000511" is 1000511; for "UO:0000031" is 31.
"""

from __future__ import annotations

import re

from ._format import ARRAY_CHARGE as ARRAY_CHARGE
from ._format import ARRAY_INTENSITY as ARRAY_INTENSITY
from ._format import ARRAY_MZ as ARRAY_MZ
from ._format import ARRAY_NON_STANDARD as ARRAY_NON_STANDARD
from ._format import ION_MOBILITY_ARRAY_TAILS as _ION_MOBILITY_TAILS
from ._format import TYPE_FLOAT32 as TYPE_FLOAT32
from ._format import TYPE_FLOAT64 as TYPE_FLOAT64
from ._format import TYPE_INT32 as TYPE_INT32

_DEFAULT_PARAM_ONTOLOGY = "MS"
_DEFAULT_UNIT_ONTOLOGY = "UO"
# Largest tail that survives seven-digit zero-padded reconstruction (section 3).
_MAX_NUMERIC_TAIL = 9999999
_ACCESSION_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9]+")
_PREFIX_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def accession_tail(accession: str) -> int:
    """Extract the integer tail from an accession string like 'MS:1000511' → 1000511."""
    try:
        return int(accession.split(":", 1)[1])
    except (IndexError, ValueError):
        raise ValueError(
            f"accession {accession!r} has no integer tail; accessions with non-numeric tails "
            "are carried as full strings and cannot be tail-encoded."
        ) from None


def accession_ontology(accession: str) -> str:
    """Extract the ontology prefix from 'MS:1000511' → 'MS'."""
    return accession.split(":")[0]


def encode_unit(unit_accession: str) -> int | list | str:
    """Encode a unit accession: tail int (UO: default), [ontology, tail] for other
    ontologies, or the full accession string when the tail is not exactly 7 digits
    (tail encoding reconstructs with 7-digit zero-padding, so anything else would
    not round-trip, e.g. 'MOD:00046')."""
    onto = accession_ontology(unit_accession)
    tail_str = unit_accession.split(":", 1)[1] if ":" in unit_accession else ""
    if not (tail_str.isdigit() and len(tail_str) == 7):
        return unit_accession
    tail = int(tail_str)
    if onto == _DEFAULT_UNIT_ONTOLOGY:
        return tail
    return [onto, tail]


def decode_tail(tail: int, ontology: str = _DEFAULT_PARAM_ONTOLOGY) -> str:
    """Reconstruct an accession string from a tail integer and ontology prefix."""
    return f"{ontology}:{tail:07d}"


def _is_numeric_tail(value: object) -> bool:
    """True for a wire numeric tail: a CBOR integer (never a boolean) in 0..9999999."""
    return type(value) is int and 0 <= value <= _MAX_NUMERIC_TAIL


def decode_unit_tail(tail: int | list | str) -> str:
    """Reconstruct a unit accession string from its wire form (int = UO: default,
    list = [ontology, tail], str = full accession).

    The wire form is checked, not the ontology: spectrl never resolves a release
    or asserts that a term exists. What is rejected here is a value that is not
    one of the three shapes section 3 defines -- a boolean read as a tail, a
    pair with a trailing extra member, a tail outside 0..9999999 (which would
    not survive seven-digit reconstruction), or a string that is not an
    accession. Without this the decoder emits accessions its own encoder
    refuses, and disagrees with the TypeScript reader about token validity.
    """
    if isinstance(tail, str):
        if not _ACCESSION_RE.fullmatch(tail):
            raise ValueError(f"invalid CV unit accession {tail!r}")
        return tail
    if isinstance(tail, list):
        if len(tail) != 2 or not isinstance(tail[0], str) or not _PREFIX_RE.fullmatch(tail[0]):
            raise ValueError("a CV unit ontology pair must be [prefix, tail]")
        if not _is_numeric_tail(tail[1]):
            raise ValueError(f"CV unit tail must be an integer in 0..{_MAX_NUMERIC_TAIL}")
        return f"{tail[0]}:{tail[1]:07d}"
    if not _is_numeric_tail(tail):
        raise ValueError(f"CV unit tail must be an integer in 0..{_MAX_NUMERIC_TAIL}")
    return f"{_DEFAULT_UNIT_ONTOLOGY}:{tail:07d}"


# Ion mobility array tails
ION_MOBILITY_ARRAY_TAILS: dict[str, int] = {decode_tail(tail): tail for tail in _ION_MOBILITY_TAILS}
