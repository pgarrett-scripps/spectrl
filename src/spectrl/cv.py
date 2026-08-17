"""CV accession ↔ integer-tail mapping for the spectrl wire format.

Rules (§3.1):
- Accession tails default to MS: ontology.
- Unit tails default to UO: ontology.
- Any other ontology uses an explicit [ontology_id, tail] pair.

The tail for "MS:1000511" is 1000511; for "UO:0000031" is 31.
"""

from __future__ import annotations

from ._format import ARRAY_CHARGE as ARRAY_CHARGE
from ._format import ARRAY_INTENSITY as ARRAY_INTENSITY
from ._format import ARRAY_MZ as ARRAY_MZ
from ._format import ARRAY_NON_STANDARD as ARRAY_NON_STANDARD
from ._format import COMP_BYTE_SHUFFLED_ZSTD as COMP_BYTE_SHUFFLED_ZSTD
from ._format import COMP_NUMLIN_ZLIB as COMP_NUMLIN_ZLIB
from ._format import COMP_NUMLIN_ZSTD as COMP_NUMLIN_ZSTD
from ._format import COMP_NUMPIC_ZLIB as COMP_NUMPIC_ZLIB
from ._format import COMP_NUMPIC_ZSTD as COMP_NUMPIC_ZSTD
from ._format import COMP_NUMSLOF_ZLIB as COMP_NUMSLOF_ZLIB
from ._format import COMP_NUMSLOF_ZSTD as COMP_NUMSLOF_ZSTD
from ._format import COMP_ZLIB as COMP_ZLIB
from ._format import COMP_ZSTD as COMP_ZSTD
from ._format import ION_MOBILITY_ARRAY_TAILS as _ION_MOBILITY_TAILS
from ._format import TYPE_FLOAT32 as TYPE_FLOAT32
from ._format import TYPE_FLOAT64 as TYPE_FLOAT64
from ._format import TYPE_INT32 as TYPE_INT32

_DEFAULT_PARAM_ONTOLOGY = "MS"
_DEFAULT_UNIT_ONTOLOGY = "UO"


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


def decode_unit_tail(tail: int | list | str) -> str:
    """Reconstruct a unit accession string from its wire form (int = UO: default,
    list = [ontology, tail], str = full accession)."""
    if isinstance(tail, str):
        return tail
    if isinstance(tail, list):
        return f"{tail[0]}:{tail[1]:07d}"
    return f"{_DEFAULT_UNIT_ONTOLOGY}:{tail:07d}"


# Ion mobility array tails
ION_MOBILITY_ARRAY_TAILS: dict[str, int] = {decode_tail(tail): tail for tail in _ION_MOBILITY_TAILS}
