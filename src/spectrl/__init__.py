"""spectrl: Inline Spectrum URL Encoder.

Encodes a single mass spectrum into a compact, URL-safe token (spectrl.v1.…) so it can be
shared with no backend. The entire spectrum lives in the token.

Public API::

    encode_spectrum(spec, *, lossless=False, max_len=None) -> str
    decode_token(token) -> DecodedSpectrum
    from_mzmlpy(spec, ref_groups=None) -> InlineSpectrum
    top_n(spec, n) -> InlineSpectrum
    to_fragment(token, base) -> str
    to_query(token, base, param="d") -> str
    to_data_uri(token) -> str
    extract_token(url_or_uri) -> str
"""

from __future__ import annotations

import warnings
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse

from .array_accession import ArrayAccession
from .cbor_format import decode_cbor, encode_cbor
from .compression_accession import CompressionAccession
from .errors import SpectrlDecodeError, SpectrlError
from .introspection import encoding_plan, inspect_token
from .model import ArrayEncoding, DecodedSpectrum, InlineSpectrum, SpectrlCvParam, SpectrlUserParam
from .peaklist import format_peak_list, parse_peak_list
from .peaks import top_n
from .serialization import spectrum_from_dict, spectrum_to_dict
from .unit_accession import UnitAccession
from .workflows import encoding_report, fit_to_budget

__all__ = [
    "encode_spectrum",
    "decode_token",
    "from_mzmlpy",
    "top_n",
    "to_fragment",
    "to_query",
    "to_data_uri",
    "extract_token",
    "InlineSpectrum",
    "DecodedSpectrum",
    "SpectrlCvParam",
    "SpectrlUserParam",
    "ArrayEncoding",
    "ArrayAccession",
    "CompressionAccession",
    "UnitAccession",
    "encoding_report",
    "fit_to_budget",
    "parse_peak_list",
    "format_peak_list",
    "conversion_report",
    "encoding_plan",
    "inspect_token",
    "spectrum_from_dict",
    "spectrum_to_dict",
    "SpectrlError",
    "SpectrlDecodeError",
]

_SIZE_WARN = 8192  # bytes; warn past this
_MAGIC_PREFIX = "spectrl.v1."
_DATA_URI_PREFIX = "data:application/vnd.spectrl;v=1,"


def encode_spectrum(
    spec: InlineSpectrum,
    *,
    lossless: bool = False,
    max_len: int | None = None,
    drop_user_params: bool = False,
    array_encodings: dict[str, ArrayEncoding | str | int | dict] | None = None,
    allow_unsafe_lossy_custom: bool = False,
) -> str:
    """Encode an InlineSpectrum to a spectrl.v1 token string.

    The token is a single CBOR document (header + array blobs embedded as byte
    strings), base64url-encoded after the ``spectrl.v1.`` magic.

    Args:
        spec: The spectrum to encode.
        lossless: If True, use raw IEEE-754 + zlib (bit-exact). Default is lossy
            MS-Numpress (recommended for URL sharing).
        max_len: Raise OverflowError if the encoded token exceeds this byte length.
            Use top_n() to reduce peak count before encoding.
        drop_user_params: If True, omit free-text user params at both spectrum and
            scan level. Vendor trailers (instrument filter strings, preset scan
            configuration) are often a large share of a small MS2 token and
            usually restate CV params the token already carries. The result is a
            conforming token; the omitted values are not recoverable from it.
        array_encodings: Optional per-array codec overrides. Keys are a core
            friendly name (``"mz"``, ``"intensity"``, ``"charge"``), its
            ArrayAccession alias, or an exact ``extra_arrays`` key. Values may
            be an ArrayEncoding, codec name, compression accession tail, or
            ``{"codec": ..., "fixed_point": ...}``.
        allow_unsafe_lossy_custom: Permit an explicitly selected lossy codec
            for an unknown or non-standard array. Its semantic suitability is
            the caller's responsibility. Known incompatible arrays still fail.

    Returns:
        A ``spectrl.v1.`` token string.

    Raises:
        OverflowError: If max_len is set and the encoded length exceeds it.
        ValueError: If arrays contain NaN/Inf, or peaks are not finite.
    """
    token = encode_cbor(
        spec,
        lossless=lossless,
        drop_user_params=drop_user_params,
        array_encodings=array_encodings,
        allow_unsafe_lossy_custom=allow_unsafe_lossy_custom,
    )

    if len(token) > _SIZE_WARN:
        warnings.warn(
            f"spectrl token length {len(token)} bytes exceeds recommended maximum of {_SIZE_WARN} bytes. "
            "Consider using top_n() to reduce peak count.",
            UserWarning,
            stacklevel=2,
        )

    if max_len is not None and len(token) > max_len:
        raise OverflowError(
            f"Encoded spectrl token is {len(token)} bytes, which exceeds max_len={max_len}. "
            "Use top_n(spec, n) to reduce peak count before encoding."
        )

    return token


def decode_token(token: str) -> DecodedSpectrum:
    """Decode a spectrl.v1 token string into a DecodedSpectrum.

    Verifies the mandatory trailing CRC-32 checksum.

    Raises:
        SpectrlDecodeError: On any malformed, corrupted, or unsupported input:
            bad magic, invalid base64url/CBOR, unsupported format version, checksum
            mismatch, unknown codec, or array/length inconsistencies.
            SpectrlDecodeError subclasses ValueError.
    """
    return decode_cbor(token)


def from_mzmlpy(spec, ref_groups: dict | None = None, *, strict: bool = False) -> InlineSpectrum:
    """Convert a mzmlpy Spectrum to InlineSpectrum.

    Args:
        spec: A mzmlpy.spectra.Spectrum.
        ref_groups: Optional dict mapping group id → mzmlpy _ParamGroup, for
            expanding referenceableParamGroupRef elements. Pass
            ``mzml.referenceable_param_groups``.
        strict: Raise rather than silently omit unresolved referenceable
            parameter groups or userParams in mzML locations spectrl.v1 cannot
            represent.

    Returns:
        InlineSpectrum ready for encoding.
    """
    try:
        from .mzml import from_mzmlpy as _bridge
    except ModuleNotFoundError as exc:
        if exc.name == "mzmlpy" or (exc.name and exc.name.startswith("mzmlpy.")):
            raise ModuleNotFoundError(
                'from_mzmlpy() requires the optional mzmlpy integration; install it with pip install "spectrl[mzml]"'
            ) from exc
        raise

    return _bridge(spec, ref_groups=ref_groups, strict=strict)


# ─── URL binding helpers ─────────────────────────────────────────────────────


def to_fragment(token: str, base: str) -> str:
    """Wrap a token as a URL fragment: ``base#token``.

    The fragment is never sent to the server, avoiding length limits and access logs.
    """
    return urlunparse(urlparse(base)._replace(fragment=token))


def to_query(token: str, base: str, param: str = "d") -> str:
    """Wrap a token as a URL query parameter, preserving existing query params.

    Token characters (base64url + '.') are quote-safe, so the token survives
    unescaped.
    """
    parsed = urlparse(base)
    pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != param]
    pairs.append((param, token))
    return urlunparse(parsed._replace(query=urlencode(pairs)))


def to_data_uri(token: str) -> str:
    """Wrap a token in a ``data:application/vnd.spectrl;v=1,`` URI."""
    return f"{_DATA_URI_PREFIX}{token}"


def extract_token(url_or_uri: str) -> str:
    """Extract a spectrl.v1 token from a URL fragment, query string, or data: URI.

    Raises ValueError if no token is found.
    """
    if url_or_uri.startswith(_DATA_URI_PREFIX):
        return url_or_uri[len(_DATA_URI_PREFIX) :]

    parsed = urlparse(url_or_uri)

    if parsed.fragment.startswith(_MAGIC_PREFIX):
        return parsed.fragment

    # Check query params for any value starting with spectrl.v1.
    qs = parse_qs(parsed.query)
    for vals in qs.values():
        for v in vals:
            if v.startswith(_MAGIC_PREFIX):
                return v

    raise ValueError(f"No spectrl.v1 token found in: {url_or_uri!r}")


def conversion_report(spec, ref_groups: dict | None = None, *, strict: bool = False) -> dict:
    """Convert an mzML spectrum with a structured fidelity report. Requires the mzml extra."""
    try:
        from .mzml import conversion_report as report
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("mzmlpy"):
            raise ModuleNotFoundError('conversion_report requires pip install "spectrl[mzml]"') from exc
        raise
    return report(spec, ref_groups, strict=strict)
