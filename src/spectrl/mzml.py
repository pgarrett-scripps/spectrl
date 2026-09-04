"""Bridge from mzmlpy.spectra.Spectrum to InlineSpectrum.

Tree-walk rules:
  NAMED REGISTRY KEYS: default_array_length (key 0), id (key 1).
  CV: everything from cv_params on spectrum, scans, scan windows, precursors, products.
  USER PARAMS: free-text userParams on the spectrum and on each scan.
  PEAK ARRAYS: mz, intensity, and charge as dedicated fields; all other
  standard arrays, including every ion-mobility variant, keyed by accession.
  EXPAND: ref_params dereferenced via optional ref_group lookup; their cvParams emitted.
  DROP: index, source_file_ref, data_processing_ref, ns, spot_id.
"""

from __future__ import annotations

from mzmlpy.elems.params import CvParam

from .model import (
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

_PRIMARY_ARRAYS = {"MS:1000514", "MS:1000515", "MS:1000516"}
_NON_STANDARD_ARRAY = "MS:1000786"


def _convert_cvparam(cv: CvParam) -> SpectrlCvParam:
    """Convert a mzmlpy CvParam to SpectrlCvParam.

    Numeric string values are coerced to float/int where possible.
    """
    value: float | int | str | None = None
    if cv.value is not None:
        try:
            f = float(cv.value)
            value = int(f) if f == int(f) else f
        except (ValueError, OverflowError):
            value = cv.value
    return SpectrlCvParam(
        accession=cv.accession,
        value=value,
        unit_accession=cv.unit_accession if cv.unit_accession else None,
    )


def _binary_array_unit(binary_array) -> str | None:
    """Return the unit attached to the array-defining cvParam, if present."""
    defining = next(
        (p for p in binary_array.cv_params if str(p.accession) == str(binary_array.binary_array_type)),
        None,
    )
    return str(defining.unit_accession) if defining is not None and defining.unit_accession else None


def _collect_arrays(spec) -> tuple[dict[str, object], dict[str, str]]:
    """Preserve auxiliary arrays and units for both core and auxiliary arrays."""
    extra_arrays = {}
    array_units: dict[str, str] = {}
    for binary_array in spec.binary_arrays:
        array_accession = str(binary_array.binary_array_type)
        unit = _binary_array_unit(binary_array)
        if array_accession in _PRIMARY_ARRAYS:
            if unit:
                array_units[
                    {"MS:1000514": "mz", "MS:1000515": "intensity", "MS:1000516": "charge"}[array_accession]
                ] = unit
            continue
        key = array_accession
        if array_accession == _NON_STANDARD_ARRAY:
            defining_param = next(
                (p for p in binary_array.cv_params if p.accession == _NON_STANDARD_ARRAY),
                None,
            )
            key = str(defining_param.value) if defining_param is not None and defining_param.value else "non-standard"
        if key in extra_arrays:
            raise ValueError(f"duplicate auxiliary binary array {key!r} in mzML spectrum {spec.id!r}")
        extra_arrays[key] = binary_array.data
        if unit:
            array_units[key] = unit
    return extra_arrays, array_units


def _collect_extra_arrays(spec) -> dict[str, object]:
    """Compatibility wrapper returning only auxiliary array values."""
    return _collect_arrays(spec)[0]


def _expand_ref_params(obj, ref_groups: dict | None, *, strict: bool = False) -> list[SpectrlCvParam]:
    """Resolve ref_params on an mzmlpy _ParamGroup object and return converted cvParams."""
    extra: list[SpectrlCvParam] = []
    if ref_groups is None:
        if strict and obj.ref_params:
            raise ValueError("unresolved referenceableParamGroupRef; pass ref_groups or disable strict mode")
        return extra
    for rp in obj.ref_params:
        group = ref_groups.get(rp.ref)
        if group is not None:
            for cv in group.cv_params:
                extra.append(_convert_cvparam(cv))
        elif strict:
            raise ValueError(f"unresolved referenceableParamGroupRef {rp.ref!r}")
    return extra


def _collect_cvparams(obj, ref_groups: dict | None, *, strict: bool = False) -> list[SpectrlCvParam]:
    """Return all cvParams from obj (including expanded ref_params)."""
    direct = [_convert_cvparam(cv) for cv in obj.cv_params]
    expanded = _expand_ref_params(obj, ref_groups, strict=strict)
    return direct + expanded


def _collect_user_params(obj) -> list[SpectrlUserParam]:
    """Read direct-child <userParam> elements off an mzmlpy element (free-text params).

    mzmlpy doesn't surface userParams as a property, so read them from the XML
    element directly (same approach the precursor walk uses for selectedIon).
    """
    el = getattr(obj, "element", None)
    ns = getattr(obj, "ns", "") or ""
    if el is None:
        return []
    out: list[SpectrlUserParam] = []
    for u in el.findall(f"./{ns}userParam"):
        value = u.get("value")
        out.append(
            SpectrlUserParam(
                name=u.get("name"),
                value=value if value not in (None, "") else None,
                type=u.get("type") or None,
                unit_accession=u.get("unitAccession") or None,
            )
        )
    return out


def from_mzmlpy(spec, ref_groups: dict | None = None, *, strict: bool = False) -> InlineSpectrum:
    """Convert a mzmlpy Spectrum to InlineSpectrum.

    Args:
        spec: A mzmlpy.spectra.Spectrum instance.
        ref_groups: Optional dict mapping group id → mzmlpy _ParamGroup for
            dereferencing referenceableParamGroupRef elements. Pass
            ``mzml.referenceable_param_groups`` if available.

    Returns:
        InlineSpectrum ready for encoding.
    """

    if strict:
        warnings = [item for item in _conversion_issues(spec, ref_groups) if item["severity"] == "warning"]
        if warnings:
            raise ValueError("mzML conversion would omit data: " + warnings[0]["message"])

    # ─── Spectrum-level CV params (EXPAND ref_params) + userParams ──────────
    spectrum_params = _collect_cvparams(spec, ref_groups, strict=strict)
    spectrum_user_params = _collect_user_params(spec)

    # ─── Scan list ───────────────────────────────────────────────────────────
    scans_out: list[SpectrlScan] = []
    scan_combination_out = None

    if spec._has_scan_list and spec._scan_list is not None:
        sl = spec._scan_list
        combo = sl.spectra_combination
        if combo is not None:
            scan_combination_out = SpectrlCvParam(accession=str(combo))

        for scan in sl.scans:
            scan_params = _collect_cvparams(scan, ref_groups, strict=strict)
            windows_out: list[SpectrlScanWindow] = []
            if scan._has_scan_windows_list and scan._scan_window_list is not None:
                for w in scan._scan_window_list.scan_windows:
                    w_params = _collect_cvparams(w, ref_groups, strict=strict)
                    windows_out.append(SpectrlScanWindow(params=w_params))
            scans_out.append(
                SpectrlScan(
                    params=scan_params,
                    windows=windows_out,
                    user_params=_collect_user_params(scan),
                )
            )

    # ─── Precursor list ──────────────────────────────────────────────────────
    precursors_out: list[SpectrlPrecursor] = []
    if spec.has_precursors:
        for pre in spec.precursors:
            iw_out = None
            if pre.isolation_window is not None:
                iw_out = SpectrlIsolationWindow(
                    params=_collect_cvparams(pre.isolation_window, ref_groups, strict=strict)
                )

            selected_ions_out: list[SpectrlSelectedIon] = []
            for si_elem in pre.element.findall(f"./{pre.ns}selectedIonList/{pre.ns}selectedIon"):
                from mzmlpy.spectra import SelectedIon

                si = SelectedIon(si_elem)
                selected_ions_out.append(SpectrlSelectedIon(params=_collect_cvparams(si, ref_groups, strict=strict)))

            act_out = None
            if pre.activation is not None:
                act_out = SpectrlActivation(params=_collect_cvparams(pre.activation, ref_groups, strict=strict))

            precursors_out.append(
                SpectrlPrecursor(
                    isolation_window=iw_out,
                    selected_ions=selected_ions_out,
                    activation=act_out,
                )
            )

    # ─── Product list ────────────────────────────────────────────────────────
    products_out: list[SpectrlProduct] = []
    if spec.has_products:
        for prod in spec.products:
            iw_out = None
            if prod.isolation_window is not None:
                iw_out = SpectrlIsolationWindow(
                    params=_collect_cvparams(prod.isolation_window, ref_groups, strict=strict)
                )
            products_out.append(SpectrlProduct(isolation_window=iw_out))

    # ─── Peak arrays ─────────────────────────────────────────────────────────
    mz = spec.mz
    intensity = spec.intensity
    charge = spec.charge

    # Preserve every remaining per-peak binary array. mzML identifies standard
    # arrays by CV accession; non-standard arrays use MS:1000786 with the name
    # carried as that cvParam's value.
    extra_arrays, array_units = _collect_arrays(spec)

    return InlineSpectrum(
        default_array_length=spec.default_array_length or (len(mz) if mz is not None else 0),
        mz=mz,
        intensity=intensity,
        charge=charge,
        id=spec.id,
        params=spectrum_params,
        scans=scans_out,
        scan_combination=scan_combination_out,
        precursors=precursors_out,
        products=products_out,
        extra_arrays=extra_arrays,
        array_units=array_units,
        user_params=spectrum_user_params,
    )


def _conversion_issues(spec, ref_groups: dict | None = None) -> list[dict[str, str]]:
    """Inventory omissions observable within this spectrum's XML subtree."""
    issues = []
    element = getattr(spec, "element", None)
    if element is None:
        return issues
    containers = {
        "spectrum",
        "scanList",
        "scan",
        "scanWindowList",
        "scanWindow",
        "precursorList",
        "precursor",
        "selectedIonList",
        "selectedIon",
        "isolationWindow",
        "activation",
        "productList",
        "product",
        "binaryDataArrayList",
        "binaryDataArray",
        "binary",
        "cvParam",
        "userParam",
        "referenceableParamGroupRef",
    }

    def add(code, path, message, severity="warning"):
        issues.append({"code": code, "path": path, "message": message, "severity": severity})

    def walk(node, path, parent=""):
        tag = str(node.tag).split("}")[-1]
        if tag not in containers:
            add("unmodeled_element", path, f"Element {tag} is outside the spectrum token model")
        if tag == "userParam" and parent not in {"spectrum", "scan"}:
            add("omitted_user_param", path, f"User parameter {node.get('name', '')!r} is not modeled at this location")
        if tag == "referenceableParamGroupRef":
            reference = node.get("ref")
            group = (ref_groups or {}).get(reference)
            if group is None:
                add("unresolved_reference", path, f"Reference group {reference!r} was not supplied")
            elif _collect_user_params(group):
                add("omitted_reference_user_params", path, "User parameters in reference groups are not expanded")
        if tag not in {"cvParam", "userParam", "referenceableParamGroupRef", "binary"}:
            preserved = {"id", "defaultArrayLength"} if tag == "spectrum" else set()
            representation = {"count", "encodedLength", "arrayLength"}
            for name in node.attrib:
                if name not in preserved | representation:
                    add("omitted_attribute", path + "/@" + name, f"Attribute {name} is not carried in v1", "info")
        counts = {}
        for child in node:
            name = str(child.tag).split("}")[-1]
            counts[name] = counts.get(name, 0) + 1
            walk(child, f"{path}/{name}[{counts[name]}]", tag)

    walk(element, "spectrum")
    return issues


def conversion_report(spec, ref_groups: dict | None = None, *, strict: bool = False) -> dict:
    """Convert mzML and report preserved data and observable omissions.

    Strict mode rejects warning-level omissions. Informational provenance
    attributes remain outside v1. Run-level XML is not available to this report.
    """
    import dataclasses

    issues = _conversion_issues(spec, ref_groups)
    if strict and any(issue["severity"] == "warning" for issue in issues):
        raise ValueError(
            "mzML conversion would omit data: " + next(i["message"] for i in issues if i["severity"] == "warning")
        )
    spectrum = from_mzmlpy(spec, ref_groups, strict=strict)
    counts = {"cv_params": 0, "user_params": 0}

    def count(value):
        if isinstance(value, SpectrlCvParam):
            counts["cv_params"] += 1
        elif isinstance(value, SpectrlUserParam):
            counts["user_params"] += 1
        elif dataclasses.is_dataclass(value):
            for field in dataclasses.fields(value):
                count(getattr(value, field.name))
        elif isinstance(value, list):
            for item in value:
                count(item)

    count(spectrum)
    return {
        "spectrum": spectrum,
        "preserved": {
            "peaks": spectrum.default_array_length,
            "arrays": sum(getattr(spectrum, key) is not None for key in ("mz", "intensity", "charge"))
            + len(spectrum.extra_arrays),
            **counts,
        },
        "issues": issues,
        "scope": "Spectrum subtree only. Run-level provenance and unmodeled XML are outside v1.",
    }
