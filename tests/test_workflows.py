"""User workflows, including real CLI pipelines and conversion reports."""

import json
import subprocess
import sys
from xml.etree.ElementTree import fromstring

import numpy as np
import pytest

from spectrl import (
    InlineSpectrum,
    SpectrlUserParam,
    conversion_report,
    decode_token,
    encoding_report,
    fit_to_budget,
    format_peak_list,
    parse_peak_list,
    spectrum_to_dict,
)


def cli(*args, text=""):
    return subprocess.run([sys.executable, "-m", "spectrl.cli", *args], input=text, text=True, capture_output=True)


def test_quality_matches_actual_token_sorted_and_zero_safe():
    source = InlineSpectrum(
        3,
        mz=[200.123456, 0, 100.123456],
        intensity=[-1, 0, 10],
        extra_arrays={"score": np.array([1, 2, 3], dtype=np.int32)},
        user_params=[SpectrlUserParam("note", "hello")],
    )
    report = encoding_report(source, drop_user_params=True)
    mz, intensity, score = report["arrays"]
    assert 0 < mz["max_absolute_error"] < 1e-5
    assert mz["zero_reference_values"] == 1
    assert mz["changed_zero_values"] == 0
    assert intensity["max_relative_error"] == 0
    assert score["exact"]
    assert report["omitted_user_params"] == 1
    assert not decode_token(report["token"]).user_params
    assert source.user_params
    json.dumps(report, allow_nan=False)
    assert encoding_report(source, lossless=True)["all_arrays_exact"]


def test_quality_empty_and_all_zero_arrays():
    for values in [[], [0, 0]]:
        r = encoding_report(InlineSpectrum(len(values), mz=values))
        assert r["arrays"][0]["max_error_ppm"] is None
        assert r["arrays"][0]["max_absolute_error"] == 0


def test_fit_budget_explicit_and_includes_unicode_carrier():
    source = InlineSpectrum(
        100,
        mz=np.arange(100) * 1.2345,
        intensity=np.arange(100),
        extra_arrays={"score": np.arange(100, dtype=np.int32)},
    )
    with pytest.raises(OverflowError):
        fit_to_budget(source, 250)
    result = fit_to_budget(source, 250, base_url="https://example.org/é#old", allow_peak_trimming=True)
    assert result["carrier_bytes"] == len(result["carrier"].encode()) <= 250
    assert 0 < result["kept_peaks"] < 100
    d = decode_token(result["token"])
    np.testing.assert_array_equal(d.extra_arrays["score"], np.arange(100 - result["kept_peaks"], 100))
    assert source.default_array_length == 100
    with pytest.raises(OverflowError):
        fit_to_budget(source, 1, allow_peak_trimming=True)
    with pytest.raises(ValueError):
        fit_to_budget(source, 250, min_peaks=-1)


def test_fit_metadata_omissions_and_exact_noop():
    source = InlineSpectrum(1, mz=[100], intensity=[42], user_params=[SpectrlUserParam("a", "b")])
    original = encoding_report(source)["token"]
    assert fit_to_budget(source, len(original))["token"] == original
    result = fit_to_budget(source, 1000, drop_user_params=True)
    assert result["omitted_user_params"] == 1
    assert not result["spectrum"].user_params
    assert source.user_params


@pytest.mark.parametrize(
    "text",
    [
        "mz,intensity\n100.5,2\n200,-3",
        "# comment\nm/z\tintensity\n100.5\t2\n200\t-3",
        "\ufeff100.5 2\n\n200 -3",
        '"mz","intensity"\n"100.5","2"\n"200","-3"',
    ],
)
def test_peak_import_export(text):
    s = parse_peak_list(text)
    np.testing.assert_array_equal(s.mz, [100.5, 200])
    np.testing.assert_array_equal(s.intensity, [2, -3])
    r = parse_peak_list(format_peak_list(s))
    np.testing.assert_array_equal(r.mz, s.mz)
    np.testing.assert_array_equal(r.intensity, s.intensity)


@pytest.mark.parametrize("text", ["", "mz,intensity", "1,2,3", "1,", "-1,2", "nan,2", "1e999,2", "1,2\n3,4,5"])
def test_invalid_peak_lists(text):
    with pytest.raises(ValueError):
        parse_peak_list(text)


def test_cli_dtype_pipeline_and_peak_import():
    source = InlineSpectrum(1, mz=[100], intensity=[2], extra_arrays={"a": np.array([1], dtype=np.int32)})
    encoded = cli("encode", "--lossless", text=json.dumps(spectrum_to_dict(source)))
    assert encoded.returncode == 0, encoded.stderr
    decoded = cli("decode", text=encoded.stdout)
    encoded2 = cli("encode", "--lossless", text=decoded.stdout)
    assert encoded2.returncode == 0, encoded2.stderr
    assert encoded2.stdout == encoded.stdout
    exported = cli("decode", "--output-format", "csv", text=encoded.stdout)
    assert parse_peak_list(exported.stdout).default_array_length == 1
    report = cli("report", "--input-format", "text", text="100.123456 10")
    assert report.returncode == 0, report.stderr
    assert json.loads(report.stdout)["arrays"][0]["max_absolute_error"] > 0
    fit = cli("fit", "--max-bytes", "1000", text=json.dumps(spectrum_to_dict(source)))
    assert fit.returncode == 0, fit.stderr
    assert json.loads(fit.stdout)["dropped_peaks"] == 0


@pytest.mark.parametrize("text", ["[]", '{"mz":[-1]}', '{"mz":[1],"intensity":[1,2]}'])
def test_cli_errors_are_concise(text):
    result = cli("encode", text=text)
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert not result.stdout


def test_conversion_report_lists_omissions_and_strict_rejects():
    from mzmlpy.spectra import Spectrum

    xml = fromstring("""<spectrum xmlns="http://psi.hupo.org/ms/mzml" id="scan=1" index="0" defaultArrayLength="0">
      <cvParam cvRef="MS" accession="MS:1000511" name="ms level" value="2"/>
      <userParam name="note" value="kept"/>
      <scanList count="1"><scan><referenceableParamGroupRef ref="missing"/>
      <scanWindowList count="1"><scanWindow><userParam name="lost" value="x"/></scanWindow></scanWindowList>
      </scan></scanList></spectrum>""")
    source = Spectrum(xml)
    report = conversion_report(source)
    codes = {item["code"] for item in report["issues"]}
    assert {"omitted_attribute", "unresolved_reference", "omitted_user_param"} <= codes
    assert report["preserved"]["user_params"] == 1
    assert report["preserved"]["cv_params"] == 1
    with pytest.raises(ValueError, match="omit data"):
        conversion_report(source, strict=True)


def test_mzml_cli_reports_real_fixture():
    result = cli("convert-mzml", "tests/data/example.mzML")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["encoding"]["token"].startswith("spectrl.v1.")
    assert "preserved" in report and "issues" in report
