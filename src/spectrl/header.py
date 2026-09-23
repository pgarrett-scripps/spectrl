"""CBOR header build/parse for the spectrl integer-key registry.

Top-level key registry (mirrors mzML <spectrum>):
  0  defaultArrayLength (int)
  1  @id (str, optional)
  2  spectrum param map
  3  scanList: {c?: combination-flag-tail, s: [scan, ...]}
  4  precursorList: [precursor, ...]
  5  productList: [product, ...]
  6  binaryDataArrayList: [descriptor, ...]
  7  userParamList: [user_param, ...] spectrum-level free-text params (optional)
 12  cv_versions: {ontology prefix: source-declared version} (optional)

The format version lives only in the token magic, and the checksum only
in the trailing token part; neither is a header key.

A user_param is a map {"n": name, "v"?: value, "u"?: unit}.
Scan maps gain key 2 for scan-level user_params (optional).

Array descriptors (key 6) use integer keys for the same reason the header does:
the names were a fixed vocabulary spelled out in full on every array of every
token, costing more than the values they labelled.
"""

from __future__ import annotations

import re

from ._format import DESC_ARRAY as DESC_ARRAY
from ._format import DESC_DATA as DESC_DATA
from ._format import DESC_NAME as DESC_NAME
from ._format import DESC_TYPE as DESC_TYPE
from ._format import DESC_UNIT as DESC_UNIT
from .context import decode_record, encode_record, validate_extensions
from .cv import (
    _DEFAULT_PARAM_ONTOLOGY,
    accession_ontology,
    accession_tail,
    decode_tail,
    decode_unit_tail,
    encode_unit,
)
from .model import (
    DecodedSpectrum,
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
from .token import FORMAT_VERSION

_ACCESSION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9]+$")
# The ontology prefix alone, as it appears to the left of the colon in an
# accession. cv_versions is keyed by this, never by mzML's <cv> @id, which
# files spell inconsistently ("MS" in one, "PSI-MS" in another) while still
# writing MS: accessions throughout.
_PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


def _require_map(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a map")
    return value


def _require_list(value: object, label: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _validate_accession(accession: str) -> None:
    if not _ACCESSION_RE.fullmatch(accession):
        raise ValueError(f"invalid CV accession {accession!r}")


def _encode_cv_versions(versions: dict) -> dict:
    """Check the shape of the ontology version map and return it unchanged.

    Values stay opaque text. Real files declare versions as "4.1.142",
    "12:10:2011", and "releases/2020-03-10", so there is no syntax to parse and
    nothing is gained by trying.
    """
    out = {}
    for prefix, version in _require_map(versions, "cv_versions").items():
        if not isinstance(prefix, str) or not _PREFIX_RE.fullmatch(prefix):
            raise ValueError(f"invalid ontology prefix {prefix!r}")
        if not isinstance(version, str) or not version:
            raise ValueError(f"ontology version for {prefix} must be nonempty text")
        out[prefix] = version
    return out


def _decode_cv_versions(raw: object) -> dict:
    """Decode key 12. Provenance only, so a reader never rejects a token over
    the version it names; only a malformed map is an error."""
    return _encode_cv_versions(raw)


# ─── CvParam encoding ───────────────────────────────────────────────────────


def _encode_cvparam(p: SpectrlCvParam) -> tuple[int | str, object]:
    """Encode a SpectrlCvParam into (tail_key, value) suitable for a CBOR map."""
    _validate_accession(p.accession)
    if p.unit_accession is not None:
        _validate_accession(p.unit_accession)
    if p.value is not None and (isinstance(p.value, bool) or not isinstance(p.value, (str, int, float))):
        raise ValueError(f"unsupported CV value type for {p.accession}: {type(p.value).__name__}")
    onto = accession_ontology(p.accession)

    # MS: keys with 7-digit tails are bare integer tails. Anything else (other
    # ontologies, or a tail that would not survive 7-digit zero-padded
    # reconstruction, e.g. 'NCIT:C25330') uses the full accession string.
    tail_str = p.accession.split(":", 1)[1] if ":" in p.accession else ""
    if onto == _DEFAULT_PARAM_ONTOLOGY and tail_str.isdigit() and len(tail_str) == 7:
        tail_key: int | str = int(tail_str)
    else:
        tail_key = p.accession

    if p.unit_accession is not None:
        val = [p.value, encode_unit(p.unit_accession)]
    else:
        val = p.value

    return tail_key, val


def _encode_param_map(params: list[SpectrlCvParam]) -> list:
    """Ordered pairs preserve repeated CV terms without duplicate CBOR map keys."""
    return [list(_encode_cvparam(p)) for p in params]


def _decode_param_map(raw) -> list[SpectrlCvParam]:
    _require_list(raw, "CV parameter list")
    out = []
    for item in raw:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("CV parameter record must have two members")
        key, value = item
        if isinstance(key, str):
            accession = key
        elif type(key) is int and 0 <= key <= 9999999:
            accession = decode_tail(key)
        else:
            raise ValueError("invalid CV parameter accession")
        _validate_accession(accession)
        unit = None
        if isinstance(value, list):
            if len(value) != 2:
                raise ValueError("invalid CV value and unit pair")
            value, raw_unit = value
            unit = decode_unit_tail(raw_unit)
        if value is not None and (type(value) not in (str, int, float)):
            raise ValueError("invalid CV scalar value")
        import math

        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("CV numbers must be finite")
        if type(value) is int and abs(value) > 9007199254740991:
            raise ValueError("CV integer exceeds safe range")
        out.append(SpectrlCvParam(accession, value, unit))
    return out


# ─── UserParam encoding ──────────────────────────────────────────────────────


def _encode_user_param(u: SpectrlUserParam) -> dict:
    """Encode a SpectrlUserParam as a compact map; absent fields are omitted."""
    if not isinstance(u.name, str) or not u.name:
        raise ValueError("user parameter name must be a non-empty string")
    _scalar(u.value)
    if u.unit_accession is not None:
        _validate_accession(u.unit_accession)
    m: dict = {"n": u.name}
    if u.value is not None:
        m["v"] = u.value
    if u.unit_accession is not None:
        m["u"] = encode_unit(u.unit_accession)
    return m


def _encode_user_params(us: list[SpectrlUserParam]) -> list[dict]:
    return [_encode_user_param(u) for u in us]


def _decode_user_params(raw: list[dict]) -> list[SpectrlUserParam]:
    _require_list(raw, "user parameter list")
    out: list[SpectrlUserParam] = []
    for m in raw:
        _shape(m, ["n", "v", "u"], "user parameter")
        _scalar(m.get("v"))
        if not isinstance(m.get("n"), str) or not m["n"]:
            raise ValueError("user parameter name must be a non-empty string")
        out.append(
            SpectrlUserParam(
                name=m["n"],
                value=m.get("v"),
                unit_accession=decode_unit_tail(m["u"]) if "u" in m else None,
            )
        )
    return out


# ─── Scan/ScanWindow encoding ────────────────────────────────────────────────


def _encode_group(value):
    out = {0: _encode_param_map(value.params)}
    if value.user_params:
        out[1] = _encode_user_params(value.user_params)
    return out


def _decode_group(value, cls):
    _require_map(value, "parameter group")
    if any(type(k) is not int or k not in (0, 1) for k in value):
        raise ValueError("unknown parameter group key")
    return cls(params=_decode_param_map(value.get(0, [])), user_params=_decode_user_params(value.get(1, [])))


def _encode_scan_window(w):
    return _encode_group(w)


def _decode_scan_window(d):
    return _decode_group(d, SpectrlScanWindow)


def _context_out(value, out):
    if value.source is not None:
        out[3] = encode_record(value.source, "source")
    if value.acquisition is not None:
        out[4] = encode_record(value.acquisition, "acquisition")
    if value.processing:
        out[5] = [encode_record(x, "processing") for x in value.processing]
    return out


def _context_in(d):
    _require_list(d.get(5, []), "processing")
    return dict(
        source=decode_record(d[3], "source") if 3 in d else None,
        acquisition=decode_record(d[4], "acquisition") if 4 in d else None,
        processing=[decode_record(x, "processing") for x in d.get(5, [])],
    )


def _encode_scan(s):
    d = {0: _encode_param_map(s.params)}
    if s.windows:
        d[1] = [_encode_scan_window(w) for w in s.windows]
    if s.user_params:
        d[2] = _encode_user_params(s.user_params)
    return _context_out(s, d)


def _decode_scan(d):
    _shape(d, range(6), "scan")
    _require_list(d.get(1, []), "scan windows")
    return SpectrlScan(
        params=_decode_param_map(d.get(0, [])),
        windows=[_decode_scan_window(w) for w in d.get(1, [])],
        user_params=_decode_user_params(d.get(2, [])),
        **_context_in(d),
    )


# ─── Precursor/Product encoding ──────────────────────────────────────────────


def _encode_isolation_window(iw: SpectrlIsolationWindow) -> dict:
    return _encode_group(iw)


def _decode_isolation_window(d: dict) -> SpectrlIsolationWindow:
    return _decode_group(d, SpectrlIsolationWindow)


def _encode_precursor(p: SpectrlPrecursor) -> dict:
    d: dict = {}
    if p.isolation_window is not None:
        d[0] = _encode_isolation_window(p.isolation_window)
    if p.selected_ions:
        d[1] = [_encode_group(si) for si in p.selected_ions]
    if p.activation is not None:
        d[2] = _encode_group(p.activation)
    return _context_out(p, d)


def _decode_precursor(d: dict) -> SpectrlPrecursor:
    _shape(d, range(6), "precursor")
    _require_list(d.get(1, []), "selected ions")
    iw = _decode_isolation_window(d[0]) if 0 in d else None
    selected_ions = [_decode_group(si, SpectrlSelectedIon) for si in d.get(1, [])]
    activation = _decode_group(d[2], SpectrlActivation) if 2 in d else None
    return SpectrlPrecursor(isolation_window=iw, selected_ions=selected_ions, activation=activation, **_context_in(d))


def _encode_product(p: SpectrlProduct) -> dict:
    d: dict = {}
    if p.isolation_window is not None:
        d[0] = _encode_isolation_window(p.isolation_window)
    return d


def _decode_product(d: dict) -> SpectrlProduct:
    _shape(d, [0], "product")
    iw = _decode_isolation_window(d[0]) if 0 in d else None
    return SpectrlProduct(isolation_window=iw)


# ─── Full header build/parse ─────────────────────────────────────────────────


def build_header_dict(spec: InlineSpectrum, descriptors: list[dict]) -> dict:
    """Build the integer-keyed header map (integer-keyed CBOR map)."""
    h: dict = {
        # int() coerces numpy integer scalars, which cbor2 cannot encode
        0: int(spec.default_array_length),
    }
    if spec.id is not None:
        h[1] = spec.id
    if spec.params:
        h[2] = _encode_param_map(spec.params)
    if spec.scans or spec.scan_combination is not None:
        scan_entry: dict = {"s": [_encode_scan(s) for s in spec.scans]}
        if spec.scan_combination is not None:
            # Combination terms (MS:1000795 etc.) are pure flags; only the
            # accession tail is carried.
            scan_entry["c"] = accession_tail(spec.scan_combination.accession)
        h[3] = scan_entry
    if spec.precursors:
        h[4] = [_encode_precursor(p) for p in spec.precursors]
    if spec.products:
        h[5] = [_encode_product(p) for p in spec.products]
    h[6] = descriptors
    if spec.user_params:
        h[7] = _encode_user_params(spec.user_params)
    if spec.source is not None:
        h[8] = encode_record(spec.source, "source")
    if spec.acquisition is not None:
        h[9] = encode_record(spec.acquisition, "acquisition")
    if spec.processing:
        h[10] = [encode_record(x, "processing") for x in spec.processing]
    if spec.extensions:
        validate_extensions(spec.extensions, require_supported=False)
        h[11] = spec.extensions
    if spec.cv_versions:
        h[12] = _encode_cv_versions(spec.cv_versions)
    return h


def parse_header_dict(h: dict) -> DecodedSpectrum:
    """Build a DecodedSpectrum from a parsed CBOR header map.

    The format version lives in the token magic and the checksum in the
    trailing token part, so neither appears here; decode_cbor fills them in.
    """
    default_array_length = h[0]
    id_ = h.get(1)
    params = _decode_param_map(h.get(2, []))

    scans: list[SpectrlScan] = []
    scan_combination: SpectrlCvParam | None = None
    scan_entry = h.get(3, {})
    _shape(scan_entry, ["s", "c"], "scan list")
    _require_list(scan_entry.get("s", []), "scans")
    if scan_entry:
        scans = [_decode_scan(s) for s in scan_entry.get("s", [])]
        if "c" in scan_entry:
            combo_tail = scan_entry["c"]
            if type(combo_tail) is not int or not 0 <= combo_tail <= 9999999:
                raise ValueError("invalid scan combination")
            scan_combination = SpectrlCvParam(accession=decode_tail(combo_tail))

    precursors = [_decode_precursor(p) for p in h.get(4, [])]
    products = [_decode_product(p) for p in h.get(5, [])]
    user_params = _decode_user_params(h.get(7, []))

    return DecodedSpectrum(
        default_array_length=default_array_length,
        id=id_,
        params=params,
        scans=scans,
        scan_combination=scan_combination,
        precursors=precursors,
        products=products,
        user_params=user_params,
        source=decode_record(h[8], "source") if 8 in h else None,
        acquisition=decode_record(h[9], "acquisition") if 9 in h else None,
        processing=[decode_record(x, "processing") for x in h.get(10, [])],
        extensions=h.get(11, {}),
        cv_versions=_decode_cv_versions(h.get(12, {})),
        format_version=FORMAT_VERSION,
    )


def _scalar(value):
    import math

    if value is None or isinstance(value, str):
        return
    if (
        type(value) in (int, float)
        and math.isfinite(value)
        and (not isinstance(value, int) or abs(value) <= 9007199254740991)
    ):
        return
    raise ValueError("invalid parameter scalar")


def _shape(value, keys, label):
    _require_map(value, label)
    if any(isinstance(k, bool) or k not in keys for k in value):
        raise ValueError(f"unsupported {label} field")
