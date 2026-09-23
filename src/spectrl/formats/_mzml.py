"""Write one decoded spectrum as a complete, valid mzML 1.1.0 document.

An information-matched writer already existed in the manuscript's analysis, but
it was built to prove a size comparison, so it refused anything it could not
compare: a spectrum without an id, extensions, external source ids, a custom
processing operation. It also stripped the lossy-encoding processing record,
because leaving it in would have described data the matched XML did not have.

An interoperability writer has to invert every one of those. A recipient wants
the lossy record most of all, since it is the only statement that the arrays
were quantized. Nothing is refused here; whatever mzML cannot express is
reported through ConversionResult instead.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from xml.dom import minidom

from ..model import DecodedSpectrum, SpectrlCvParam, SpectrlUserParam
from ._names import term_name
from ._report import ConversionResult

MZML_NS = "http://psi.hupo.org/ms/mzml"
_WRITER_SOFTWARE = "spectrl_writer"

# file://C:/path puts a Windows drive letter where the authority belongs, which
# is not a valid xs:anyURI and makes the whole document fail validation. RFC
# 8089 spells it with an empty authority. Real files carry the broken form, so
# it is repaired on the way out rather than copied into invalid XML.
_WINDOWS_FILE_URI = re.compile(r"^(file://)(?=[A-Za-z]:)")


def _location(value: str, result: ConversionResult) -> str:
    fixed = _WINDOWS_FILE_URI.sub(r"\1/", value)
    if fixed != value:
        result.add(
            "location_uri_normalized",
            "source.location",
            f"source location {value!r} is not a valid URI; wrote {fixed!r}",
            severity="info",
        )
    return fixed


def _cv(parent, param: SpectrlCvParam, names) -> None:
    attrs = {
        "cvRef": param.accession.split(":", 1)[0],
        "accession": param.accession,
        "name": term_name(param.accession, names),
    }
    # Empty string is a value; only None marks a flag parameter.
    if param.value is not None:
        attrs["value"] = str(param.value)
    if param.unit_accession:
        attrs["unitAccession"] = param.unit_accession
        attrs["unitName"] = term_name(param.unit_accession, names)
        attrs["unitCvRef"] = param.unit_accession.split(":", 1)[0]
    ET.SubElement(parent, "cvParam", attrs)


def _user(parent, param: SpectrlUserParam, names) -> None:
    attrs = {"name": param.name}
    # mzML has no native numeric type, so annotate to let a reader recover it.
    if type(param.value) is int:
        attrs["type"] = "xsd:integer"
    elif type(param.value) is float:
        attrs["type"] = "xsd:double"
    if param.value is not None:
        attrs["value"] = str(param.value)
    if param.unit_accession:
        attrs["unitAccession"] = param.unit_accession
        attrs["unitName"] = term_name(param.unit_accession, names)
        attrs["unitCvRef"] = param.unit_accession.split(":", 1)[0]
    ET.SubElement(parent, "userParam", attrs)


def _params(parent, params, user_params, names) -> None:
    for param in params or []:
        _cv(parent, param, names)
    for param in user_params or []:
        _user(parent, param, names)


def _record_params(parent, record: dict, names) -> None:
    _params(parent, record.get("params"), record.get("user_params"), names)


def _group(parent, tag, value, names):
    if value is None:
        return None
    node = ET.SubElement(parent, tag)
    _params(node, value.params, value.user_params, names)
    return node


class _Scaffold:
    """Collects the header lists mzML requires, inventing only what it must.

    mzML 1.1.0 requires softwareList, instrumentConfigurationList and
    dataProcessingList even when the token carries no such context, so a
    placeholder entry is created and reported rather than omitted, which would
    make the document invalid.
    """

    def __init__(self, result: ConversionResult, names):
        self.result = result
        self.names = names
        self.sources: dict = {}
        self.instruments: dict = {}
        self.software: dict = {}
        self.processing: dict = {}
        self._taken: set[str] = set()
        self._allocated: dict[tuple[str, str], str] = {}

    def xml_id(self, kind: str, key: str) -> str:
        """An xs:ID for a token identifier, unique across the whole document.

        mzML ids are xs:ID, so they must be NCNames and unique document-wide,
        while a token's identifiers are only unique within their own record
        kind. One real file names both its source file and its software
        "UNIFI", which collides once both land in the same document.
        """
        if (kind, key) in self._allocated:
            return self._allocated[(kind, key)]
        candidate = re.sub(r"[^A-Za-z0-9_.-]", "_", key) or kind
        if not re.match(r"^[A-Za-z_]", candidate):
            candidate = f"{kind}_{candidate}"
        if candidate != key:
            self.result.add(
                "id_normalized",
                f"{kind}.id",
                f"{kind} id {key!r} is not a valid XML id; wrote {candidate!r}",
                severity="info",
            )
        unique, suffix = candidate, 2
        while unique in self._taken:
            unique = f"{candidate}_{suffix}"
            suffix += 1
        if unique != candidate:
            self.result.add(
                "id_deduplicated",
                f"{kind}.id",
                f"{kind} id {candidate!r} is already used by another record; wrote {unique!r}",
                severity="info",
            )
        self._taken.add(unique)
        self._allocated[(kind, key)] = unique
        return unique

    def source(self, record) -> dict:
        if not record:
            return {}
        attrs = {}
        if record.get("spectrum_ref"):
            attrs["externalSpectrumID"] = record["spectrum_ref"]
        key = record.get("id")
        if key:
            key = self.xml_id("sourceFile", key)
            if key not in self.sources:
                attributes = {k: record[k] for k in ("id", "name", "location") if k in record}
                attributes["id"] = key
                if "location" in attributes:
                    attributes["location"] = _location(attributes["location"], self.result)
                node = ET.Element("sourceFile", attributes)
                _record_params(node, record, self.names)
                # mzML has no element for these, so they become userParams
                # rather than vanishing.
                for value in record.get("external_ids", []):
                    ET.SubElement(node, "userParam", {"name": "spectrl:external_id", "value": value})
                self.sources[key] = node
            attrs["sourceFileRef"] = key
        elif record.get("external_ids"):
            self.result.add(
                "external_ids_without_source",
                "source.external_ids",
                "source external identifiers need a source file to attach to",
            )
        return attrs

    def external_anchor(self) -> str:
        """A sourceFile id for references that point outside this document.

        mzML says externalSpectrumID "must correspond to the id attribute of a
        spectrum in the external document indicated by sourceFileRef", so a
        reference with no source file of its own still needs one to hang on.
        """
        key = self.xml_id("sourceFile", "spectrl_origin")
        if key not in self.sources:
            node = ET.Element("sourceFile", {"id": key, "name": "unknown", "location": "file:///"})
            ET.SubElement(
                node,
                "userParam",
                {"name": "spectrl:synthesized", "value": "origin of an external spectrum reference"},
            )
            self.sources[key] = node
            self.result.add(
                "synthesized_source_file",
                "precursor.sourceFileRef",
                "a placeholder sourceFile was written to anchor an external precursor reference",
                severity="info",
            )
        return key

    def software_ref(self, record) -> str:
        """A softwareRef, synthesizing the writer's own entry when absent.

        processingMethod requires softwareRef, so a processing record with no
        software still needs one to keep the document valid.
        """
        if record is None:
            writer = self.xml_id("software", _WRITER_SOFTWARE)
            if writer not in self.software:
                node = ET.Element("software", {"id": writer, "version": _version()})
                ET.SubElement(
                    node,
                    "userParam",
                    {"name": "spectrl:synthesized", "value": "processing record carried no software context"},
                )
                self.software[writer] = node
            return writer
        key = self.xml_id("software", record.get("id") or f"software{len(self.software)}")
        if key not in self.software:
            node = ET.Element("software", {"id": key, "version": str(record.get("version", ""))})
            _record_params(node, record, self.names)
            self.software[key] = node
        return key

    def acquisition(self, record) -> str | None:
        if not record:
            return None
        value = record.get("instrument")
        if not value:
            return None
        key = self.xml_id("instrumentConfiguration", value.get("id") or f"instrument{len(self.instruments)}")
        if key not in self.instruments:
            node = ET.Element("instrumentConfiguration", {"id": key})
            _record_params(node, value, self.names)
            components = value.get("components", [])
            if components:
                collection = ET.SubElement(node, "componentList", {"count": str(len(components))})
                for component in components:
                    part = ET.SubElement(collection, component["kind"], {"order": str(component.get("order", 1))})
                    _record_params(part, component, self.names)
            if value.get("software"):
                ET.SubElement(node, "softwareRef", {"ref": self.software_ref(value["software"])})
            self.instruments[key] = node
        return key

    def processing_ref(self, records) -> str:
        key = self.xml_id("dataProcessing", f"processing{len(self.processing)}")
        node = ET.Element("dataProcessing", {"id": key})
        for order, record in enumerate(records or []):
            method = ET.SubElement(
                node,
                "processingMethod",
                {"order": str(order), "softwareRef": self.software_ref(record.get("software"))},
            )
            _record_params(method, record, self.names)
            # The benchmark writer refused these and stripped the lossy record
            # with them. They are the provenance a recipient most needs, so
            # they are written as userParams and kept.
            if record.get("operation"):
                ET.SubElement(method, "userParam", {"name": "spectrl:operation", "value": str(record["operation"])})
                if record.get("revision") is not None:
                    ET.SubElement(
                        method,
                        "userParam",
                        {"name": "spectrl:operation_revision", "value": str(record["revision"])},
                    )
                self.result.add(
                    "operation_as_user_param",
                    "processing.operation",
                    f"processing operation {record['operation']} written as a userParam; "
                    "mzML has no controlled term for it",
                    severity="info",
                )
        if not (records or []):
            ET.SubElement(
                node,
                "processingMethod",
                {"order": "0", "softwareRef": self.software_ref(None)},
            )
        self.processing[key] = node
        return key


def _version() -> str:
    """The installed package version, or "unknown" when running from a tree
    that was never installed. A writer must not fail over a label."""
    from importlib.metadata import PackageNotFoundError, version  # noqa: PLC0415

    try:
        return version("spectrl")
    except PackageNotFoundError:
        return "unknown"


def _binary_arrays(parent, spectrum: DecodedSpectrum, names, result, scaffold) -> None:
    """One binaryDataArray per array, base64 of little-endian words.

    mzML carries reconstructed values, so the arrays are written as decoded,
    not as the token's encoded words. Every array is declared 64-bit float and
    uncompressed, which is what a decoded spectrum is in memory.
    """
    import base64  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    # The per-array maps are keyed the way the caller addresses an array --
    # "mz" for a core array, the extra-array key otherwise -- which is not the
    # accession the descriptor carries. Both are tracked so the lookups hit.
    arrays: list[tuple[str, object, str | None, str]] = []
    for key, accession in (("mz", "MS:1000514"), ("intensity", "MS:1000515"), ("charge", "MS:1000516")):
        values = getattr(spectrum, key, None)
        if values is not None:
            arrays.append((accession, values, spectrum.array_names.get(key), key))
    for key, values in (spectrum.extra_arrays or {}).items():
        accession = key if ":" in key else "MS:1000786"
        arrays.append((accession, values, key if ":" not in key else spectrum.array_names.get(key), key))

    collection = ET.SubElement(parent, "binaryDataArrayList", {"count": str(len(arrays))})
    for accession, values, name, key in arrays:
        data = np.asarray(values, dtype="<f8").tobytes()
        encoded = base64.b64encode(data).decode("ascii")
        node = ET.SubElement(collection, "binaryDataArray", {"encodedLength": str(len(encoded))})
        _cv(node, SpectrlCvParam("MS:1000523"), names)
        _cv(node, SpectrlCvParam("MS:1000576"), names)
        unit = (spectrum.array_units or {}).get(key)
        _cv(node, SpectrlCvParam(accession, name if accession == "MS:1000786" else None, unit), names)
        for param in (spectrum.array_params or {}).get(key, []):
            _cv(node, param, names)
        for param in (spectrum.array_user_params or {}).get(key, []):
            _user(node, param, names)
        records = (spectrum.array_processing or {}).get(key)
        if records:
            node.set("dataProcessingRef", scaffold.processing_ref(records))
        ET.SubElement(node, "binary").text = encoded


def write_mzml(
    spectrum: DecodedSpectrum,
    *,
    names: dict[str, str] | None = None,
    indent: bool = True,
) -> ConversionResult:
    """Write one decoded spectrum as a complete mzML 1.1.0 document.

    Nothing is refused. An absent spectrum id is synthesized, because mzML
    requires one; extensions, which have no mzML element, are reported. Pass
    `names` to supply CV term names for accessions outside the set spectrl
    defines; see _names for why no ontology is bundled.
    """
    result = ConversionResult("", "mzml")
    scaffold = _Scaffold(result, names)

    spectrum_id = spectrum.id
    if not spectrum_id:
        spectrum_id = "index=0"
        result.add(
            "synthesized_id",
            "spectrum.id",
            "the token carried no spectrum id; mzML requires one, so 'index=0' was written",
            severity="info",
        )
    for scope, value in (("spectrum", spectrum.extensions), ("array", spectrum.array_extensions)):
        if value:
            result.add(
                "extensions_dropped",
                f"{scope}.extensions",
                f"{scope}-level extensions ({', '.join(sorted(value))}) have no mzML representation",
            )
    if spectrum.cv_versions:
        result.add(
            "cv_versions_as_cv_list",
            "cv_versions",
            "ontology versions written onto the cvList entries they describe",
            severity="info",
        )

    node = ET.Element(
        "spectrum",
        {"id": spectrum_id, "index": "0", "defaultArrayLength": str(spectrum.default_array_length)},
    )
    _params(node, spectrum.params, spectrum.user_params, names)
    node.attrib.update(scaffold.source(spectrum.source))

    if spectrum.scans or spectrum.scan_combination:
        scans = ET.SubElement(node, "scanList", {"count": str(len(spectrum.scans))})
        if spectrum.scan_combination:
            _cv(scans, spectrum.scan_combination, names)
        for scan in spectrum.scans:
            scan_node = ET.SubElement(scans, "scan", scaffold.source(scan.source))
            instrument = scaffold.acquisition(scan.acquisition)
            if instrument:
                scan_node.set("instrumentConfigurationRef", instrument)
            _params(scan_node, scan.params, scan.user_params, names)
            if scan.windows:
                windows = ET.SubElement(scan_node, "scanWindowList", {"count": str(len(scan.windows))})
                for window in scan.windows:
                    _group(windows, "scanWindow", window, names)
            if scan.processing:
                scan_node.set("dataProcessingRef", scaffold.processing_ref(scan.processing))

    if spectrum.precursors:
        precursors = ET.SubElement(node, "precursorList", {"count": str(len(spectrum.precursors))})
        for precursor in spectrum.precursors:
            attrs = scaffold.source(precursor.source)
            if "externalSpectrumID" in attrs and "sourceFileRef" not in attrs:
                attrs["sourceFileRef"] = scaffold.external_anchor()
            entry = ET.SubElement(precursors, "precursor", attrs)
            _group(entry, "isolationWindow", precursor.isolation_window, names)
            if precursor.selected_ions:
                ions = ET.SubElement(entry, "selectedIonList", {"count": str(len(precursor.selected_ions))})
                for ion in precursor.selected_ions:
                    _group(ions, "selectedIon", ion, names)
            _group(entry, "activation", precursor.activation, names)

    if spectrum.products:
        products = ET.SubElement(node, "productList", {"count": str(len(spectrum.products))})
        for product in spectrum.products:
            entry = ET.SubElement(products, "product")
            _group(entry, "isolationWindow", product.isolation_window, names)

    _binary_arrays(node, spectrum, names, result, scaffold)

    # A scan-level instrument alone still needs the run's required default reference.
    instrument = scaffold.acquisition(spectrum.acquisition) or next(iter(scaffold.instruments), None)
    processing = scaffold.processing_ref(spectrum.processing)
    result.text = _document(node, spectrum, scaffold, instrument, processing, indent)
    return result


def _document(spectrum_node, spectrum, scaffold, instrument, processing, indent) -> str:
    """Wrap the spectrum in the header lists mzML 1.1.0 requires."""
    root = ET.Element("mzML", {"xmlns": MZML_NS, "version": "1.1.0"})

    declared = dict(spectrum.cv_versions or {})
    entries = [
        ("MS", "PSI Mass Spectrometry Ontology", "https://purl.obolibrary.org/obo/ms.obo"),
        ("UO", "Unit Ontology", "https://purl.obolibrary.org/obo/uo.obo"),
    ]
    for prefix in sorted(declared):
        if prefix not in {"MS", "UO"}:
            entries.append((prefix, prefix, ""))
    cv_list = ET.SubElement(root, "cvList", {"count": str(len(entries))})
    for prefix, full_name, uri in entries:
        attrs = {"id": prefix, "fullName": full_name, "URI": uri}
        # The token's declared version is the one this document's accessions
        # were written under, so it is restored where mzML expects it.
        if declared.get(prefix):
            attrs["version"] = declared[prefix]
        ET.SubElement(cv_list, "cv", attrs)

    description = ET.SubElement(root, "fileDescription")
    ET.SubElement(description, "fileContent")
    if scaffold.sources:
        collection = ET.SubElement(description, "sourceFileList", {"count": str(len(scaffold.sources))})
        collection.extend(scaffold.sources.values())

    if not scaffold.software:
        scaffold.software_ref(None)
    for tag, records in (
        ("softwareList", scaffold.software),
        ("instrumentConfigurationList", scaffold.instruments),
        ("dataProcessingList", scaffold.processing),
    ):
        if tag == "instrumentConfigurationList" and not records:
            node = ET.Element("instrumentConfiguration", {"id": "instrument0"})
            records = {"instrument0": node}
            instrument = "instrument0"
        collection = ET.SubElement(root, tag, {"count": str(len(records))})
        collection.extend(records.values())

    run = ET.SubElement(root, "run", {"id": "spectrl", "defaultInstrumentConfigurationRef": instrument})
    spectrum_list = ET.SubElement(run, "spectrumList", {"count": "1", "defaultDataProcessingRef": processing})
    spectrum_list.append(spectrum_node)

    raw = ET.tostring(root, encoding="unicode")
    if not indent:
        return '<?xml version="1.0" encoding="utf-8"?>' + raw
    return minidom.parseString(raw).toprettyxml(indent="  ")
