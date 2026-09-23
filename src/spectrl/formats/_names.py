"""CV term names for formats that require them, without shipping an ontology.

mzML declares `name` required on every cvParam, but a token carries accessions
only: the accession is the identifier, and the term name is a label the reader
is expected to resolve. spectrl deliberately does not bundle psi-ms.obo, which
is larger than the library and would tie releases to ontology releases.

So names come from what spectrl already defines normatively -- the generated
array and unit accession enums, and the well-known parameters in the registry
-- and any accession outside that set is written with the accession itself as
its name. That is valid, self-describing, and honest about what is known. A
caller holding an ontology can pass `names` to do better.
"""

from __future__ import annotations

from ..array_accession import ArrayAccession
from ..unit_accession import UnitAccession

# Identities the format defines itself, which no ontology lookup should be
# needed to spell.
_CORE = {
    "MS:1000514": "m/z array",
    "MS:1000515": "intensity array",
    "MS:1000516": "charge array",
    "MS:1000786": "non-standard data array",
    "MS:1000523": "64-bit float",
    "MS:1000521": "32-bit float",
    "MS:1000519": "32-bit integer",
    "MS:1000576": "no compression",
    "MS:1000127": "centroid spectrum",
    "MS:1000128": "profile spectrum",
    "MS:1000129": "negative scan",
    "MS:1000130": "positive scan",
    "MS:1000511": "ms level",
    "MS:1000285": "total ion current",
    "MS:1000504": "base peak m/z",
    "MS:1000505": "base peak intensity",
    "MS:1000527": "highest observed m/z",
    "MS:1000528": "lowest observed m/z",
    "MS:1000016": "scan start time",
    "MS:1000927": "ion injection time",
    "MS:1000744": "selected ion m/z",
    "MS:1000041": "charge state",
    "MS:1000042": "peak intensity",
    "MS:1000045": "collision energy",
    "MS:1000501": "scan window lower limit",
    "MS:1000500": "scan window upper limit",
}


def _from_enum(member) -> str:
    """RAW_ION_MOBILITY -> 'raw ion mobility'. The generated enums spell the
    PSI-MS term in their member names, so the name is already there."""
    return member.name.replace("_", " ").lower()


_GENERATED = {
    **{str(m): _from_enum(m) for m in ArrayAccession},
    **{str(m): _from_enum(m) for m in UnitAccession},
}

# Core spellings win: the generated enum name is a mechanical transform, while
# these are the terms as PSI-MS writes them.
KNOWN: dict[str, str] = {**_GENERATED, **_CORE}


def term_name(accession: str, names: dict[str, str] | None = None) -> str:
    """The name to write for an accession. Falls back to the accession."""
    if names and accession in names:
        return names[accession]
    return KNOWN.get(accession, accession)


def is_known(accession: str, names: dict[str, str] | None = None) -> bool:
    return bool(names and accession in names) or accession in KNOWN
