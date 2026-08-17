from __future__ import annotations

import json

import numpy as np
import pytest

from spectrl import (
    ArrayAccession,
    CompressionAccession,
    UnitAccession,
    decode_token,
    encode_spectrum,
    encoding_plan,
    spectrum_from_dict,
    spectrum_to_dict,
)
from spectrl.model import InlineSpectrum, SpectrlCvParam, SpectrlScan


def test_lists_are_normalized_and_sorted_with_extra_arrays():
    spec = InlineSpectrum(
        default_array_length=2,
        mz=[200.0, 100.0],
        intensity=[2.0, 1.0],
        extra_arrays={ArrayAccession.RAW_ION_MOBILITY_DRIFT_TIME: [20.0, 10.0]},
    )
    decoded = decode_token(encode_spectrum(spec))
    np.testing.assert_allclose(decoded.extra_arrays[ArrayAccession.RAW_ION_MOBILITY_DRIFT_TIME], [10.0, 20.0])


def test_array_units_roundtrip_and_appear_in_plan():
    accession = ArrayAccession.RAW_ION_MOBILITY_DRIFT_TIME
    spec = InlineSpectrum(
        default_array_length=2,
        mz=[100.0, 200.0],
        intensity=[1.0, 2.0],
        extra_arrays={accession: [12.1, 13.4]},
        array_units={accession: UnitAccession.MILLISECOND},
    )
    decoded = decode_token(encode_spectrum(spec))
    assert decoded.array_units[accession] == UnitAccession.MILLISECOND
    item = next(v for v in encoding_plan(spec) if v["accession"] == accession)
    assert item["unit_accession"] == UnitAccession.MILLISECOND


def test_full_compression_accession_and_semantic_guards():
    spec = InlineSpectrum(default_array_length=2, mz=[100.1, 200.2], intensity=[1.0, 2.0])
    decoded = decode_token(encode_spectrum(spec, array_encodings={"mz": CompressionAccession.NUMPRESS_LINEAR_ZSTD}))
    np.testing.assert_allclose(decoded.mz, spec.mz, atol=1e-5)
    with pytest.raises(ValueError, match="not compatible"):
        encode_spectrum(spec, array_encodings={"mz": CompressionAccession.NUMPRESS_PIC_ZLIB})


def test_reserved_custom_array_names_are_rejected():
    spec = InlineSpectrum(default_array_length=1, mz=[1.0], intensity=[2.0], extra_arrays={"mz": [3.0]})
    with pytest.raises(ValueError, match="reserved"):
        encode_spectrum(spec)


def test_json_representation_roundtrips_all_modeled_fields():
    spec = InlineSpectrum(
        default_array_length=1,
        mz=[100.0],
        intensity=[200.0],
        id="scan=1",
        params=[SpectrlCvParam("MS:1000511", 2)],
        scans=[SpectrlScan(params=[SpectrlCvParam("MS:1000016", 1.2, "UO:0000031")])],
        extra_arrays={ArrayAccession.SIGNAL_TO_NOISE: [3.0]},
        array_units={"intensity": UnitAccession.NUMBER_OF_DETECTOR_COUNTS},
    )
    restored = spectrum_from_dict(json.loads(json.dumps(spectrum_to_dict(spec))))
    assert spectrum_to_dict(restored) == spectrum_to_dict(spec)
