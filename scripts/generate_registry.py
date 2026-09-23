"""Generate the registry and language-specific internal format constants.

Run from the repo root:
    uv run python scripts/generate_registry.py

The JSON registry is written first conceptually. The Python and TypeScript
modules are pure projections of its keys, CV tails, defaults, and limits.
"""

import json
import sys
from pathlib import Path

from mzmlpy.constants import (
    BinaryDataArrayAccession,
    BinaryDataTypeAccession,
    CollisionDissociationTypeAccession,
    ScanPolarity,
    SpectrumCombinationAccession,
    SpectrumMSAccession,
    SpectrumType,
)

from spectrl.cv import accession_tail
FORMAT_VERSION = 3
MAGIC = "spectrl.v3"
DESC_TYPE = 0
DESC_ARRAY = 1
DESC_ENCODING = 2
DESC_NAME = 4
DESC_DATA = 5
DESC_UNIT = 6


def _tail(acc: str) -> int:
    return accession_tail(acc)


def _enum_to_dict(enum_cls, descriptions: dict[str, str] | None = None) -> dict:
    out = {}
    for member in enum_cls:
        acc = str(member)
        tail = _tail(acc)
        entry = {
            "accession": acc,
            "tail": tail,
            "name": member.name,
        }
        if descriptions and acc in descriptions:
            entry["description"] = descriptions[acc]
        out[str(tail)] = entry
    return out


ION_MOBILITY_ACCESSIONS = (
    "MS:1003007",
    "MS:1002477",
    "MS:1003156",
    "MS:1003006",
    "MS:1002816",
    "MS:1003155",
    "MS:1003153",
    "MS:1003008",
    "MS:1003154",
    "MS:1002893",
)

DESC_UNIT = 6
MAX_SAFE_INTEGER = 9_007_199_254_740_991



UNIT_ACCESSIONS = {
    "MZ": "MS:1000040",
    "NUMBER_OF_DETECTOR_COUNTS": "MS:1000131",
    "PERCENT_OF_BASE_PEAK": "MS:1000132",
    "COUNTS_PER_SECOND": "MS:1000814",
    "SECOND": "UO:0000010",
    "MILLISECOND": "UO:0000028",
    "MINUTE": "UO:0000031",
    "VOLT_SECOND_PER_SQUARE_CENTIMETER": "MS:1002814",
}

# Public API names are owned here so an upstream mzmlpy rename cannot silently
# break ArrayAccession members in a spectrl release.
ARRAY_SYMBOLS = {
    "MS:1003007": "RAW_ION_MOBILITY",
    "MS:1002477": "MEAN_ION_MOBILITY_DRIFT_TIME",
    "MS:1003156": "DECONVOLUTED_ION_MOBILITY_DRIFT_TIME",
    "MS:1003006": "MEAN_INVERSE_REDUCED_ION_MOBILITY",
    "MS:1002816": "MEAN_ION_MOBILITY",
    "MS:1003155": "DECONVOLUTED_INVERSE_REDUCED_ION_MOBILITY",
    "MS:1003153": "RAW_ION_MOBILITY_DRIFT_TIME",
    "MS:4000210": "VACUUM_PUMP_PRESSURE",
    "MS:1003008": "RAW_INVERSE_REDUCED_ION_MOBILITY",
    "MS:1003154": "DECONVOLUTED_ION_MOBILITY",
    "MS:1000595": "TIME",
    "MS:1002478": "MEAN_CHARGE",
    "MS:1000514": "MZ",
    "MS:1002744": "SAMPLED_NOISE_INTENSITY",
    "MS:1000820": "FLOW_RATE",
    "MS:1000516": "CHARGE",
    "MS:1002745": "SAMPLED_NOISE_BASELINE",
    "MS:1002893": "ION_MOBILITY",
    "MS:1002530": "BASELINE",
    "MS:1002529": "RESOLUTION",
    "MS:1000821": "PRESSURE",
    "MS:1000515": "INTENSITY",
    "MS:1002716": "MEASURED_ELEMENT",
    "MS:1003158": "SCANNING_QUADRUPOLE_POSITION_UPPER_BOUND_MZ",
    "MS:1000786": "NON_STANDARD_DATA",
    "MS:1003157": "SCANNING_QUADRUPOLE_POSITION_LOWER_BOUND_MZ",
    "MS:1002742": "NOISE",
    "MS:1000617": "WAVELENGTH",
    "MS:1000517": "SIGNAL_TO_NOISE",
    "MS:1003143": "MASS",
    "MS:1000822": "TEMPERATURE",
    "MS:1002743": "SAMPLED_NOISE_MZ",
}


def _binary_array_dict() -> dict:
    entries = _enum_to_dict(BinaryDataArrayAccession)
    for entry in entries.values():
        entry["name"] = ARRAY_SYMBOLS[entry["accession"]]
    return entries


registry = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://github.com/pgarrett-scripps/spectrl/schema/registry.json",
    "title": "spectrl registry",
    "description": (
        "Machine-readable registry of all integer keys, CV accession tails, "
        "and codec identifiers used in the spectrl.v3 token format."
    ),
    "spectrl_version": FORMAT_VERSION,
    "wire_constants": {
        "checksum_hex_chars": 8,
        "max_blob_bytes": 64 * 1024 * 1024,
        "max_token_bytes": 16 * 1024 * 1024,
        "max_array_length": 4_000_000,
        "max_cbor_depth": 32,
        "max_cbor_items": 100_000,
        "default_mz_ppm": 0.1,
        "default_intensity_scale": 3_600,
        "max_safe_integer": MAX_SAFE_INTEGER,
    },
    # ── Token format ──────────────────────────────────────────────────────────
    "token_format": {
        "magic": MAGIC,
        "description": (
            "identifier '.' version '.' mode '.' base64url(payload) '.' checksum. The CBOR document is "
            "the header map (see header_keys) with each array's encoded words embedded "
            "inline as a CBOR byte string in its descriptor (descriptor key 5). Encoded "
            "deterministically (RFC 8949 §4.2). The format version is carried only in the "
            "magic. The token string is the interchange unit."
        ),
        "payload_modes": {"r": "raw CBOR", "z": "zlib stream", "b": "Brotli stream"},
        "selection": "Default zlib-6. Explicit auto chooses the shortest available token, ties z/r/b",
        "presets": {"z": 6, "b": 5},
        "required_payload_modes": ["r", "z"],
        "expanded_payload_limit": 16 * 1024 * 1024,
        "base64url": "RFC 4648 §5: URL-safe alphabet, no padding ('=' stripped).",
        "checksum": (
            "REQUIRED fifth part: CRC-32/ISO-HDLC over the ASCII text of the first four parts, "
            "'spectrl.version.mode.payload', encoded as eight lowercase hexadecimal characters. "
            "Consumers MUST reject a token on mismatch."
        ),
        "parts": [
            {"index": 0, "content": "format identifier", "example": "spectrl"},
            {"index": 1, "content": "version identifier", "example": f"v{FORMAT_VERSION}"},
            {"index": 2, "content": "payload compression: r raw, z zlib, b Brotli"},
            {"index": 3, "content": "base64url(raw or compressed CBOR document)"},
            {"index": 4, "content": "CRC-32 checksum over parts 0-3 (required, 8 lowercase hex chars)"},
        ],
    },
    # ── Ontology defaults ─────────────────────────────────────────────────────
    "ontology_defaults": {
        "param_accession": "MS",
        "unit_accession": "UO",
        "description": (
            "CV param tails are integers from the MS: namespace by default. Tail encoding "
            "requires an exactly-7-digit tail. Param keys from any other ontology (or with a "
            "non-7-digit tail) are the full accession string. Unit tails (values) are integers "
            "from the UO: namespace by default. Other ontologies use [ontology_string, tail_int], "
            "or the full accession string when the tail is not 7 digits."
        ),
    },
    # ── CV param encoding rules ───────────────────────────────────────────────
    "cvparam_encoding": {
        "description": "Ordered list of [accession, value] pairs. Repeated accessions are retained.",
        "forms": [
            {"form": "flag", "example": [1000130, None]},
            {"form": "valued", "example": [1000511, 2]},
            {"form": "with_unit", "example": [1000016, [23.41, 31]]},
            {"form": "other_ontology", "example": ["NCIT:C25330", "sample"]},
        ],
    },
    # ── Top-level header keys ─────────────────────────────────────────────────
    "header_keys": {
        "0": {
            "name": "default_array_length",
            "type": "int",
            "required": True,
            "description": "Number of peaks. Mirrors mzML @defaultArrayLength.",
        },
        "1": {
            "name": "id",
            "type": "string",
            "required": False,
            "description": "Spectrum identifier string. Mirrors mzML @id (e.g. 'scan=42').",
        },
        "2": {
            "name": "spectrum_params",
            "type": "cvparam_list",
            "required": False,
            "description": (
                "Spectrum-level CV parameters as a ordered list of [accession, value] pairs. "
                "Includes ms level, polarity flag, centroid/profile flag, TIC, "
                "base peak m/z and intensity, lowest/highest observed m/z, etc."
            ),
        },
        "3": {
            "name": "scan_list",
            "type": "object",
            "required": False,
            "description": "Mirrors mzML scanList.",
            "fields": {
                "c": {
                    "name": "combination",
                    "type": "int (accession tail)",
                    "description": "Spectrum combination method tail (e.g. no combination, sum, mean).",
                },
                "s": {
                    "name": "scans",
                    "type": "array of scan objects",
                    "description": "Each scan: {0: cvparam_list, 1: [scan_window_cvparam_lists], 2: [user_params]}.",
                    "scan_fields": {
                        "0": "cvparam_list: scan params (start time, ion injection time, filter string, …)",
                        "1": "array of cvparam_lists: one per scan window (lower/upper m/z limits)",
                        "2": "array of user_param maps: scan-level free-text params (optional)",
                    },
                },
            },
        },
        "4": {
            "name": "precursor_list",
            "type": "array of precursor objects",
            "required": False,
            "description": "Mirrors mzML precursorList.",
            "precursor_fields": {
                "0": "isolation_window: cvparam_list (target m/z, lower/upper offsets)",
                "1": "selected_ions: array of cvparam_lists (m/z, charge, intensity, IM)",
                "2": "activation: cvparam_list (method as flag + collision energy as value)",
            },
        },
        "5": {
            "name": "product_list",
            "type": "array of product objects",
            "required": False,
            "description": "Mirrors mzML productList. Each product: {0: isolation_window cvparam_list}.",
        },
        "6": {
            "name": "binary_data_array_list",
            "type": "array of array_descriptor objects",
            "required": False,
            "description": (
                "One descriptor per binary array. Each carries its blob inline (key 5). "
                "Optional like all keys except 0. Absent means the spectrum carries no arrays."
            ),
            "descriptor_keys": {
                str(DESC_TYPE): {
                    "name": "type",
                    "description": "int: data type accession tail (see data_types). float64/float32/int32 supported",
                },
                str(DESC_ARRAY): {
                    "name": "array",
                    "description": (
                        "int: array type accession tail (see array_types). MS:1000786 = non-standard, see key 4"
                    ),
                },
                "2": {"name": "encoding", "description": "[identifier, revision, optional parameter map]"},
                "7": {"name": "fidelity", "description": "0 bit-exact or 1 potentially lossy relative to the encoder input"},
                "8": {"name": "params", "description": "Ordered scientific CV parameter pairs"},
                "9": {"name": "user_params", "description": "User parameters"},
                "10": {"name": "processing", "description": "Ordered processing records"},
                "11": {"name": "extensions", "description": "Namespaced extension map"},
                str(DESC_NAME): {
                    "name": "name",
                    "description": (
                        "Nonempty str: required for MS:1000786, optional for standard arrays. "
                        "Names do not change standard array identity."
                    ),
                },
                str(DESC_DATA): {
                    "name": "d",
                    "description": "bytes: the array's encoded words, embedded inline as a CBOR byte string",
                },
                str(DESC_UNIT): {
                    "name": "unit",
                    "description": "optional CV unit accession encoded with the same rules as cvParam units",
                },
            },
        },
        "7": {
            "name": "user_param_list",
            "type": "array of user_param objects",
            "required": False,
            "description": (
                "Spectrum-level free-text userParams (no CV accession). Each: "
                "{n: name, v?: value, u?: unit-tail}. Scan-level userParams "
                "live under scan_fields key 2. Omitted entirely when empty."
            ),
        },
    },
    # ── Compression codecs ────────────────────────────────────────────────────
    "unit_accessions": {
        "description": "Stable unit accessions commonly used by binary arrays.",
        "units": {name: {"accession": accession} for name, accession in UNIT_ACCESSIONS.items()},
    },
    # ── Data types ────────────────────────────────────────────────────────────
    "data_types": {
        "description": (
            "Binary data type accession tails. Used in array descriptor 'type' field. "
            "Only float64, float32, and int32 are permitted in spectrl.v3 tokens. Other "
            "mzML data types (int64, ASCII string) are listed for completeness but MUST NOT appear."
        ),
        "types": _enum_to_dict(
            BinaryDataTypeAccession,
            {
                str(BinaryDataTypeAccession.FLOAT_64): "64-bit IEEE-754 little-endian double. Default.",
                str(BinaryDataTypeAccession.FLOAT_32): "32-bit IEEE-754 little-endian float.",
                str(BinaryDataTypeAccession.INT_32): "32-bit signed integer little-endian.",
                str(BinaryDataTypeAccession.INT_64): (
                    "64-bit signed integer little-endian. NOT permitted in spectrl.v3."
                ),
            },
        ),
    },
    # ── Array types ───────────────────────────────────────────────────────────
    "array_types": {
        "description": "Array semantic type accession tails. Used in array descriptor 'array' field.",
        "core": _binary_array_dict(),
    },
    # ── Well-known spectrum CV params ─────────────────────────────────────────
    "well_known_cv_params": {
        "description": (
            "Commonly used CV params in spectrl tokens. All are MS: ontology. "
            "This list is not exhaustive. Any valid PSI-MS cvParam may appear."
        ),
        "spectrum_level": {
            str(_tail(SpectrumType.CENTROID)): {
                "accession": str(SpectrumType.CENTROID),
                "name": "centroid spectrum",
                "form": "flag",
            },
            str(_tail(SpectrumType.PROFILE)): {
                "accession": str(SpectrumType.PROFILE),
                "name": "profile spectrum",
                "form": "flag",
            },
            str(_tail(ScanPolarity.POSITIVE)): {
                "accession": str(ScanPolarity.POSITIVE),
                "name": "positive scan",
                "form": "flag",
            },
            str(_tail(ScanPolarity.NEGATIVE)): {
                "accession": str(ScanPolarity.NEGATIVE),
                "name": "negative scan",
                "form": "flag",
            },
            str(_tail(SpectrumMSAccession.MS_LEVEL)): {
                "accession": str(SpectrumMSAccession.MS_LEVEL),
                "name": "ms level",
                "form": "valued",
                "type": "int",
            },
            str(_tail(SpectrumMSAccession.TOTAL_ION_CURRENT)): {
                "accession": str(SpectrumMSAccession.TOTAL_ION_CURRENT),
                "name": "total ion current",
                "form": "valued",
                "type": "float",
            },
            "1000504": {"accession": "MS:1000504", "name": "base peak m/z", "form": "valued", "type": "float"},
            "1000505": {"accession": "MS:1000505", "name": "base peak intensity", "form": "valued", "type": "float"},
            "1000528": {"accession": "MS:1000528", "name": "lowest observed m/z", "form": "valued", "type": "float"},
            "1000527": {"accession": "MS:1000527", "name": "highest observed m/z", "form": "valued", "type": "float"},
        },
        "scan": {
            str(_tail(SpectrumMSAccession.SCAN_START_TIME)): {
                "accession": str(SpectrumMSAccession.SCAN_START_TIME),
                "name": "scan start time",
                "form": "valued_with_unit",
                "type": "float",
                "typical_unit": "UO:0000031 (minute) or UO:0000010 (second)",
            },
            str(_tail(SpectrumMSAccession.ION_INJECTION_TIME)): {
                "accession": str(SpectrumMSAccession.ION_INJECTION_TIME),
                "name": "ion injection time",
                "form": "valued",
                "type": "float",
                "unit": "ms",
            },
        },
        "scan_window": {
            str(_tail(SpectrumMSAccession.SCAN_WINDOW_LOWER_LIMIT)): {
                "accession": str(SpectrumMSAccession.SCAN_WINDOW_LOWER_LIMIT),
                "name": "scan window lower limit",
                "form": "valued",
                "type": "float",
            },
            str(_tail(SpectrumMSAccession.SCAN_WINDOW_UPPER_LIMIT)): {
                "accession": str(SpectrumMSAccession.SCAN_WINDOW_UPPER_LIMIT),
                "name": "scan window upper limit",
                "form": "valued",
                "type": "float",
            },
        },
        "isolation_window": {
            "1000827": {
                "accession": "MS:1000827",
                "name": "isolation window target m/z",
                "form": "valued",
                "type": "float",
            },
            "1000828": {
                "accession": "MS:1000828",
                "name": "isolation window lower offset",
                "form": "valued",
                "type": "float",
            },
            "1000829": {
                "accession": "MS:1000829",
                "name": "isolation window upper offset",
                "form": "valued",
                "type": "float",
            },
        },
        "selected_ion": {
            str(_tail(SpectrumMSAccession.SELECTED_ION_MZ)): {
                "accession": str(SpectrumMSAccession.SELECTED_ION_MZ),
                "name": "selected ion m/z",
                "form": "valued",
                "type": "float",
            },
            str(_tail(SpectrumMSAccession.CHARGE_STATE)): {
                "accession": str(SpectrumMSAccession.CHARGE_STATE),
                "name": "charge state",
                "form": "valued",
                "type": "int",
            },
            str(_tail(SpectrumMSAccession.PEAK_INTENSITY)): {
                "accession": str(SpectrumMSAccession.PEAK_INTENSITY),
                "name": "peak intensity",
                "form": "valued",
                "type": "float",
            },
        },
        "activation": {
            "1000045": {"accession": "MS:1000045", "name": "collision energy", "form": "valued", "type": "float"},
            **{
                str(_tail(str(m))): {"accession": str(m), "name": m.name.replace("_", " ").lower(), "form": "flag"}
                for m in CollisionDissociationTypeAccession
            },
        },
        "scan_combination": _enum_to_dict(SpectrumCombinationAccession),
    },
    # ── Ion mobility array types ──────────────────────────────────────────────
    "ion_mobility_array_types": {
        "description": "Subset of array_types that represent ion mobility. "
        "Any of these tails in a descriptor indicates an IM array.",
        "tails": {str(_tail(acc)): str(acc) for acc in ION_MOBILITY_ACCESSIONS},
    },
    # ── Canonical form rules ──────────────────────────────────────────────────
    "canonical_form": {
        "description": "Rules for producing a deterministic token from the same input.",
        "rules": [
            "Peaks sorted m/z-ascending before encoding. All parallel arrays (incl. auxiliary) permuted identically.",
            "NaN and Inf values are not allowed in any float array.",
            "Array descriptors emitted in fixed order: m/z, intensity, charge, then additional arrays sorted "
            "ascending by key (CV accession string, or name for non-standard arrays).",
            "CRC-32/ISO-HDLC checksum (required fifth token part) is computed over the ASCII text before "
            "the checksum, 'spectrl.version.mode.payload' (blobs are inline and therefore covered).",
            "Checksum encoding: eight lowercase hexadecimal characters, zero-padded.",
            "Default lossy arrays use quantized words with a pointwise 0.1 ppm bound for m/z and log1p scale 3600 for intensity, "
            "raised to ceil(3600 / 2 * (m + 1) / m) when the smallest positive intensity m is below 1.",
            "Default lossless m/z uses delta and shuffle, intensity uses shuffle, and other arrays use raw words.",
            "Integer and auxiliary arrays remain exact in both profiles. Invalid automatic quantization falls back to exact.",
            "Array blobs have no individual compression. Whole-document zlib level 6 is the default payload compression.",
        ],
    },
}

# Versioned operation and context registries are independent of PSI-MS aliases.
from spectrl.pipeline import ENCODING_NAMES
from spectrl.context import FIELDS, ALLOWED
registry["encodings"] = {str(v): {"name": k, "revision": 1, "lossless": v < 3,
    "parameters": {"scale": "finite positive number", "width": "1, 2, 4, or 8", "log": "optional boolean", "delta": "optional boolean"} if v == 3 else {}}
    for k, v in ENCODING_NAMES.items()}
registry["core_encodings"] = [0, 1, 2, 3]
registry["default_profiles"] = {"lossless": {"mz": 2, "intensity": 1, "other": 0},
    "lossy": {"mz": {"encoding": 3, "max_error_ppm": 0.1, "log": True, "delta": True},
              "intensity": {"encoding": 3, "scale": 3600, "log": True,
                            "scale_rule": "max(3600, ceil(3600 / 2 * (m + 1) / m)) when the smallest positive intensity m < 1"},
              "other": 0},
    "integer_arrays": "exact", "outer_compression": "zlib"}
registry["operation_descriptor"] = {
    "form": "[identifier, revision, optional string-keyed parameters]",
    "identifier": "nonnegative built-in integer or namespaced string, such as org.example:codec",
    "revision": "positive safe integer",
    "unknown": "inspection and forwarding allowed, full decoding fails",
}
registry["context_fields"] = {str(v): k for k, v in FIELDS.items()}
registry["context_records"] = {kind: sorted(keys) for kind, keys in ALLOWED.items()}
registry["extension_record"] = {"revision": "positive safe integer", "required": "boolean", "data": "CBOR value"}
for key, name, kind in [(8, "source", "source record"), (9, "acquisition", "acquisition record"),
                        (10, "processing", "ordered processing records"), (11, "extensions", "namespaced map")]:
    registry["header_keys"][str(key)] = {"name": name, "type": kind, "required": False}
registry["header_keys"]["12"] = {
    "name": "cv_versions",
    "type": "map of ontology prefix to version string",
    "required": False,
    "description": (
        "Source-declared ontology version for each accession prefix used by the spectrum, "
        "keyed without the colon (MS, UO). Values are opaque nonempty text recorded verbatim; "
        "declared syntax varies across files and is never parsed. Informational provenance only: "
        "the accession is the identifier, and a reader must not reject a token over the version it names."
    ),
}
registry["parameter_group"] = {"0": "ordered CV pairs", "1": "optional user parameters"}
registry["header_keys"]["3"]["fields"]["s"]["scan_fields"] = {
    "0": "CV pairs", "1": "parameter groups for scan windows", "2": "user parameters",
    "3": "source", "4": "acquisition", "5": "processing"}
registry["header_keys"]["4"]["precursor_fields"] = {
    "0": "isolation window parameter group", "1": "selected ion parameter groups", "2": "activation parameter group",
    "3": "source", "4": "acquisition", "5": "processing"}
registry["header_keys"]["5"]["description"] = "Each product is {0: optional isolation window parameter group}."


def _entry_tail(entries: dict, accession: str) -> int:
    return next(int(tail) for tail, entry in entries.items() if entry["accession"] == accession)


def _generated_values(r: dict) -> dict[str, object]:
    descriptors = r["header_keys"]["6"]["descriptor_keys"]
    types = r["data_types"]["types"]
    arrays = r["array_types"]["core"]
    return {
        "FORMAT_VERSION": r["spectrl_version"],
        "MAGIC": r["token_format"]["magic"],
        "CHECKSUM_HEX_CHARS": r["wire_constants"]["checksum_hex_chars"],
        **{
            ("DESC_DATA" if value["name"] == "d" else f"DESC_{value['name'].upper()}"): int(key)
            for key, value in descriptors.items()
        },
        "MAX_BLOB_BYTES": r["wire_constants"]["max_blob_bytes"],
        "MAX_TOKEN_BYTES": r["wire_constants"]["max_token_bytes"],
        "MAX_ARRAY_LENGTH": r["wire_constants"]["max_array_length"],
        "MAX_CBOR_DEPTH": r["wire_constants"]["max_cbor_depth"],
        "MAX_CBOR_ITEMS": r["wire_constants"]["max_cbor_items"],
        "DEFAULT_MZ_PPM": r["wire_constants"]["default_mz_ppm"],
        "DEFAULT_INTENSITY_SCALE": r["wire_constants"]["default_intensity_scale"],
        "MAX_SAFE_INTEGER": r["wire_constants"]["max_safe_integer"],
        "TYPE_FLOAT64": _entry_tail(types, "MS:1000523"),
        "TYPE_FLOAT32": _entry_tail(types, "MS:1000521"),
        "TYPE_INT32": _entry_tail(types, "MS:1000519"),
        "ARRAY_MZ": _entry_tail(arrays, "MS:1000514"),
        "ARRAY_INTENSITY": _entry_tail(arrays, "MS:1000515"),
        "ARRAY_CHARGE": _entry_tail(arrays, "MS:1000516"),
        "ARRAY_NON_STANDARD": _entry_tail(arrays, "MS:1000786"),
        "ION_MOBILITY_ARRAY_TAILS": tuple(int(v) for v in r["ion_mobility_array_types"]["tails"]),
    }


def _python_module(values: dict[str, object]) -> str:
    lines = ['"""Generated from schema/registry.json. Do not edit by hand."""', ""]
    for name, value in values.items():
        if isinstance(value, str):
            lines.append(f"{name} = {json.dumps(value)}")
        elif isinstance(value, tuple):
            if len(value) == 1:
                lines.append(f"{name} = ({value[0]},)")
            else:
                lines.append(f"{name} = (")
                lines.extend(f"    {item}," for item in value)
                lines.append(")")
        else:
            lines.append(f"{name} = {value!r}")
    return "\n".join(lines) + "\n"


def _typescript_module(values: dict[str, object]) -> str:
    lines = ["/** Generated from schema/registry.json. Do not edit by hand. */", ""]
    for name, value in values.items():
        ts_name = name
        if isinstance(value, str):
            rendered = json.dumps(value)
        elif isinstance(value, tuple):
            rendered = "new Set([" + ", ".join(str(v) for v in value) + "])"
            lines.append(f"export const {ts_name}: ReadonlySet<number> = {rendered}")
            continue
        else:
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
        lines.append(f"export const {ts_name} = {rendered}")
    return "\n".join(lines) + "\n"


def _array_accession_entries(r: dict) -> list[tuple[str, str]]:
    arrays = r["array_types"]["core"]
    return [(entry["name"], entry["accession"]) for entry in arrays.values()]


def _python_array_accession_module(r: dict) -> str:
    lines = [
        '"""Generated PSI-MS binary-array accessions. Do not edit by hand."""',
        "",
        "from enum import StrEnum",
        "",
        "",
        "class ArrayAccession(StrEnum):",
        '    """Stable PSI-MS identities for registered binary arrays."""',
        "",
    ]
    lines.extend(f"    {name} = {json.dumps(accession)}" for name, accession in _array_accession_entries(r))
    return "\n".join(lines) + "\n"


def _typescript_array_accession_module(r: dict) -> str:
    lines = [
        "/** Generated PSI-MS binary-array accessions. Do not edit by hand. */",
        "",
        "export const ArrayAccession = {",
    ]
    lines.extend(f"  {name}: {json.dumps(accession)}," for name, accession in _array_accession_entries(r))
    lines.extend(
        [
            "} as const",
            "",
            "export type ArrayAccession = (typeof ArrayAccession)[keyof typeof ArrayAccession]",
            "",
        ]
    )
    return "\n".join(lines)


def _python_simple_accession_module(class_name: str, doc: str, entries: list[tuple[str, str]]) -> str:
    lines = [
        f'"""Generated {doc.lower()}. Do not edit by hand."""',
        "",
        "from enum import StrEnum",
        "",
        "",
        f"class {class_name}(StrEnum):",
        f'    """{doc}."""',
        "",
    ]
    lines.extend(f"    {name} = {json.dumps(accession)}" for name, accession in entries)
    return "\n".join(lines) + "\n"


def _typescript_simple_accession_module(name: str, entries: list[tuple[str, str]]) -> str:
    lines = [f"/** Generated {name} values. Do not edit by hand. */", "", f"export const {name} = {{"]
    lines.extend(f"  {symbol}: {json.dumps(accession)}," for symbol, accession in entries)
    lines.extend(["} as const", "", f"export type {name} = (typeof {name})[keyof typeof {name}]", ""])
    return "\n".join(lines)


def _unit_entries(r: dict) -> list[tuple[str, str]]:
    return [(name, entry["accession"]) for name, entry in r["unit_accessions"]["units"].items()]


def _write_generated_modules(r: dict, root: Path) -> None:
    values = _generated_values(r)
    (root / "src/spectrl/_format.py").write_text(_python_module(values))
    (root / "js/src/format.ts").write_text(_typescript_module(values))
    (root / "src/spectrl/array_accession.py").write_text(_python_array_accession_module(r))
    (root / "js/src/array_accession.ts").write_text(_typescript_array_accession_module(r))
    (root / "src/spectrl/unit_accession.py").write_text(
        _python_simple_accession_module("UnitAccession", "Common binary-array unit accessions", _unit_entries(r))
    )
    (root / "js/src/unit_accession.ts").write_text(
        _typescript_simple_accession_module("UnitAccession", _unit_entries(r))
    )


root = Path(__file__).parent.parent
if len(sys.argv) > 1 and sys.argv[1] == "--check-generated":
    values = _generated_values(registry)
    expected = {
        root / "src/spectrl/_format.py": _python_module(values),
        root / "js/src/format.ts": _typescript_module(values),
        root / "src/spectrl/array_accession.py": _python_array_accession_module(registry),
        root / "js/src/array_accession.ts": _typescript_array_accession_module(registry),
        root / "src/spectrl/unit_accession.py": _python_simple_accession_module(
            "UnitAccession", "Common binary-array unit accessions", _unit_entries(registry)
        ),
        root / "js/src/unit_accession.ts": _typescript_simple_accession_module(
            "UnitAccession", _unit_entries(registry)
        ),
    }
    stale = [str(path.relative_to(root)) for path, content in expected.items() if path.read_text() != content]
    if stale:
        raise SystemExit(f"generated modules are stale: {', '.join(stale)}. Run: just registry")
    print("Generated modules are current")
else:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "schema/registry.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(registry, indent=2))
    print(f"Written {out_path}  ({out_path.stat().st_size:,} bytes)")
    if len(sys.argv) == 1:
        _write_generated_modules(registry, root)
        print("Written generated Python and TypeScript modules")
