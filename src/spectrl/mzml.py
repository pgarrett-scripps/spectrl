"""Bridge from mzmlpy.spectra.Spectrum to InlineSpectrum.

Tree-walk rules:
  NAMED REGISTRY KEYS: default_array_length (key 0), id (key 1).
  CV: everything from cv_params on spectrum, scans, scan windows, precursors, products.
  USER PARAMS: free-text userParams on the spectrum and on each scan.
  PEAK ARRAYS: mz, intensity, and charge as dedicated fields; all other
  standard arrays, including every ion-mobility variant, keyed by accession.
  EXPAND: ref_params dereferenced via optional ref_group lookup; their cvParams emitted.
  CONTEXT: resolve source, instrument, software, and processing references from run.
  DROP: index, XML namespace, spot_id.
"""

from __future__ import annotations

import numpy as np
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


def _native_array(binary_array):
    """Restore the declared numeric width after mzmlpy widens decoded values."""
    data = binary_array.data
    encoding = str(getattr(binary_array, "encoding", None))
    compression = str(getattr(binary_array, "compression", None))
    if compression in {
        "MS:1002312",
        "MS:1002313",
        "MS:1002314",
        "MS:1002746",
        "MS:1002747",
        "MS:1002748",
        "MS:1003783",
        "MS:1003784",
        "MS:1003785",
    }:
        return np.asarray(data, dtype=np.float64)
    dtype = {"MS:1000519": "int32", "MS:1000521": "float32", "MS:1000523": "float64"}.get(encoding)
    if encoding == "MS:1000522":
        raise ValueError("spectrl v3 does not support mzML int64 arrays")
    return np.asarray(data, dtype=dtype) if dtype else data


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
        extra_arrays[key] = _native_array(binary_array)
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
    from .mzml_values import user_param

    return [user_param(u) for u in el.findall(f"./{ns}userParam")]


def from_mzmlpy(spec, ref_groups=None, *, strict=False, run=None):
    """Convert a spectrum and optional run context, preserving relevant metadata."""
    from .mzml_context import params, resolve_context

    NS = {"m": spec.ns.strip("{}") if spec.ns else ""}
    context = resolve_context(run)
    groups = (
        context.groups
        if context
        else {key: getattr(value, "element", value) for key, value in (ref_groups or {}).items()}
    )
    issues = _conversion_issues(spec, ref_groups, run=run)
    if strict and any(x["severity"] == "warning" for x in issues):
        raise ValueError(
            "mzML conversion would omit data: " + next(x["message"] for x in issues if x["severity"] == "warning")
        )

    def group(element, cls):
        if element is None:
            return None
        try:
            cvs, users = params(element, groups)
        except ValueError:
            if strict:
                raise
            import copy

            element = copy.deepcopy(element)
            for ref in element.findall("m:referenceableParamGroupRef", NS):
                if ref.get("ref") not in groups:
                    element.remove(ref)
            cvs, users = params(element, groups)
        return cls(params=cvs, user_params=users)

    root = spec.element
    base = group(root, lambda **kw: kw)
    extra, units = _collect_arrays(spec)
    core = {}
    array_params, array_users, array_processing = {}, {}, {}
    representation = {
        "MS:1000519",
        "MS:1000521",
        "MS:1000522",
        "MS:1000523",
        "MS:1000574",
        "MS:1000576",
        "MS:1002312",
        "MS:1002313",
        "MS:1002314",
        "MS:1002746",
        "MS:1002747",
        "MS:1002748",
        "MS:1003780",
        "MS:1003781",
        "MS:1003782",
        "MS:1003783",
        "MS:1003784",
        "MS:1003785",
    }
    processing_key = root.get(
        "dataProcessingRef", context.spectrum_list.get("defaultDataProcessingRef") if context else None
    )
    for array in spec.binary_arrays:
        accession = str(array.binary_array_type)
        element = array.element
        key = {"MS:1000514": "mz", "MS:1000515": "intensity", "MS:1000516": "charge"}.get(accession, accession)
        if key in {"mz", "intensity", "charge"}:
            core[key] = _native_array(array)
        if accession == "MS:1000786":
            term = next((p for p in array.cv_params if str(p.accession) == accession), None)
            key = str(term.value) if term is not None and term.value else "non-standard"
        record = group(element, lambda **kw: kw)
        cv = [p for p in record["params"] if p.accession not in representation | {accession}]
        if cv:
            array_params[key] = cv
        if record["user_params"]:
            array_users[key] = record["user_params"]
        if context and element.get("dataProcessingRef"):
            array_processing[key] = context.processing_steps(element.get("dataProcessingRef"))
    scans = []
    for elem in root.findall("./m:scanList/m:scan", NS):
        scan = group(elem, SpectrlScan)
        scan.windows = [group(w, SpectrlScanWindow) for w in elem.findall("./m:scanWindowList/m:scanWindow", NS)]
        if context and elem.get("instrumentConfigurationRef"):
            scan.acquisition = context.acquisition(elem.get("instrumentConfigurationRef"))
        if elem.get("spectrumRef") or elem.get("externalSpectrumID"):
            ref = elem.get("spectrumRef", elem.get("externalSpectrumID"))
            scan.source = context.source(elem.get("sourceFileRef"), ref) if context else {"spectrum_ref": ref}
        scans.append(scan)
    precursors = []
    for elem in root.findall("./m:precursorList/m:precursor", NS):
        ref = elem.get("spectrumRef", elem.get("externalSpectrumID"))
        source = context.source(elem.get("sourceFileRef"), ref) if context else ({"spectrum_ref": ref} if ref else None)
        precursors.append(
            SpectrlPrecursor(
                isolation_window=group(elem.find("m:isolationWindow", NS), SpectrlIsolationWindow),
                selected_ions=[
                    group(x, SpectrlSelectedIon) for x in elem.findall("./m:selectedIonList/m:selectedIon", NS)
                ],
                activation=group(elem.find("m:activation", NS), SpectrlActivation),
                source=source,
            )
        )
    products = [
        SpectrlProduct(isolation_window=group(x.find("m:isolationWindow", NS), SpectrlIsolationWindow))
        for x in root.findall("./m:productList/m:product", NS)
    ]
    # Only the ontologies this spectrum actually cites, so a token does not
    # carry a version for a vocabulary it never uses.
    cited = set()
    for node in root.iter():
        for attr in ("accession", "unitAccession"):
            value = node.get(attr)
            if value and ":" in value:
                cited.add(value.split(":", 1)[0])
    cv_versions = {k: v for k, v in (context.cv_versions if context else {}).items() if k in cited}

    combo = None
    scan_list = root.find("m:scanList", NS)
    if scan_list is not None:
        cv, _ = params(scan_list, groups)
        if cv:
            combo = cv[0]
    return InlineSpectrum(
        default_array_length=spec.default_array_length,
        id=spec.id,
        **core,
        **base,
        scans=scans,
        scan_combination=combo,
        precursors=precursors,
        products=products,
        extra_arrays=extra,
        array_units=units,
        array_params=array_params,
        array_user_params=array_users,
        array_processing=array_processing,
        source=context.source(root.get("sourceFileRef", context.run.get("defaultSourceFileRef"))) if context else None,
        acquisition=context.acquisition(context.run.get("defaultInstrumentConfigurationRef")) if context else None,
        processing=context.processing_steps(processing_key) if context else [],
        cv_versions=cv_versions,
    )


def _conversion_issues(spec, ref_groups: dict | None = None, *, run=None) -> list[dict[str, str]]:
    """Inventory omissions observable within this spectrum's XML subtree."""
    from .mzml_context import resolve_context

    context = resolve_context(run)
    if context:
        ref_groups = context.groups
    issues = []
    if context is None:
        issues.append(
            {
                "code": "context_not_supplied",
                "path": "run",
                "severity": "info",
                "message": "Supply run context to preserve instrument, source, and processing records",
            }
        )
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
        if tag == "userParam" and parent not in {
            "spectrum",
            "scan",
            "scanWindow",
            "isolationWindow",
            "selectedIon",
            "activation",
            "binaryDataArray",
        }:
            add("omitted_user_param", path, f"User parameter {node.get('name', '')!r} is not modeled at this location")
        if tag == "referenceableParamGroupRef":
            reference = node.get("ref")
            group = (ref_groups or {}).get(reference)
            if group is None:
                add("unresolved_reference", path, f"Reference group {reference!r} was not supplied")

        if tag not in {"cvParam", "userParam", "referenceableParamGroupRef", "binary"}:
            preserved = {"id", "defaultArrayLength"} if tag == "spectrum" else set()
            if tag in {"precursor", "scan"}:
                preserved |= {"spectrumRef", "externalSpectrumID"}
            if context:
                preserved |= {"sourceFileRef", "instrumentConfigurationRef", "dataProcessingRef"}
            representation = {"count", "encodedLength", "arrayLength"}
            for name in node.attrib:
                if name not in preserved | representation:
                    add("omitted_attribute", path + "/@" + name, f"Attribute {name} is not carried in v3", "info")
        counts = {}
        for child in node:
            name = str(child.tag).split("}")[-1]
            counts[name] = counts.get(name, 0) + 1
            walk(child, f"{path}/{name}[{counts[name]}]", tag)

    walk(element, "spectrum")
    return issues


def conversion_report(spec, ref_groups: dict | None = None, *, strict: bool = False, run=None) -> dict:
    """Convert mzML and report preserved data and observable omissions.

    Strict mode rejects warning-level omissions. Supplying run context resolves
    selected-spectrum references without importing the complete run inventory.
    """
    import dataclasses

    issues = _conversion_issues(spec, ref_groups, run=run)
    if strict and any(issue["severity"] == "warning" for issue in issues):
        raise ValueError(
            "mzML conversion would omit data: " + next(i["message"] for i in issues if i["severity"] == "warning")
        )
    spectrum = from_mzmlpy(spec, ref_groups, strict=strict, run=run)
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
        "scope": "Selected spectrum and supplied acquisition context. Other run records are outside v3.",
    }
