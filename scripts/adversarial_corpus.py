"""Deterministic adversarial token corpus shared by both reference implementations.

Two families:

* ``named_cases()`` -- hand-written attacks on one rule each, with the verdict
  the format requires. These are the regression cases; a name never changes
  meaning, so a diff in this file is a deliberate change to the accepted
  language.
* ``mutation_cases()`` -- seeded mutations of a metadata-rich spectrum's decoded
  CBOR tree (replace, delete, and insert at random paths), re-framed with a
  valid checksum so the mutation reaches the semantic validators rather than
  dying at the CRC. Verdicts are not asserted; these exist so Python and
  TypeScript can be compared on inputs nobody thought to write down.

``python scripts/adversarial_corpus.py --out corpus.json`` writes tokens plus
this implementation's verdict. ``scripts/check_adversarial_parity.py`` feeds
that to the TypeScript decoder and fails on any disagreement.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import json
import random
import sys
import zlib
from pathlib import Path

import cbor2
import numpy as np

from spectrl import SpectrlDecodeError, decode_token
from spectrl.cbor_format import _canonical, encode_cbor, read_token_payload, token_checksum
from spectrl.model import (
    InlineSpectrum,
    SpectrlActivation,
    SpectrlCvParam,
    SpectrlIsolationWindow,
    SpectrlPrecursor,
    SpectrlProduct,
    SpectrlScan,
    SpectrlScanWindow,
    SpectrlSelectedIon,
    SpectrlUserParam,
)
from spectrl.token import b64url_encode

ROOT = Path(__file__).resolve().parents[1]
ACCEPT, REJECT = "accept", "reject"


def _gzip(raw: bytes) -> bytes:
    """gzip with the header fixed: mtime 0 and OS byte 255, which Python < 3.13 writes as 3."""
    blob = gzip.compress(raw, mtime=0)
    return blob[:9] + b"\xff" + blob[10:]


def frame(raw: bytes, mode: str = "r") -> str:
    """Wrap payload bytes in valid framing with a correct checksum."""
    packed = {"r": lambda b: b, "z": lambda b: zlib.compress(b, 6)}[mode](raw)
    return frame_text(b64url_encode(packed), mode)


def frame_text(payload: str, mode: str = "r") -> str:
    """Wrap an already-spelled payload string, so base64 itself can be attacked."""
    body = f"spectrl.v3.{mode}.{payload}"
    return f"{body}.{token_checksum(body)}"


def _minimal() -> InlineSpectrum:
    return InlineSpectrum(
        default_array_length=3,
        mz=np.array([100.0, 200.0, 300.0]),
        intensity=np.array([1.0, 2.0, 3.0]),
    )


def _rich() -> InlineSpectrum:
    """A spectrum touching every optional header key, so mutations reach them all."""
    return InlineSpectrum(
        default_array_length=3,
        mz=np.array([100.0, 200.0, 300.0]),
        intensity=np.array([1.0, 2.0, 3.0]),
        charge=np.array([1, 2, 1], dtype=np.int32),
        extra_arrays={"MS:1002476": np.array([0.1, 0.2, 0.3]), "custom": np.array([1.0, 2.0, 3.0])},
        id="scan=1",
        params=[SpectrlCvParam("MS:1000511", 2), SpectrlCvParam("MS:1000016", 23.4, "UO:0000031")],
        user_params=[SpectrlUserParam("note", "hello"), SpectrlUserParam("n2", 5, "UO:0000031")],
        scans=[
            SpectrlScan(
                params=[SpectrlCvParam("MS:1000016", 1.0, "UO:0000031")],
                windows=[SpectrlScanWindow(params=[SpectrlCvParam("MS:1000501", 100.0, "MS:1000040")])],
            )
        ],
        precursors=[
            SpectrlPrecursor(
                isolation_window=SpectrlIsolationWindow(params=[SpectrlCvParam("MS:1000827", 500.0)]),
                selected_ions=[SpectrlSelectedIon(params=[SpectrlCvParam("MS:1000744", 500.0)])],
                activation=SpectrlActivation(params=[SpectrlCvParam("MS:1000133", None)]),
            )
        ],
        products=[
            SpectrlProduct(isolation_window=SpectrlIsolationWindow(params=[SpectrlCvParam("MS:1000827", 300.0)]))
        ],
        array_units={"mz": "MS:1000040", "intensity": "MS:1000131"},
        array_names={"custom": "custom"},
        array_params={"intensity": [SpectrlCvParam("MS:1000618", 1.0)]},
        array_user_params={"mz": [SpectrlUserParam("au", "x")]},
        array_processing={"mz": [{"operation": "x:y", "revision": 1, "parameters": {"a": 1}}]},
        source={"id": "s1", "name": "file.raw", "location": "file:///x", "external_ids": ["E1"]},
        acquisition={
            "instrument": {
                "id": "IC1",
                "components": [{"kind": "source", "order": 1}],
                "software": {"id": "sw", "version": "1.0"},
            }
        },
        processing=[
            {
                "operation": "x:z",
                "revision": 2,
                "parameters": {"k": "v"},
                "source_params": [SpectrlCvParam("MS:1000285", 1.0)],
            }
        ],
        extensions={"ns:ext": {"revision": 1, "required": False, "data": {"a": [1, 2]}}},
        array_extensions={"charge": {"ns:e2": {"revision": 1, "required": False, "data": 1}}},
        cv_versions={"MS": "4.1.1"},
    )


def base_document(spec: InlineSpectrum | None = None) -> dict:
    """The decoded CBOR tree of a valid token, ready to be mutated."""
    return cbor2.loads(read_token_payload(encode_cbor(spec or _minimal(), lossless=True, compression="raw")))


def _doc_token(doc: dict, mode: str = "r") -> str:
    """Serialise a mutated tree the way a conforming writer would.

    Numbers go through the same canonicalisation an encoder applies, so a case
    that writes 1.0 tests the rule it means to and not the separate rule that
    an integral value is spelled as a CBOR integer. Attacks on numeric spelling
    itself are written as raw bytes and go through `frame` instead.
    """
    return frame(_canonical(doc), mode)


def named_cases() -> list[dict]:
    """Attacks on one rule each, with the verdict the format requires."""
    base = base_document()
    valid = _doc_token(base)
    payload = valid.split(".")[3]
    out: list[dict] = []

    def case(name: str, token: str, expect: str, rule: str) -> None:
        out.append({"name": name, "token": token, "expect": expect, "rule": rule})

    def mutate(name: str, expect: str, rule: str, fn, mode: str = "r") -> None:
        doc = copy.deepcopy(base)
        fn(doc)
        case(name, _doc_token(doc, mode), expect, rule)

    case("valid/raw", valid, ACCEPT, "1 framing")
    case("valid/zlib", frame(read_token_payload(valid), "z"), ACCEPT, "1 framing")

    # --- 1 framing and base64 canonicality -----------------------------------
    case("framing/base64_padded", frame_text(payload + "=" * (-len(payload) % 4)), REJECT, "1 unpadded base64url")
    case("framing/base64_over_padded", frame_text(payload + "==="), REJECT, "1 unpadded base64url")
    case(
        "framing/base64_trailing_bits",
        frame_text(payload[:-1] + chr(ord(payload[-1]) + 1)),
        REJECT,
        "1 canonical base64url",
    )
    case("framing/base64_impossible_length", frame_text(payload + "A"), REJECT, "1 unpadded base64url")
    case(
        "framing/checksum_uppercase",
        valid.rsplit(".", 1)[0] + "." + valid.rsplit(".", 1)[1].upper(),
        REJECT,
        "1 checksum",
    )
    case("framing/checksum_tampered", valid[:-1] + ("0" if valid[-1] != "0" else "1"), REJECT, "1 checksum")
    case("framing/mode_uppercase", frame_text(payload, "r").replace(".r.", ".R.", 1), REJECT, "1 payload mode")
    case("framing/extra_part", valid + ".extra", REJECT, "1 five parts")

    # --- 1 compression -------------------------------------------------------
    raw = read_token_payload(valid)
    case(
        "compression/zlib_trailing_data",
        frame_text(b64url_encode(zlib.compress(raw, 6) + b"\x00"), "z"),
        REJECT,
        "1 trailing data",
    )
    case(
        "compression/zlib_concatenated",
        frame_text(b64url_encode(zlib.compress(raw, 6) * 2), "z"),
        REJECT,
        "1 concatenated streams",
    )
    case("compression/bare_deflate", frame_text(b64url_encode(zlib.compress(raw, 6)[2:-4]), "z"), REJECT, "1 zlib only")
    case("compression/gzip_as_zlib", frame_text(b64url_encode(_gzip(raw)), "z"), REJECT, "1 zlib only")
    case(
        "compression/zlib_truncated",
        frame_text(b64url_encode(zlib.compress(raw, 6)[:-3]), "z"),
        REJECT,
        "1 truncated stream",
    )
    case("compression/raw_mode_holds_zlib", frame(zlib.compress(raw, 6), "r"), REJECT, "1 no inference from bytes")

    def preset_dict() -> bytes:
        c = zlib.compressobj(6, zlib.DEFLATED, 15, 8, zlib.Z_DEFAULT_STRATEGY, zdict=b"spectrl")
        return c.compress(raw) + c.flush()

    case(
        "compression/zlib_preset_dictionary",
        frame_text(b64url_encode(preset_dict()), "z"),
        REJECT,
        "1 no preset dictionary",
    )

    # --- 1 CBOR structure ----------------------------------------------------
    case("cbor/indefinite_map", frame(b"\xbf\x00\x00\x06\x80\xff"), REJECT, "1 definite length")
    case("cbor/indefinite_text", frame(b"\xa3\x00\x00\x01\x7f\x62ab\x61c\xff\x06\x80"), REJECT, "1 definite length")
    case("cbor/tag", frame(b"\xa2\x00\xc0\x61x\x06\x80"), REJECT, "1 no tags")
    case("cbor/simple_value_24", frame(b"\xa2\x00\x00\x06\xf8\x20"), REJECT, "1 no other simple values")
    case("cbor/undefined", frame(b"\xa2\x00\x00\x06\xf7"), REJECT, "1 undefined unsupported")
    case("cbor/trailing_bytes", frame(_canonical(base) + b"\x00"), REJECT, "1 trailing data")
    case("cbor/duplicate_key", frame(b"\xa3\x00\x03\x18\x00\x03\x06\x80"), REJECT, "1 duplicate map keys")
    case("cbor/map_length_overdeclared", frame(b"\xb9\xff\xff\x00\x00"), REJECT, "1 truncated item")
    case("cbor/array_length_overdeclared", frame(b"\xa2\x00\x00\x06\x9a\x00\xff\xff\xff"), REJECT, "8 item ceiling")
    case(
        "cbor/string_length_2_63",
        frame(b"\xa2\x00\x00\x06\x5b\x7f\xff\xff\xff\xff\xff\xff\xff"),
        REJECT,
        "1 truncated string",
    )
    case("cbor/float_nan", frame(b"\xa2\x00\x00\x06\xfb\x7f\xf8\x00\x00\x00\x00\x00\x00"), REJECT, "1 finite numbers")
    case(
        "cbor/float_infinity",
        frame(b"\xa2\x00\x00\x06\xfb\x7f\xf0\x00\x00\x00\x00\x00\x00"),
        REJECT,
        "1 finite numbers",
    )
    case(
        "cbor/integer_above_safe_range",
        frame(b"\xa2\x00\x1b\x00\x20\x00\x00\x00\x00\x00\x00\x06\x80"),
        REJECT,
        "1 safe integer range",
    )
    # A CBOR float carrying an integral safe value has an integer spelling that
    # section 1 requires instead. JavaScript cannot tell the two apart once
    # parsed, so accepting it would put the two readers permanently at odds.
    case(
        "cbor/integral_float64",
        frame(b"\xa2\x00\xfb\x40\x08\x00\x00\x00\x00\x00\x00\x06\x80"),
        REJECT,
        "1 integral values are integers",
    )
    case("cbor/integral_float16", frame(b"\xa2\x00\xf9\x00\x00\x06\x80"), REJECT, "1 integral values are integers")
    case(
        "cbor/negative_zero_float",
        frame(b"\xa2\x00\xfb\x80\x00\x00\x00\x00\x00\x00\x00\x06\x80"),
        REJECT,
        "1 signed zero is integer zero",
    )
    case("cbor/root_not_a_map", frame(cbor2.dumps([1, 2, 3])), REJECT, "2 integer-keyed map")

    # --- 2 header ------------------------------------------------------------
    mutate("header/missing_key0", REJECT, "2 key 0 required", lambda d: d.pop(0))
    mutate("header/key0_negative", REJECT, "2 nonnegative integer", lambda d: d.__setitem__(0, -1))
    mutate("header/key0_above_ceiling", REJECT, "8 peak ceiling", lambda d: d.__setitem__(0, 4_000_001))
    mutate("header/key0_boolean", REJECT, "2 nonnegative integer", lambda d: d.__setitem__(0, True))
    mutate("header/unknown_key", REJECT, "2 unknown keys are errors", lambda d: d.__setitem__(13, 1))
    mutate("header/negative_key", REJECT, "2 unknown keys are errors", lambda d: d.__setitem__(-1, 1))
    mutate("header/text_key", REJECT, "2 unknown keys are errors", lambda d: d.__setitem__("0", 1))
    mutate("header/id_not_text", REJECT, "2 spectrum id is text", lambda d: d.__setitem__(1, 5))
    mutate("header/params_not_a_list", REJECT, "3 ordered pairs", lambda d: d.__setitem__(2, {}))
    mutate("header/extensions_null", REJECT, "8 extension map", lambda d: d.__setitem__(11, None))

    # --- 3 parameters --------------------------------------------------------
    mutate(
        "param/accession_above_tail_range",
        REJECT,
        "3 tails are 0..9999999",
        lambda d: d.__setitem__(2, [[10000000, 1]]),
    )
    mutate(
        "param/accession_max_safe_integer",
        REJECT,
        "3 tails are 0..9999999",
        lambda d: d.__setitem__(2, [[9007199254740991, 1]]),
    )
    mutate("param/accession_negative", REJECT, "3 tails are 0..9999999", lambda d: d.__setitem__(2, [[-1, None]]))
    mutate(
        "param/accession_malformed_string",
        REJECT,
        "3 accession syntax",
        lambda d: d.__setitem__(2, [["not an accession", 1]]),
    )
    mutate("param/pair_of_three", REJECT, "3 accession/value pairs", lambda d: d.__setitem__(2, [[1000511, 1, 2]]))
    mutate("param/value_boolean", REJECT, "3 scalar domain", lambda d: d.__setitem__(2, [[1000511, True]]))
    mutate("param/value_map", REJECT, "3 scalar domain", lambda d: d.__setitem__(2, [[1000511, {}]]))
    # Unit wire forms. Syntax only: no ontology is consulted, but a value that is
    # not one of section 3's three shapes is not a unit.
    for label, wire in [
        ("boolean", True),
        ("negative_tail", -5),
        ("tail_above_range", 10000000),
        ("garbage_string", "junk"),
        ("empty_string", ""),
        ("pair_too_short", ["UO"]),
        ("pair_too_long", ["UO", 31, 9]),
        ("pair_integer_prefix", [7, 31]),
        ("pair_nested_prefix", [["UO"], 31]),
        ("pair_text_tail", ["UO", "31"]),
        ("null", None),
    ]:
        mutate(
            f"param/unit_{label}", REJECT, "3 unit wire form", lambda d, w=wire: d.__setitem__(2, [[1000016, [1.0, w]]])
        )
    mutate("param/unit_uo_tail", ACCEPT, "3 unit wire form", lambda d: d.__setitem__(2, [[1000016, [1.0, 31]]]))
    mutate(
        "param/unit_ontology_pair",
        ACCEPT,
        "3 unit wire form",
        lambda d: d.__setitem__(2, [[1000016, [1.0, ["MS", 1000040]]]]),
    )
    mutate(
        "param/unit_full_string",
        ACCEPT,
        "3 unit wire form",
        lambda d: d.__setitem__(2, [[1000016, [1.0, "MOD:00046"]]]),
    )

    # Array-scoped parameters reach the same validators by a different route.
    mutate(
        "param/array_unit_pair_too_short",
        REJECT,
        "3 unit wire form",
        lambda d: d[6][0].__setitem__(8, [[1000131, [1.0, ["UO"]]]]),
    )
    mutate(
        "param/array_user_unit_pair_too_short",
        REJECT,
        "3 unit wire form",
        lambda d: d[6][0].__setitem__(9, [{"n": "q", "u": ["UO"]}]),
    )
    mutate(
        "param/processing_unit_pair_too_short",
        REJECT,
        "3 unit wire form",
        lambda d: d.__setitem__(10, [{13: "x:y", 14: 1, 16: [[1000131, [1.0, ["UO"]]]]}]),
    )

    mutate("userparam/empty_name", REJECT, "3 nonempty name", lambda d: d.__setitem__(7, [{"n": ""}]))
    mutate("userparam/missing_name", REJECT, "3 nonempty name", lambda d: d.__setitem__(7, [{"v": 1}]))
    mutate(
        "userparam/type_annotation",
        REJECT,
        "3 no type annotation",
        lambda d: d.__setitem__(7, [{"n": "x", "t": "int"}]),
    )
    mutate("userparam/boolean_value", REJECT, "3 scalar domain", lambda d: d.__setitem__(7, [{"n": "x", "v": True}]))
    mutate(
        "scanlist/combination_out_of_range",
        REJECT,
        "3 flag accession tail",
        lambda d: d.__setitem__(3, {"s": [], "c": 10000000}),
    )
    mutate("scanlist/unknown_key", REJECT, "3 scan list shape", lambda d: d.__setitem__(3, {"s": [], "x": 1}))

    # --- 4 array descriptors -------------------------------------------------
    def desc(doc, key, value):
        doc[6][0][key] = value

    for key in (0, 1, 2, 5, 7):
        mutate(f"descriptor/missing_key{key}", REJECT, "4 required keys", lambda d, k=key: d[6][0].pop(k))
    mutate("descriptor/key3_present", REJECT, "4 key 3 is invalid", lambda d: desc(d, 3, 1))
    mutate("descriptor/unknown_key", REJECT, "4 unknown keys are errors", lambda d: desc(d, 12, 1))
    mutate("descriptor/unsupported_type", REJECT, "2 three numeric types", lambda d: desc(d, 0, 1000522))
    mutate("descriptor/array_tail_negative", REJECT, "3 tails are 0..9999999", lambda d: desc(d, 1, -1))
    mutate("descriptor/fidelity_two", REJECT, "4 fidelity is 0 or 1", lambda d: desc(d, 7, 2))
    mutate("descriptor/fidelity_boolean", REJECT, "4 fidelity is 0 or 1", lambda d: desc(d, 7, True))
    mutate("descriptor/fidelity_mismatch", REJECT, "4 fidelity matches encoding", lambda d: desc(d, 7, 1))
    mutate("descriptor/data_not_bytes", REJECT, "4 bytes carry blobs", lambda d: desc(d, 5, "abc"))
    mutate("descriptor/name_empty", REJECT, "4 nonempty name", lambda d: desc(d, 4, ""))
    mutate("descriptor/unit_out_of_range", REJECT, "3 unit wire form", lambda d: desc(d, 6, 10000000))
    mutate("descriptor/processing_not_a_list", REJECT, "7 ordered processing list", lambda d: desc(d, 10, ""))
    mutate("descriptor/processing_empty_map", REJECT, "7 ordered processing list", lambda d: desc(d, 10, {}))
    mutate("descriptor/processing_bytes", REJECT, "7 ordered processing list", lambda d: desc(d, 10, b""))
    mutate("descriptor/extensions_null", REJECT, "8 extension map", lambda d: desc(d, 11, None))
    mutate(
        "descriptor/duplicate_array", REJECT, "2 identity appears once", lambda d: d[6].append(copy.deepcopy(d[6][0]))
    )
    mutate("descriptor/operation_empty_parameters", REJECT, "4 omit empty parameters", lambda d: desc(d, 2, [2, 1, {}]))
    mutate("descriptor/operation_revision_zero", REJECT, "4 positive revision", lambda d: desc(d, 2, [2, 0]))
    mutate("descriptor/operation_four_members", REJECT, "4 operation shape", lambda d: desc(d, 2, [2, 1, {}, 5]))
    mutate(
        "descriptor/operation_integer_keyed_parameters",
        REJECT,
        "4 string-keyed parameters",
        lambda d: desc(d, 2, [2, 1, {1: 2}]),
    )
    mutate("descriptor/operation_bare_integer", REJECT, "4 [identifier, revision]", lambda d: desc(d, 2, 2))
    # Unknown codecs stay inspectable but must not decode, and must never be
    # guessed at or treated as raw words.
    mutate("descriptor/unknown_builtin_encoding", REJECT, "4 unknown encoding fails", lambda d: desc(d, 2, [99, 1]))
    mutate(
        "descriptor/unknown_namespaced_encoding", REJECT, "4 unknown encoding fails", lambda d: desc(d, 2, ["x:y", 1])
    )
    mutate("descriptor/unknown_revision", REJECT, "4 unknown revision fails", lambda d: desc(d, 2, [2, 2]))

    def nonstandard(doc, name):
        doc[6][1][1] = 1000786
        doc[6][1][4] = name

    mutate("descriptor/nonstandard_named_mz", REJECT, "2 reserved core names", lambda d: nonstandard(d, "mz"))
    mutate(
        "descriptor/nonstandard_named_accession",
        REJECT,
        "2 accession-shaped names reserved",
        lambda d: nonstandard(d, "MS:1000517"),
    )
    mutate(
        "descriptor/nonstandard_missing_name",
        REJECT,
        "2 nonstandard needs a name",
        lambda d: d[6][1].__setitem__(1, 1000786),
    )
    mutate(
        "descriptor/nonstandard_plain_name", ACCEPT, "2 nonstandard needs a name", lambda d: nonstandard(d, "my array")
    )

    # --- 5 numeric encodings -------------------------------------------------
    def quantized(doc, params, blob=None):
        doc[6][0][0] = 1000523
        doc[6][0][2] = [3, 1, params]
        doc[6][0][7] = 1
        doc[6][0][5] = blob if blob is not None else bytes(3 * params.get("width", 8))

    mutate(
        "quantized/missing_parameters", REJECT, "5 scale and width required", lambda d: d[6][0].__setitem__(2, [3, 1])
    )
    mutate("quantized/scale_zero", REJECT, "5 finite positive scale", lambda d: quantized(d, {"scale": 0, "width": 8}))
    mutate(
        "quantized/scale_negative",
        REJECT,
        "5 finite positive scale",
        lambda d: quantized(d, {"scale": -1.0, "width": 8}),
    )
    mutate(
        "quantized/scale_boolean",
        REJECT,
        "5 finite positive scale",
        lambda d: quantized(d, {"scale": True, "width": 8}),
    )
    mutate("quantized/width_three", REJECT, "5 width 1, 2, 4 or 8", lambda d: quantized(d, {"scale": 1.0, "width": 3}))
    mutate(
        "quantized/width_boolean", REJECT, "5 width 1, 2, 4 or 8", lambda d: quantized(d, {"scale": 1.0, "width": True})
    )
    mutate(
        "quantized/log_not_boolean",
        REJECT,
        "5 log and delta are booleans",
        lambda d: quantized(d, {"scale": 1.0, "width": 8, "log": 1}),
    )
    mutate(
        "quantized/unknown_parameter",
        REJECT,
        "5 no other parameters",
        lambda d: quantized(d, {"scale": 1.0, "width": 8, "zz": 1}),
    )
    mutate(
        "quantized/byte_count_mismatch",
        REJECT,
        "5 incorrect byte counts",
        lambda d: quantized(d, {"scale": 1.0, "width": 8}, bytes(17)),
    )
    mutate(
        "quantized/index_above_safe_range",
        REJECT,
        "5 index domain",
        lambda d: quantized(d, {"scale": 1.0, "width": 8, "delta": True}, b"\xff" * 24),
    )
    mutate(
        "quantized/declared_for_int32",
        REJECT,
        "5 encoding 3 is float64",
        lambda d: (quantized(d, {"scale": 1.0, "width": 8}), d[6][0].__setitem__(0, 1000519)),
    )

    mutate("blob/raw_misaligned", REJECT, "5 length matches dtype", lambda d: d[6][0].__setitem__(5, bytes(23)))
    mutate(
        "blob/shorter_than_declared", REJECT, "2 arrays have key 0 length", lambda d: d[6][0].__setitem__(5, bytes(8))
    )
    mutate(
        "blob/longer_than_declared", REJECT, "2 arrays have key 0 length", lambda d: d[6][0].__setitem__(5, bytes(32))
    )
    mutate("blob/declared_length_disagrees", REJECT, "2 arrays have key 0 length", lambda d: d.__setitem__(0, 2))

    # --- 7 context records ---------------------------------------------------
    mutate("record/source_disallowed_field", REJECT, "7 allowed fields per record", lambda d: d.__setitem__(8, {8: {}}))
    mutate(
        "record/component_bad_kind",
        REJECT,
        "7 component kinds",
        lambda d: d.__setitem__(9, {8: {9: [{10: "magnet", 11: 0}]}}),
    )
    mutate(
        "record/component_negative_order",
        REJECT,
        "7 nonnegative order",
        lambda d: d.__setitem__(9, {8: {9: [{10: "source", 11: -1}]}}),
    )
    mutate(
        "record/processing_revision_zero",
        REJECT,
        "7 positive revision",
        lambda d: d.__setitem__(10, [{13: "x:y", 14: 0}]),
    )
    mutate("record/external_id_empty", REJECT, "7 nonempty external ids", lambda d: d.__setitem__(8, {6: [""]}))
    mutate("record/unknown_field_key", REJECT, "7 allowed fields per record", lambda d: d.__setitem__(8, {99: "x"}))
    # Processing parameters are a string-keyed map. A byte string reports
    # `typeof "object"` in JavaScript and is neither an Array nor a Map, so it
    # once passed the shape check there while Python rejected it.
    for label, wire in [("bytes", b""), ("bytes_nonempty", b"\x00\x01"), ("list", []), ("integer", 5), ("text", "x")]:
        mutate(
            f"record/processing_parameters_{label}",
            REJECT,
            "7 string-keyed parameters",
            lambda d, w=wire: d.__setitem__(10, [{13: "x:y", 14: 1, 15: w}]),
        )
        mutate(
            f"record/array_processing_parameters_{label}",
            REJECT,
            "7 string-keyed parameters",
            lambda d, w=wire: d[6][0].__setitem__(10, [{13: "x:y", 14: 1, 15: w}]),
        )
    mutate(
        "record/processing_parameters_map",
        ACCEPT,
        "7 string-keyed parameters",
        lambda d: d.__setitem__(10, [{13: "x:y", 14: 1, 15: {"a": 1}}]),
    )
    mutate(
        "record/source_params_bytes",
        REJECT,
        "3 ordered pairs",
        lambda d: d.__setitem__(10, [{13: "x:y", 14: 1, 16: b""}]),
    )
    mutate("record/external_ids_bytes", REJECT, "7 nonempty external ids", lambda d: d.__setitem__(8, {6: b"ab"}))
    mutate("record/components_bytes", REJECT, "7 ordered component list", lambda d: d.__setitem__(9, {8: {9: b""}}))

    # --- 8 extensions and limits ---------------------------------------------
    for label, record in [
        ("missing_revision", {"required": False, "data": 1}),
        ("missing_required", {"revision": 1, "data": 1}),
        ("missing_data", {"revision": 1, "required": False}),
        ("extra_field", {"revision": 1, "required": False, "data": 1, "z": 2}),
        ("revision_zero", {"revision": 0, "required": False, "data": 1}),
        ("required_not_boolean", {"revision": 1, "required": 1, "data": 1}),
    ]:
        mutate(
            f"extension/{label}", REJECT, "8 extension record shape", lambda d, r=record: d.__setitem__(11, {"ns:e": r})
        )
    mutate(
        "extension/unnamespaced_identifier",
        REJECT,
        "8 namespaced keys",
        lambda d: d.__setitem__(11, {"plain": {"revision": 1, "required": False, "data": 1}}),
    )
    mutate(
        "extension/unknown_required",
        REJECT,
        "8 unknown required extension",
        lambda d: d.__setitem__(11, {"ns:e": {"revision": 1, "required": True, "data": 1}}),
    )
    mutate(
        "extension/unknown_optional_retained",
        ACCEPT,
        "8 unknown optional retained",
        lambda d: d.__setitem__(11, {"ns:e": {"revision": 1, "required": False, "data": 1}}),
    )

    nested: object = 1
    for _ in range(31):
        nested = [nested]
    mutate(
        "limits/nesting_over_depth",
        REJECT,
        "8 nesting depth 32",
        lambda d: d.__setitem__(11, {"ns:e": {"revision": 1, "required": False, "data": nested}}),
    )
    mutate(
        "limits/item_count_exceeded",
        REJECT,
        "8 item ceiling",
        lambda d: d.__setitem__(11, {"ns:e": {"revision": 1, "required": False, "data": list(range(100000))}}),
    )

    # The worst legitimate expansion the wire ceilings alone permit: four
    # width-1 quantized arrays of 4,000,000 elements reconstruct to 128 MB of
    # float64 from a ~21 kB token. The default budgets must refuse it.
    big = {
        0: 4_000_000,
        6: [
            {0: 1000523, 1: tail, 2: [3, 1, {"scale": 1.0, "width": 1}], 5: bytes(4_000_000), 7: 1}
            for tail in (1000514, 1000515, 1002476, 1003007)
        ],
    }
    case("limits/decode_amplification", _doc_token(big, "z"), REJECT, "8 default budgets")

    # --- 12 ontology versions ------------------------------------------------
    mutate("cvversions/empty_value", REJECT, "2 nonempty version text", lambda d: d.__setitem__(12, {"MS": ""}))
    mutate("cvversions/numeric_value", REJECT, "2 version carried verbatim", lambda d: d.__setitem__(12, {"MS": 4}))
    mutate(
        "cvversions/prefix_with_colon",
        REJECT,
        "2 prefix written without a colon",
        lambda d: d.__setitem__(12, {"MS:": "4.1"}),
    )
    mutate(
        "cvversions/integer_key", REJECT, "2 prefix written without a colon", lambda d: d.__setitem__(12, {1: "4.1"})
    )
    mutate(
        "cvversions/unknown_release_accepted",
        ACCEPT,
        "2 never rejected over a release",
        lambda d: d.__setitem__(12, {"MS": "not-a-release-anyone-has"}),
    )

    return out


JUNK: list[object] = [
    None,
    True,
    False,
    0,
    -1,
    1,
    3.5,
    float(2**53),
    -0.0,
    9007199254740991,
    9007199254740992,
    "",
    "x",
    "MS:1000511",
    "\x00",
    "\U0001f600",
    b"",
    b"\x00\x01",
    [],
    {},
    [1],
    [1, 2],
    [1, 2, 3],
    {"n": "x"},
    {0: []},
    {1: 1},
    [[1, 2]],
    [[]],
    [None, None],
    ["UO"],
    [[1], 2],
    10000000,
    -10000000,
    [0, 1],
    [3, 1, {}],
    {"scale": 1.0},
    1e308,
    -1e308,
]


def _paths(node, prefix=()):
    yield prefix, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _paths(value, (*prefix, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _paths(value, (*prefix, index))


def mutation_cases(seed: int = 31337, count: int = 20000) -> list[dict]:
    """Seeded replace/delete/insert mutations of the rich spectrum's CBOR tree.

    Deterministic: the same seed and count always give the same tokens, whatever
    else the process has already generated. JUNK holds mutable containers, so
    each pick is copied before it is spliced in. Inserting the shared object
    instead lets a later mutation grow it in place, which silently made the
    corpus depend on generation order.
    """
    base = base_document(_rich())
    paths = [path for path, _ in _paths(base) if path]
    rng = random.Random(seed)
    junk = lambda: copy.deepcopy(rng.choice(JUNK))  # noqa: E731
    out: list[dict] = []
    for index in range(count):
        doc = copy.deepcopy(base)
        for _ in range(rng.randint(1, 3)):
            choice = rng.random()
            path = rng.choice(paths)
            try:
                parent = doc
                for key in path[:-1]:
                    parent = parent[key]
                if choice < 0.72:
                    parent[path[-1]] = junk()
                elif choice < 0.86:
                    del parent[path[-1]]
                elif isinstance(parent, dict):
                    parent[rng.choice([rng.randrange(-3, 20), rng.choice(["z", "n", "v", "u", "s", "c"])])] = junk()
                elif isinstance(parent, list):
                    parent.append(junk())
            except (KeyError, IndexError, TypeError):
                break
        try:
            out.append({"name": f"mutation/{seed}/{index}", "token": _doc_token(doc)})
        except Exception:  # noqa: BLE001 - a mutation that will not even serialise is not a test case
            continue
    return out


def verdict(token: str) -> dict:
    """This implementation's verdict, with the detail the parity check compares."""
    try:
        decoded = decode_token(token)
    except SpectrlDecodeError:
        return {"ok": False}
    except Exception as exc:  # noqa: BLE001 - an escape is the finding, not a crash
        return {"ok": False, "escape": type(exc).__name__, "message": str(exc)[:200]}
    return {
        "ok": True,
        "n": int(decoded.default_array_length),
        "nparams": len(decoded.params),
        "nuser": len(decoded.user_params),
        "arrays": sorted(decoded.extra_arrays),
        "mz": None if decoded.mz is None else [float(x) for x in decoded.mz[:3]],
        "units": dict(sorted(decoded.array_units.items())),
    }


def build(seed: int, mutations: int, *, include_named: bool = True) -> list[dict]:
    cases = (named_cases() if include_named else []) + mutation_cases(seed, mutations)
    for case in cases:
        case["py"] = verdict(case["token"])
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=31337)
    parser.add_argument("--mutations", type=int, default=20000)
    args = parser.parse_args()

    cases = build(args.seed, args.mutations)
    args.out.write_text(json.dumps(cases), encoding="utf-8")

    named = [c for c in cases if "expect" in c]
    wrong = [c for c in named if c["py"]["ok"] != (c["expect"] == ACCEPT)]
    escapes = [c for c in cases if c["py"].get("escape")]
    print(f"{len(cases)} cases ({len(named)} named, {len(cases) - len(named)} mutations) -> {args.out}")
    print(f"named verdict mismatches: {len(wrong)}")
    for case in wrong:
        print(f"  {case['name']}: expected {case['expect']}, rule {case['rule']}, got {case['py']}")
    print(f"non-SpectrlDecodeError escapes: {len(escapes)}")
    for case in escapes[:10]:
        print(f"  {case['name']}: {case['py']['escape']}: {case['py']['message']}")
    return 1 if wrong or escapes else 0


if __name__ == "__main__":
    sys.exit(main())
