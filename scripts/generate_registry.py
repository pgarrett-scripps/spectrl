"""Generate the registry and language-specific internal format constants.

Run from the repo root:
    uv run python scripts/generate_registry.py

The JSON registry is written first conceptually; the Python and TypeScript
modules are pure projections of its keys, CV tails, defaults, and limits.
"""

import json
import sys
from pathlib import Path

from mzmlpy.constants import (
    BinaryDataArrayAccession,
    BinaryDataTypeAccession,
    CollisionDissociationTypeAccession,
    CompressionTypeAccessions,
    ScanPolarity,
    SpectrumCombinationAccession,
    SpectrumMSAccession,
    SpectrumType,
)

from spectrl.cv import accession_tail
from spectrl.header import (
    DESC_ARRAY,
    DESC_COMP,
    DESC_DATA,
    DESC_FP,
    DESC_NAME,
    DESC_TYPE,
)
from spectrl.token import FORMAT_VERSION, MAGIC


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


registry = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://github.com/pgarrett-scripps/spectrl/schema/registry.json",
    "title": "spectrl registry",
    "description": (
        "Machine-readable registry of all integer keys, CV accession tails, "
        "and codec identifiers used in the spectrl2 token format."
    ),
    "spectrl_version": FORMAT_VERSION,
    "wire_constants": {
        "hash_bytes": 12,
        "max_blob_bytes": 64 * 1024 * 1024,
        "max_token_bytes": 16 * 1024 * 1024,
        "max_array_length": 4_000_000,
        "max_cbor_depth": 32,
        "max_cbor_items": 100_000,
        "default_numlin_fp": 100_000,
        "default_numslof_fp": 3_600,
    },
    # ── Token format ──────────────────────────────────────────────────────────
    "token_format": {
        "magic": MAGIC,
        "description": (
            "magic '.' base64url(CBOR document) ['.' integrity_hash]. The CBOR document is "
            "the header map (see header_keys) with each array's compressed blob embedded "
            "inline as a CBOR byte string in its descriptor (descriptor key 5). Encoded "
            "deterministically (RFC 8949 §4.2). The format version is carried only in the "
            "magic; the token string is the interchange unit."
        ),
        "base64url": "RFC 4648 §5: URL-safe alphabet, no padding ('=' stripped).",
        "integrity_hash": (
            "OPTIONAL third part: base64url(first 12 bytes of SHA-256 over the ASCII text "
            "of the first two parts, 'magic.payload'), 16 chars. Verified over the received "
            "text; consumers MUST reject a three-part token on mismatch."
        ),
        "parts": [
            {"index": 0, "content": "magic string", "example": MAGIC},
            {"index": 1, "content": "base64url(CBOR document); header map + inline array blobs"},
            {"index": 2, "content": "integrity hash over parts 0-1 (optional, 16 base64url chars)"},
        ],
    },
    # ── Ontology defaults ─────────────────────────────────────────────────────
    "ontology_defaults": {
        "param_accession": "MS",
        "unit_accession": "UO",
        "description": (
            "CV param tails are integers from the MS: namespace by default; tail encoding "
            "requires an exactly-7-digit tail. Param keys from any other ontology (or with a "
            "non-7-digit tail) are the full accession string. Unit tails (values) are integers "
            "from the UO: namespace by default; other ontologies use [ontology_string, tail_int], "
            "or the full accession string when the tail is not 7 digits."
        ),
    },
    # ── CV param encoding rules ───────────────────────────────────────────────
    "cvparam_encoding": {
        "description": "How a single cvParam is stored as a CBOR map entry.",
        "forms": [
            {
                "form": "flag",
                "key": "tail_int (MS: default)",
                "value": "null",
                "example": {"1000130": None},
                "meaning": "Presence is the meaning (e.g. positive scan).",
            },
            {
                "form": "valued",
                "key": "tail_int",
                "value": "number or string",
                "example": {"1000511": 2},
                "meaning": "Param with a scalar value (e.g. ms level = 2).",
            },
            {
                "form": "valued_with_unit",
                "key": "tail_int",
                "value": "[value, unit_tail_int]  OR  [value, [ontology, unit_tail_int]]",
                "example": {"1000016": [23.41, 31]},
                "meaning": "Param with value and unit (e.g. scan time 23.41 min, UO:0000031=31).",
            },
            {
                "form": "non_ms_ontology",
                "key": "full accession string",
                "value": "same value rules as above",
                "example": {"UO:0000010": 3.5},
                "meaning": (
                    "Param from a non-MS ontology (or with a non-7-digit tail); "
                    "the map key is the full accession string."
                ),
            },
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
            "type": "cvparam_map",
            "required": False,
            "description": (
                "Spectrum-level CV parameters as a tail-keyed map. "
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
                    "description": "Each scan: {0: cvparam_map, 1: [scan_window_cvparam_maps], 2: [user_params]}.",
                    "scan_fields": {
                        "0": "cvparam_map: scan params (start time, ion injection time, filter string, …)",
                        "1": "array of cvparam_maps: one per scan window (lower/upper m/z limits)",
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
                "0": "isolation_window: cvparam_map (target m/z, lower/upper offsets)",
                "1": "selected_ions: array of cvparam_maps (m/z, charge, intensity, IM)",
                "2": "activation: cvparam_map (method as flag + collision energy as value)",
            },
        },
        "5": {
            "name": "product_list",
            "type": "array of product objects",
            "required": False,
            "description": "Mirrors mzML productList. Each product: {0: isolation_window cvparam_map}.",
        },
        "6": {
            "name": "binary_data_array_list",
            "type": "array of array_descriptor objects",
            "required": False,
            "description": (
                "One descriptor per binary array; each carries its blob inline (key 5). "
                "Optional like all keys except 0; absent means the spectrum carries no arrays."
            ),
            "descriptor_keys": {
                str(DESC_TYPE): {
                    "name": "type",
                    "description": "int: data type accession tail (see data_types); float64/float32/int32 supported",
                },
                str(DESC_ARRAY): {
                    "name": "array",
                    "description": (
                        "int: array type accession tail (see array_types); MS:1000786 = non-standard, see key 4"
                    ),
                },
                str(DESC_COMP): {
                    "name": "comp",
                    "description": "int: compression accession tail (see compression_codecs)",
                },
                str(DESC_FP): {
                    "name": "fp",
                    "description": (
                        "int: numpress fixed-point scale factor actually used by the blob, a whole "
                        "number; linear/slof codecs only. Omitted when it is the codec default, "
                        "so absent means that default."
                    ),
                },
                str(DESC_NAME): {
                    "name": "name",
                    "description": (
                        "str: free-text descriptor name; REQUIRED iff key 1 is MS:1000786 (non-standard array)"
                    ),
                },
                str(DESC_DATA): {
                    "name": "d",
                    "description": "bytes: the array's compressed blob, embedded inline as a CBOR byte string",
                },
            },
        },
        "7": {
            "name": "interp",
            "type": "string",
            "required": False,
            "description": (
                "ProForma 2.0 peptide interpretation string. "
                "PSI-MOD terms as [MOD:00046], Unimod as [UNIMOD:21], bare mass deltas as [+79.966]."
            ),
        },
        "8": {
            "name": "user_param_list",
            "type": "array of user_param objects",
            "required": False,
            "description": (
                "Spectrum-level free-text userParams (no CV accession). Each: "
                "{n: name, v?: value, t?: xsd-type, u?: unit-tail}. Scan-level userParams "
                "live under scan_fields key 2. Omitted entirely when empty."
            ),
        },
    },
    # ── Compression codecs ────────────────────────────────────────────────────
    "compression_codecs": {
        "description": (
            "Keyed by MS: accession tail integer. The 'pipeline' field describes encode order (decode is reversed)."
        ),
        "codecs": {
            str(_tail(CompressionTypeAccessions.MS_NUMPRESS_LINEAR_PREDICTION_ZLIB)): {
                "accession": str(CompressionTypeAccessions.MS_NUMPRESS_LINEAR_PREDICTION_ZLIB),
                "name": "MS-Numpress linear prediction + zlib",
                "use_for": "m/z arrays (lossy default)",
                "pipeline": ["numpress_encode_linear(data, fp)", "zlib_compress"],
                "decode_pipeline": ["zlib_decompress", "numpress_decode_linear"],
                "lossy": True,
                "library_hint": "pynumpress.encode_linear / decode_linear",
            },
            str(_tail(CompressionTypeAccessions.MS_NUMPRESS_SHORT_LOGGED_FLOAT_ZLIB)): {
                "accession": str(CompressionTypeAccessions.MS_NUMPRESS_SHORT_LOGGED_FLOAT_ZLIB),
                "name": "MS-Numpress short logged float + zlib",
                "use_for": "intensity arrays (lossy default)",
                "pipeline": ["numpress_encode_slof(data, fp)", "zlib_compress"],
                "decode_pipeline": ["zlib_decompress", "numpress_decode_slof"],
                "lossy": True,
                "library_hint": "pynumpress.encode_slof / decode_slof",
            },
            str(_tail(CompressionTypeAccessions.MS_NUMPRESS_POSITIVE_INTEGER_ZLIB)): {
                "accession": str(CompressionTypeAccessions.MS_NUMPRESS_POSITIVE_INTEGER_ZLIB),
                "name": "MS-Numpress positive integer + zlib",
                "use_for": "charge arrays (lossy, rounds to nearest integer)",
                "pipeline": ["numpress_encode_pic(data)", "zlib_compress"],
                "decode_pipeline": ["zlib_decompress", "numpress_decode_pic"],
                "lossy": True,
                "library_hint": "pynumpress.encode_pic / decode_pic",
            },
            str(_tail(CompressionTypeAccessions.ZLIB_COMPRESSION)): {
                "accession": str(CompressionTypeAccessions.ZLIB_COMPRESSION),
                "name": "zlib",
                "use_for": (
                    "all arrays when lossless=True, and always for auxiliary arrays; "
                    "raw little-endian bytes of the declared type (float64/float32/int32) + zlib"
                ),
                "pipeline": ["to_little_endian_bytes(data, type)", "zlib_compress"],
                "decode_pipeline": ["zlib_decompress", "from_little_endian_bytes(type)"],
                "lossy": False,
                "library_hint": "zlib.compress / decompress",
            },
        },
    },
    # ── Data types ────────────────────────────────────────────────────────────
    "data_types": {
        "description": (
            "Binary data type accession tails. Used in array descriptor 'type' field. "
            "Only float64, float32, and int32 are permitted in spectrl2 tokens; other "
            "mzML data types (int64, ASCII string) are listed for completeness but MUST NOT appear."
        ),
        "types": _enum_to_dict(
            BinaryDataTypeAccession,
            {
                str(BinaryDataTypeAccession.FLOAT_64): "64-bit IEEE-754 little-endian double. Default.",
                str(BinaryDataTypeAccession.FLOAT_32): "32-bit IEEE-754 little-endian float.",
                str(BinaryDataTypeAccession.INT_32): "32-bit signed integer little-endian.",
                str(BinaryDataTypeAccession.INT_64): "64-bit signed integer little-endian. NOT permitted in spectrl2.",
            },
        ),
    },
    # ── Array types ───────────────────────────────────────────────────────────
    "array_types": {
        "description": "Array semantic type accession tails. Used in array descriptor 'array' field.",
        "core": _enum_to_dict(BinaryDataArrayAccession),
    },
    # ── Well-known spectrum CV params ─────────────────────────────────────────
    "well_known_cv_params": {
        "description": (
            "Commonly used CV params in spectrl tokens. All are MS: ontology. "
            "This list is not exhaustive; any valid PSI-MS cvParam may appear."
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
        "tails": {
            str(_tail(acc)): str(acc)
            for acc in (
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
        },
    },
    # ── Canonical form rules ──────────────────────────────────────────────────
    "canonical_form": {
        "description": "Rules for producing a deterministic token from the same input.",
        "rules": [
            "Peaks sorted m/z-ascending before encoding; all parallel arrays (incl. auxiliary) permuted identically.",
            "NaN and Inf values are not allowed in any float array.",
            "Array descriptors emitted in fixed order: m/z, intensity, charge, ion mobility, then auxiliary arrays "
            "sorted ascending by key (CV accession string, or name for non-standard arrays).",
            "Integrity hash (optional third token part) is computed over the ASCII text of the first two "
            "token parts, 'magic.payload' (blobs are inline in the payload and therefore covered).",
            "Hash algorithm: SHA-256, first 12 bytes, base64url-encoded (16 chars).",
            "Numpress fp is a whole number. Defaults: linear 100000; slof floor(min(3600, "
            "65535/ln(max+1))), clamped DOWN so no encoded value overflows uint16. A descriptor omits "
            "fp when it equals the default and carries the clamped value otherwise.",
            "Arrays containing negative values fall back to the lossless zlib codec in lossy mode "
            "(numpress cannot represent them); negative m/z is rejected.",
        ],
    },
}


def _entry_tail(entries: dict, accession: str) -> int:
    return next(int(tail) for tail, entry in entries.items() if entry["accession"] == accession)


def _generated_values(r: dict) -> dict[str, object]:
    descriptors = r["header_keys"]["6"]["descriptor_keys"]
    codecs = r["compression_codecs"]["codecs"]
    types = r["data_types"]["types"]
    arrays = r["array_types"]["core"]
    return {
        "FORMAT_VERSION": r["spectrl_version"],
        "MAGIC": r["token_format"]["magic"],
        "HASH_BYTES": r["wire_constants"]["hash_bytes"],
        **{
            ("DESC_DATA" if value["name"] == "d" else f"DESC_{value['name'].upper()}"): int(key)
            for key, value in descriptors.items()
        },
        "MAX_BLOB_BYTES": r["wire_constants"]["max_blob_bytes"],
        "MAX_TOKEN_BYTES": r["wire_constants"]["max_token_bytes"],
        "MAX_ARRAY_LENGTH": r["wire_constants"]["max_array_length"],
        "MAX_CBOR_DEPTH": r["wire_constants"]["max_cbor_depth"],
        "MAX_CBOR_ITEMS": r["wire_constants"]["max_cbor_items"],
        "DEFAULT_NUMLIN_FP": r["wire_constants"]["default_numlin_fp"],
        "DEFAULT_NUMSLOF_FP": r["wire_constants"]["default_numslof_fp"],
        "COMP_NUMLIN_ZLIB": _entry_tail(codecs, "MS:1002746"),
        "COMP_NUMSLOF_ZLIB": _entry_tail(codecs, "MS:1002748"),
        "COMP_NUMPIC_ZLIB": _entry_tail(codecs, "MS:1002747"),
        "COMP_ZLIB": _entry_tail(codecs, "MS:1000574"),
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
    lines = ['"""Generated from schema/registry.json; do not edit by hand."""', ""]
    for name, value in values.items():
        if isinstance(value, str):
            lines.append(f"{name} = {json.dumps(value)}")
        elif isinstance(value, tuple):
            lines.append(f"{name} = (")
            lines.extend(f"    {item}," for item in value)
            lines.append(")")
        else:
            lines.append(f"{name} = {value!r}")
    return "\n".join(lines) + "\n"


def _typescript_module(values: dict[str, object]) -> str:
    lines = ["/** Generated from schema/registry.json; do not edit by hand. */", ""]
    for name, value in values.items():
        ts_name = name
        if isinstance(value, str):
            rendered = json.dumps(value)
        elif isinstance(value, tuple):
            rendered = "new Set([" + ", ".join(str(v) for v in value) + "])"
            lines.append(f"export const {ts_name}: ReadonlySet<number> = {rendered};")
            continue
        else:
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
        lines.append(f"export const {ts_name} = {rendered};")
    return "\n".join(lines) + "\n"


def _write_generated_modules(r: dict, root: Path) -> None:
    values = _generated_values(r)
    (root / "src/spectrl/_format.py").write_text(_python_module(values))
    (root / "js/src/format.ts").write_text(_typescript_module(values))


root = Path(__file__).parent.parent
if len(sys.argv) > 1 and sys.argv[1] == "--check-generated":
    values = _generated_values(registry)
    expected = {
        root / "src/spectrl/_format.py": _python_module(values),
        root / "js/src/format.ts": _typescript_module(values),
    }
    stale = [str(path.relative_to(root)) for path, content in expected.items() if path.read_text() != content]
    if stale:
        raise SystemExit(f"generated format modules are stale: {', '.join(stale)}; run: just registry")
    print("Generated format modules are current")
else:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "schema/registry.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(registry, indent=2))
    print(f"Written {out_path}  ({out_path.stat().st_size:,} bytes)")
    if len(sys.argv) == 1:
        _write_generated_modules(registry, root)
        print("Written src/spectrl/_format.py and js/src/format.ts")
