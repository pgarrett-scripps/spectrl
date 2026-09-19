"""Exercise public workflows from an installed wheel, without optional extras."""

from spectrl import (
    DecodeLimits,
    SpectrlDecodeError,
    decode_token,
    encoding_report,
    fit_to_budget,
    format_peak_list,
    parse_peak_list,
)

source = parse_peak_list("mz,intensity\n100.123456,10\n200.123456,20")
report = encoding_report(source, lossless=True)
assert report["token"].startswith("spectrl.v3.")
assert report["all_arrays_exact"]
assert decode_token(report["token"], limits=DecodeLimits(max_decoded_bytes=32)).default_array_length == 2
try:
    decode_token(report["token"], limits=DecodeLimits(max_decoded_bytes=31))
except SpectrlDecodeError:
    pass
else:
    raise AssertionError("Installed wheel ignored decoder limits")
assert parse_peak_list(format_peak_list(decode_token(report["token"]))).default_array_length == 2
assert fit_to_budget(source, 1000)["dropped_peaks"] == 0
assert encoding_report(source, array_encodings={"mz": "raw"})["arrays"][0]["encoding"] == [0, 1]
print("Installed wheel workflows passed")
