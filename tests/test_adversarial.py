"""Adversarial decode cases, from the shared corpus and from specific defects.

The parametrised case at the top runs the whole named corpus in
`scripts/adversarial_corpus.py`, which is also what the cross-implementation
parity check feeds to the TypeScript decoder. The tests below it pin individual
defects that corpus found, so a regression names the rule it broke rather than
just failing an opaque case id.
"""

from __future__ import annotations

import copy
import json
import sys
import zlib
from pathlib import Path

import numpy as np
import pytest

from spectrl import (
    DecodeLimits,
    InlineSpectrum,
    SpectrlCvParam,
    SpectrlDecodeError,
    SpectrlUserParam,
    decode_token,
    encode_spectrum,
)
from spectrl.cbor_format import _canonical, read_token_document, read_token_payload, token_checksum
from spectrl.cv import decode_unit_tail
from spectrl.token import b64url_decode, b64url_encode

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from adversarial_corpus import ACCEPT, base_document, frame, frame_text, named_cases  # noqa: E402

CASES = named_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_named_adversarial_case(case):
    """Every named case gets the verdict the specification requires."""
    if case["expect"] == ACCEPT:
        assert decode_token(case["token"]) is not None
        return
    with pytest.raises(SpectrlDecodeError):
        decode_token(case["token"])


def test_corpus_covers_every_specification_section():
    sections = {c["rule"].split()[0] for c in CASES}
    assert {"1", "2", "3", "4", "5", "7", "8"} <= sections


# --- the public error contract ----------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_malformed_input_never_escapes_as_another_exception(case):
    """SpectrlDecodeError is the only exception decode_token may raise.

    A short unit pair once reached `decode_unit_tail` through array-scoped
    parameters and raised IndexError, which subclasses neither
    SpectrlDecodeError nor ValueError, so a caller guarding the documented
    contract crashed instead of rejecting the token.
    """
    try:
        decode_token(case["token"])
    except SpectrlDecodeError:
        pass
    except Exception as exc:  # noqa: BLE001 - the escape is what we are testing for
        pytest.fail(f"{case['name']} raised {type(exc).__name__}: {exc}")


# --- section 1: one token string per payload --------------------------------


def token():
    return encode_spectrum(
        InlineSpectrum(3, mz=np.array([100.0, 200.0, 300.0]), intensity=np.array([1.0, 2.0, 3.0])),
        lossless=True,
        compression="raw",
    )


def test_base64url_padding_is_rejected():
    payload = token().split(".")[3]
    for padding in ("=", "==", "==="):
        with pytest.raises(SpectrlDecodeError, match="unpadded"):
            decode_token(frame_text(payload + padding))


def test_base64url_trailing_bits_must_be_zero():
    """Exactly one base64url spelling decodes to a given payload."""
    assert b64url_decode("_-4") == b"\xff\xee"
    for alias in ("_-5", "_-6", "_-7"):
        with pytest.raises(SpectrlDecodeError, match="trailing bits"):
            b64url_decode(alias)


def test_a_payload_has_exactly_one_valid_token_string():
    original = token()
    payload = original.split(".")[3]
    aliases = [payload + "=", payload + "==", payload[:-1] + chr(ord(payload[-1]) + 1)]
    for alias in aliases:
        with pytest.raises(SpectrlDecodeError):
            decode_token(frame_text(alias))
    assert decode_token(original) is not None


@pytest.mark.parametrize(
    "raw",
    [
        b"\xa2\x00\xfb\x40\x08\x00\x00\x00\x00\x00\x00\x06\x80",  # 3.0 as float64
        b"\xa2\x00\xfa\x40\x40\x00\x00\x06\x80",  # 3.0 as float32
        b"\xa2\x00\xf9\x42\x00\x06\x80",  # 3.0 as float16
        b"\xa2\x00\xfb\x80\x00\x00\x00\x00\x00\x00\x00\x06\x80",  # -0.0
    ],
)
def test_integral_values_must_be_cbor_integers(raw):
    """`3` and `3.0` must not both spell the same document.

    A JavaScript reader cannot tell them apart after parsing, so tolerating the
    float form would leave the two implementations permanently disagreeing.
    """
    with pytest.raises(SpectrlDecodeError, match="must be CBOR integers"):
        decode_token(frame(raw))


def test_non_integral_and_out_of_range_floats_are_still_allowed():
    spec = InlineSpectrum(
        1,
        mz=np.array([100.0]),
        intensity=np.array([1.0]),
        params=[SpectrlCvParam("MS:1000016", 23.41), SpectrlCvParam("MS:1000505", 1e300)],
    )
    decoded = decode_token(encode_spectrum(spec, lossless=True))
    assert [p.value for p in decoded.params] == [23.41, 1e300]


# --- section 3: unit wire forms ---------------------------------------------

BAD_UNITS = [True, -5, 10000000, "junk", "", ["UO"], ["UO", 31, 9], [7, 31], [["UO"], 31], ["UO", "31"], None]


@pytest.mark.parametrize("wire", BAD_UNITS)
def test_unit_wire_form_is_checked_at_every_scope(wire):
    """Syntax only: no ontology is consulted, but these are not units.

    Before this check a boolean became `UO:0000001`, a three-member pair
    silently dropped its third member, and a nested prefix produced the string
    `"['UO']:0000031"`. Each decoded to an accession the encoder then refused.
    """
    base = base_document()
    scopes = {
        "spectrum param": lambda d: d.__setitem__(2, [[1000016, [1.5, wire]]]),
        "spectrum user param": lambda d: d.__setitem__(7, [{"n": "x", "u": wire}]),
        "array param": lambda d: d[6][0].__setitem__(8, [[1000131, [1.5, wire]]]),
        "array user param": lambda d: d[6][0].__setitem__(9, [{"n": "x", "u": wire}]),
        "processing source param": lambda d: d.__setitem__(10, [{13: "x:y", 14: 1, 16: [[1000131, [1.5, wire]]]}]),
    }
    for mutate in scopes.values():
        doc = copy.deepcopy(base)
        mutate(doc)
        body = "spectrl.v3.r." + b64url_encode(_canonical(doc))
        with pytest.raises(SpectrlDecodeError):
            decode_token(f"{body}.{token_checksum(body)}")


@pytest.mark.parametrize(
    "wire,expected",
    [
        (31, "UO:0000031"),
        (0, "UO:0000000"),
        (9999999, "UO:9999999"),
        (["MS", 1000040], "MS:1000040"),
        ("MOD:00046", "MOD:00046"),
    ],
)
def test_valid_unit_wire_forms_still_decode(wire, expected):
    assert decode_unit_tail(wire) == expected


def test_decoded_units_always_re_encode():
    """Whatever the decoder accepts, the encoder can write back.

    Not a claim that a noncanonical token round-trips byte-identically, only
    that a decoded spectrum is a legal encoder input.
    """
    spec = InlineSpectrum(
        1,
        mz=np.array([100.0]),
        intensity=np.array([1.0]),
        params=[SpectrlCvParam("MS:1000016", 23.41, "UO:0000031")],
        user_params=[SpectrlUserParam("x", 1.5, "MS:1000040")],
    )
    decoded = decode_token(encode_spectrum(spec, lossless=True, compression="raw"))
    again = InlineSpectrum(
        decoded.default_array_length,
        mz=decoded.mz,
        intensity=decoded.intensity,
        params=decoded.params,
        user_params=decoded.user_params,
    )
    assert encode_spectrum(again, lossless=True, compression="raw") == encode_spectrum(
        spec, lossless=True, compression="raw"
    )


# --- section 4: array descriptors -------------------------------------------


@pytest.mark.parametrize("value", ["", {}, b"", 0, None])
def test_array_processing_must_be_a_list(value):
    """An empty string iterates to nothing, which once passed as 'no processing'."""
    doc = base_document()
    doc[6][0][10] = value
    body = "spectrl.v3.r." + b64url_encode(_canonical(doc))
    with pytest.raises(SpectrlDecodeError):
        decode_token(f"{body}.{token_checksum(body)}")


# --- section 8: resource budgets --------------------------------------------


def amplification_token():
    """Four width-1 quantized arrays of 4,000,000 elements: ~21 kB in, 128 MB out."""
    doc = {
        0: 4_000_000,
        6: [
            {0: 1000523, 1: tail, 2: [3, 1, {"scale": 1.0, "width": 1}], 5: bytes(4_000_000), 7: 1}
            for tail in (1000514, 1000515, 1002476, 1003007)
        ],
    }
    return frame(_canonical(doc), "z")


def test_decode_amplification_is_refused_by_default():
    """The wire ceilings alone allow ~6000x expansion, so the budgets are on."""
    token = amplification_token()
    assert len(token) < 32 * 1024
    with pytest.raises(SpectrlDecodeError, match="max_peaks|max_decoded_bytes"):
        decode_token(token)
    with pytest.raises(SpectrlDecodeError, match="max_peaks|max_decoded_bytes"):
        decode_token(token, limits=DecodeLimits())


def test_amplification_ratio_stays_bounded_under_the_defaults():
    limits = DecodeLimits()
    worst_output = limits.max_peaks * 8 * limits.max_arrays
    assert worst_output / limits.max_token_bytes <= 128, "default budgets permit more expansion than intended"
    assert limits.max_decoded_bytes <= 64 * 1024 * 1024


def test_defaults_clear_the_largest_corpus_spectrum():
    """217,009 peaks in a 1.05 MB token is the largest real case measured."""
    limits = DecodeLimits()
    assert limits.max_peaks >= 217_009 * 4
    assert limits.max_token_bytes >= 1_048_822 * 3


def test_unlimited_is_available_for_a_trusted_producer():
    # m/z only: two float64 arrays of this length would exceed the 16 MiB
    # payload ceiling, which is a separate wire limit and not what is under test.
    big = InlineSpectrum(1_200_000, mz=np.arange(1_200_000, dtype=np.float64) / 1000 + 100)
    token = encode_spectrum(big, lossless=True)
    with pytest.raises(SpectrlDecodeError, match="max_peaks"):
        decode_token(token)
    assert decode_token(token, limits=DecodeLimits.unlimited()).default_array_length == 1_200_000


def test_budgets_apply_to_inspection_too():
    with pytest.raises(SpectrlDecodeError):
        read_token_document(amplification_token())


def test_encoding_is_not_bound_by_the_decode_budgets():
    """Encoding self-verifies against the wire ceilings, not the untrusted-input budgets."""
    big = InlineSpectrum(1_200_000, mz=np.arange(1_200_000, dtype=np.float64))
    assert encode_spectrum(big, lossless=True)


# --- compression --------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        lambda raw: zlib.compress(raw, 6) + b"\x00",
        lambda raw: zlib.compress(raw, 6) * 2,
        lambda raw: zlib.compress(raw, 6)[2:-4],
        lambda raw: zlib.compress(raw, 6)[:-3],
    ],
    ids=["trailing", "concatenated", "bare-deflate", "truncated"],
)
def test_zlib_streams_must_be_single_and_complete(payload):
    raw = read_token_payload(token())
    with pytest.raises(SpectrlDecodeError):
        decode_token(frame_text(b64url_encode(payload(raw)), "z"))


# --- the corpus itself --------------------------------------------------------


def test_mutation_corpus_is_deterministic_and_order_independent():
    """A seed names a fixed set of tokens, whatever else was generated first.

    The mutation values include shared mutable containers. Splicing one in by
    reference let a later mutation grow it in place, which made the corpus
    depend on generation order and quietly shrank it as a run progressed.
    """
    from adversarial_corpus import mutation_cases

    first = [c["token"] for c in mutation_cases(99, 300)]
    mutation_cases(31337, 300)
    assert [c["token"] for c in mutation_cases(99, 300)] == first
    assert len(mutation_cases(8675309, 500)) == 500


def test_named_cases_match_the_committed_vector_file():
    """tests/ and js/test/ must be checking the same language."""
    vectors = json.loads((Path(__file__).resolve().parents[1] / "test-vectors/adversarial-vectors.json").read_text())
    committed = {v["name"]: (v["expect"], v["token"]) for v in vectors["vectors"]}
    current = {c["name"]: (c["expect"], c["token"]) for c in CASES}
    assert committed == current, "run `python scripts/gen_adversarial_vectors.py`"
