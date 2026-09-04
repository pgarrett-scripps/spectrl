"""Exercise public workflows from an installed wheel, without optional extras."""

from spectrl import decode_token, encoding_report, fit_to_budget, format_peak_list, parse_peak_list

source = parse_peak_list("mz,intensity\n100.123456,10\n200.123456,20")
report = encoding_report(source, lossless=True)
assert report["all_arrays_exact"]
assert parse_peak_list(format_peak_list(decode_token(report["token"]))).default_array_length == 2
assert fit_to_budget(source, 1000)["dropped_peaks"] == 0
assert encoding_report(source, array_encodings={"mz": "zstd"})["arrays"][0]["compression_accession"] == "MS:1003780"
print("Installed wheel workflows passed")
