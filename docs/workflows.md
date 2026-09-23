**Quality, sharing, and conversion workflows**

These APIs use the `spectrl.v3` format. They do not require a service. Python uses snake_case names and TypeScript uses camelCase names.

**Measure encoding quality**

```python
from spectrl import parse_peak_list, encoding_report

source = parse_peak_list("mz,intensity\n200.123456,20\n100.123456,10")
report = encoding_report(source)
print(report["token_bytes"])
print(report["arrays"][0]["max_error_ppm"])
token = report["token"]
```

`encoding_report` accepts the `encode_spectrum` codec, lossless, unsafe-custom and user-param options, excluding `max_len`. It returns the exact token measured, peak count, raw array byte count, per-array compressed bytes, codec and dtype information, and maximum absolute and relative errors. The m/z entry also includes maximum and mean error in ppm. Each entry reports whether the array is bit-exact, including dtype and signed zero.

The comparison uses the same stable m/z ordering as the encoder and retains the alignment of every parallel array. Relative-error statistics exclude zero reference values. `zero_reference_values` and `changed_zero_values` make those cases visible. A relative statistic with no nonzero references is `None` in Python and `null` in JSON. A metric too large for a finite float64 is also unavailable. Negative intensities use an absolute denominator. Empty arrays have zero maximum absolute error.

`omitted_user_params` counts user parameters at all modeled locations removed by an explicit `drop_user_params=True` option. The report measures array encoding error, not peak-selection quality or all possible mzML metadata loss. Use the conversion report for mzML omissions. A token alone cannot reveal its error relative to an unavailable original spectrum.

```typescript
import { parsePeakList, encodingReport } from "@spectrl-ms/spectrl"

const source = parsePeakList("100.123456 10\n200.123456 20")
const report = encodingReport(source, { lossless: false })
console.log(report.tokenBytes, report.arrays[0]?.maxErrorPpm)
```

**Fit a token or complete URL to a budget**

```python
from spectrl import fit_to_budget

candidate = fit_to_budget(
    source,
    2000,
    base_url="https://viewer.example.com/spectrum",
    allow_peak_trimming=True,
    drop_user_params=False,
    min_peaks=1,
)
print(candidate["carrier_bytes"], candidate["dropped_peaks"])
print(candidate["omitted_user_params"])
url = candidate["carrier"]
```

Without `base_url`, the budget measures the token. With it, the budget measures the complete fragment URL in UTF-8 bytes, replacing any existing fragment. The result includes `spectrum`, `token`, `carrier`, measured bytes, original and retained peak counts, and explicit omission counts. Input data is not mutated. Metadata and all auxiliary arrays remain aligned with selected peaks.

Peak removal requires `allow_peak_trimming=True`. Free-text removal separately requires `drop_user_params=True`. If these permissions do not allow a candidate to fit, the call fails. It never quietly discards additional metadata. Trimming requires an intensity array and uses the existing deterministic highest-intensity selection policy. Negative intensities are ranked by signed value. `min_peaks=0` explicitly permits an empty result.

The bounded search measures each candidate's actual compressed size. Because compression is not monotonic in peak count, it returns a fitting candidate rather than guaranteeing the greatest mathematically possible retained count. A failure at the requested minimum is conservative and does not prove that no unusual larger compressed candidate could fit. A byte budget is not a universal guarantee of QR readability or acceptance by every receiving service.

```typescript
import { fitToBudget } from "@spectrl-ms/spectrl"

const candidate = fitToBudget(source, 2000, {
  baseUrl: "https://viewer.example.com/spectrum",
  allowPeakTrimming: true,
  dropUserParams: false,
  minPeaks: 1,
})
console.log(candidate.carrier, candidate.droppedPeaks)
```

**Import and export peak lists**

`parse_peak_list` / `parsePeakList` accepts two numeric columns separated by whitespace, commas, or tabs. An optional `mz,intensity` or `m/z,intensity` header is recognized. Empty lines and lines beginning with `#` are ignored. The parser preserves input order and negative intensities, rejects negative m/z and non-finite values, and reports the line number for malformed rows. Extra columns are rejected. Quoted CSV numbers and headers are supported. This is a two-column importer, not a general spreadsheet or MGF parser.

`format_peak_list` / `formatPeakList` exports those two arrays with an optional comma, tab, or space delimiter. It intentionally omits metadata and auxiliary arrays. Use tokens or spectrum JSON for those fields.

**Spectrum JSON and typed arrays**

Python `spectrum_to_dict` produces JSON-compatible arrays and an `extra_array_dtypes` object mapping each custom-array key to `int32`, `float32`, or `float64`. `spectrum_from_dict` restores those dtypes and validates their numeric ranges. Existing plain-list JSON remains supported, with custom arrays interpreted as float64 when dtype metadata is absent. The dtype metadata belongs to the JSON representation, not the token format. Core arrays retain float32, float64, or int32 through `array_dtypes`. Plain lists default to float64. Byte strings and non-string map keys in opaque extensions use the tagged JSON forms documented in the README.

**Report mzML conversion fidelity**

```python
from mzmlpy.run import Mzml
from spectrl import conversion_report, encoding_report

with Mzml("data.mzML") as mzml:
    conversion = conversion_report(
        mzml.spectra[0],
        run=mzml,
    )
    for issue in conversion["issues"]:
        print(issue["severity"], issue["path"], issue["message"])
    encoded = encoding_report(conversion["spectrum"])
```

The conversion result contains the spectrum, preserved peak/array/CV/user-param counts, and structured issues with `code`, XML `path`, `severity`, and `message`. It identifies unresolved reference groups, unsupported user-param locations, unmodeled elements, and omitted attributes. Provenance attributes such as an mzML spectrum index are informational. `strict=True` rejects warning-level omissions. The existing `from_mzmlpy(..., strict=True)` uses the same warning checks.

Pass `run=mzml` to resolve relevant source, instrument, software, and processing references. The report identifies observable omissions in the selected spectrum and reference context. It does not audit every semantic distinction in a complete mzML run. The bridge is a Python feature and requires `pip install "spectrl[mzml]"`.

**CLI examples**

```bash
spectrl encode peaks.csv --input-format csv
spectrl report peaks.tsv --input-format tsv --lossless
spectrl fit spectrum.json --max-bytes 2000 --allow-peak-trimming --base-url https://viewer.example.com/spectrum
spectrl decode token.txt --output-format tsv
spectrl convert-mzml data.mzML --index 0
spectrl inspect token.txt
```

`decode` and `inspect` also accept a carrier URL read from their input file or stdin. `fit`, `report`, and `convert-mzml` return JSON. The `fit` result contains the selected spectrum JSON, and the conversion result includes its encoding quality report. `encode` returns the token alone. Invalid inputs return a nonzero exit code and a concise error on stderr.

**Browser workflow**

The demo page (`index.html`) puts one spectrum on the page. Select an example, toggle the lossless checkbox to re-encode it, and copy the token, the shareable link, or the QR code. The metadata carried in the token, the encoding details, and the quality report are shown below the plot, and the report can be downloaded for spectra encoded in the page. Pasted tokens have no known source for an error measurement.

The Convert page (`convert.html`) reads an mzML, MGF, or MS2 file, or a pasted peak list, and encodes the selected spectrum into a token. The displayed spectrum can be written back out as mzML, MGF, MS2, or a TSV peak list. Files never leave the browser.

The plot displays at most 5,000 peaks to keep rendering bounded. This visual limit does not trim tokens or exports. The Brotli payload backend loads when a token needs it. Both default profiles use zlib payload compression.

V3 records peak selection and user-parameter omission in processing history.
Known prior lossy encoding history survives later exact recompression. Sorting
or selecting arrays with attached extensions requires the caller to update or
remove those extensions explicitly. Inspection works without custom codecs,
but full decoding requires registered implementations and required extensions.
