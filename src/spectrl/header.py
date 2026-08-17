"""CBOR header build/parse for the spectrl integer-key registry.

Top-level key registry (mirrors mzML <spectrum>):
  0  defaultArrayLength (int)
  1  @id (str, optional)
  2  spectrum param map
  3  scanList: {c?: combination-flag-tail, s: [scan, ...]}
  4  precursorList: [precursor, ...]
  5  productList: [product, ...]
  6  binaryDataArrayList: [descriptor, ...]
  7  interp: ProForma string (optional)
  8  userParamList: [user_param, ...] spectrum-level free-text params (optional)

The format version lives only in the token magic, and the checksum only
in the trailing token part; neither is a header key.

A user_param is a map {"n": name, "v"?: value, "t"?: xsd-type, "u"?: unit}.
Scan maps gain key 2 for scan-level user_params (optional).

Array descriptors (key 6) use integer keys for the same reason the header does:
the names were a fixed vocabulary spelled out in full on every array of every
token, costing more than the values they labelled.
"""

from __future__ import annotations

import re

from ._format import DESC_ARRAY as DESC_ARRAY
from ._format import DESC_COMP as DESC_COMP
from ._format import DESC_DATA as DESC_DATA
from ._format import DESC_FP as DESC_FP
from ._format import DESC_NAME as DESC_NAME
from ._format import DESC_TYPE as DESC_TYPE
from ._format import DESC_UNIT as DESC_UNIT
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

    if p.value is None:
        val = None
    elif p.unit_accession is not None:
        val = [p.value, encode_unit(p.unit_accession)]
    else:
        val = p.value

    return tail_key, val


def _encode_param_map(params: list[SpectrlCvParam]) -> dict:
    """Encode a list of CvParams into an integer-keyed map.

    The map is keyed by accession, so repeated accessions are not representable
    and are rejected rather than silently losing scientific metadata.
    """
    m: dict = {}
    for p in params:
        key, val = _encode_cvparam(p)
        if key in m:
            raise ValueError(f"duplicate CV accession {p.accession} in parameter list")
        m[key] = val
    return m


def _decode_param_map(m: dict) -> list[SpectrlCvParam]:
    """Decode an integer-keyed param map into a list of SpectrlCvParam."""
    _require_map(m, "CV parameter list")
    params = []
    for raw_key, raw_val in m.items():
        if isinstance(raw_key, str):
            accession = raw_key
            _validate_accession(accession)
        elif isinstance(raw_key, int) and not isinstance(raw_key, bool) and raw_key >= 0:
            accession = decode_tail(raw_key)
        else:
            raise ValueError(f"invalid CV parameter key {raw_key!r}")

        if raw_val is None:
            params.append(SpectrlCvParam(accession=accession))
        elif isinstance(raw_val, list):
            if len(raw_val) != 2:
                raise ValueError(f"CV parameter {accession} value/unit pair must have two items")
            value = raw_val[0]
            unit_accession = decode_unit_tail(raw_val[1])
            params.append(SpectrlCvParam(accession=accession, value=value, unit_accession=unit_accession))
        else:
            params.append(SpectrlCvParam(accession=accession, value=raw_val))
    return params


# ─── UserParam encoding ──────────────────────────────────────────────────────


def _encode_user_param(u: SpectrlUserParam) -> dict:
    """Encode a SpectrlUserParam as a compact map; absent fields are omitted."""
    if not isinstance(u.name, str) or not u.name:
        raise ValueError("user parameter name must be a non-empty string")
    if u.unit_accession is not None:
        _validate_accession(u.unit_accession)
    m: dict = {"n": u.name}
    if u.value is not None:
        m["v"] = u.value
    if u.type is not None:
        m["t"] = u.type
    if u.unit_accession is not None:
        m["u"] = encode_unit(u.unit_accession)
    return m


def _encode_user_params(us: list[SpectrlUserParam]) -> list[dict]:
    return [_encode_user_param(u) for u in us]


def _decode_user_params(raw: list[dict]) -> list[SpectrlUserParam]:
    _require_list(raw, "user parameter list")
    out: list[SpectrlUserParam] = []
    for m in raw:
        _require_map(m, "user parameter")
        if not isinstance(m.get("n"), str) or not m["n"]:
            raise ValueError("user parameter name must be a non-empty string")
        out.append(
            SpectrlUserParam(
                name=m["n"],
                value=m.get("v"),
                type=m.get("t"),
                unit_accession=decode_unit_tail(m["u"]) if "u" in m else None,
            )
        )
    return out


# ─── Scan/ScanWindow encoding ────────────────────────────────────────────────


def _encode_scan_window(w: SpectrlScanWindow) -> dict:
    return _encode_param_map(w.params)


def _decode_scan_window(d: dict) -> SpectrlScanWindow:
    return SpectrlScanWindow(params=_decode_param_map(d))


def _encode_scan(s: SpectrlScan) -> dict:
    d: dict = {0: _encode_param_map(s.params)}
    if s.windows:
        d[1] = [_encode_scan_window(w) for w in s.windows]
    if s.user_params:
        d[2] = _encode_user_params(s.user_params)
    return d


def _decode_scan(d: dict) -> SpectrlScan:
    params = _decode_param_map(d.get(0, {}))
    windows = [_decode_scan_window(w) for w in d.get(1, [])]
    user_params = _decode_user_params(d.get(2, []))
    return SpectrlScan(params=params, windows=windows, user_params=user_params)


# ─── Precursor/Product encoding ──────────────────────────────────────────────


def _encode_isolation_window(iw: SpectrlIsolationWindow) -> dict:
    return _encode_param_map(iw.params)


def _decode_isolation_window(d: dict) -> SpectrlIsolationWindow:
    return SpectrlIsolationWindow(params=_decode_param_map(d))


def _encode_precursor(p: SpectrlPrecursor) -> dict:
    d: dict = {}
    if p.isolation_window is not None:
        d[0] = _encode_isolation_window(p.isolation_window)
    if p.selected_ions:
        d[1] = [_encode_param_map(si.params) for si in p.selected_ions]
    if p.activation is not None:
        d[2] = _encode_param_map(p.activation.params)
    return d


def _decode_precursor(d: dict) -> SpectrlPrecursor:
    iw = _decode_isolation_window(d[0]) if 0 in d else None
    selected_ions = [SpectrlSelectedIon(params=_decode_param_map(si)) for si in d.get(1, [])]
    activation = SpectrlActivation(params=_decode_param_map(d[2])) if 2 in d else None
    return SpectrlPrecursor(isolation_window=iw, selected_ions=selected_ions, activation=activation)


def _encode_product(p: SpectrlProduct) -> dict:
    d: dict = {}
    if p.isolation_window is not None:
        d[0] = _encode_isolation_window(p.isolation_window)
    return d


def _decode_product(d: dict) -> SpectrlProduct:
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
    if spec.interp is not None:
        h[7] = spec.interp
    if spec.user_params:
        h[8] = _encode_user_params(spec.user_params)
    return h


def parse_header_dict(h: dict) -> DecodedSpectrum:
    """Build a DecodedSpectrum from a parsed CBOR header map.

    The format version lives in the token magic and the checksum in the
    trailing token part, so neither appears here; decode_cbor fills them in.
    """
    default_array_length = h[0]
    id_ = h.get(1)
    params = _decode_param_map(h.get(2, {}))

    scans: list[SpectrlScan] = []
    scan_combination: SpectrlCvParam | None = None
    scan_entry = h.get(3, {})
    if scan_entry:
        scans = [_decode_scan(s) for s in scan_entry.get("s", [])]
        if "c" in scan_entry:
            combo_tail = scan_entry["c"]
            scan_combination = SpectrlCvParam(accession=decode_tail(combo_tail))

    precursors = [_decode_precursor(p) for p in h.get(4, [])]
    products = [_decode_product(p) for p in h.get(5, [])]
    interp = h.get(7)
    user_params = _decode_user_params(h.get(8, []))

    return DecodedSpectrum(
        default_array_length=default_array_length,
        id=id_,
        params=params,
        scans=scans,
        scan_combination=scan_combination,
        precursors=precursors,
        products=products,
        interp=interp,
        user_params=user_params,
        format_version=FORMAT_VERSION,
    )
