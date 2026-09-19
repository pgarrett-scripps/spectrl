"""Inventory v3-relevant metadata in the existing codec benchmark selection."""

import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SELECTION = ROOT / "experiments/encoding/psi-sweep.json"
NS = {"m": "http://psi.hupo.org/ms/mzml"}
TYPE_IDS = {"MS:1000519", "MS:1000521", "MS:1000522", "MS:1000523"}


def local(node):
    return node.tag.rsplit("}", 1)[-1]


def audit():
    provenance = json.loads(SELECTION.read_text())["provenance"]
    totals = Counter()
    types = Counter()
    users = Counter()
    rows = []
    for entry in provenance:
        path = Path(entry["path"])
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], path
        root = ET.fromstring(data)
        run = root.find(".//m:run", NS)
        spectrum_list = run.find("m:spectrumList", NS)
        groups = {x.get("id"): x for x in root.findall(".//m:referenceableParamGroup", NS)}
        instruments = {x.get("id"): x for x in root.findall(".//m:instrumentConfiguration", NS)}
        processing = {x.get("id"): x for x in root.findall(".//m:dataProcessing", NS)}
        software = {x.get("id"): x for x in root.findall(".//m:software", NS)}
        by_id = {x.get("id"): x for x in spectrum_list.findall("m:spectrum", NS)}
        for picked in entry["selected"]:
            spectrum = by_id[picked["id"]]
            flags = set()
            scans = spectrum.findall("./m:scanList/m:scan", NS)
            instrument_ids = {
                x.get("instrumentConfigurationRef", run.get("defaultInstrumentConfigurationRef")) for x in scans
            }
            instrument_ids.discard(None)
            if instrument_ids:
                flags.add("instrument_reference")
            resolved_instruments = [instruments[x] for x in instrument_ids if x in instruments]
            if resolved_instruments:
                flags.add("resolved_instrument")
            if any(x.find("m:componentList", NS) is not None for x in resolved_instruments):
                flags.add("resolved_instrument_components")
            arrays = spectrum.findall("./m:binaryDataArrayList/m:binaryDataArray", NS)
            default_processing = spectrum.get("dataProcessingRef", spectrum_list.get("defaultDataProcessingRef"))
            processing_ids = {default_processing} | {x.get("dataProcessingRef") for x in arrays}
            processing_ids.discard(None)
            if processing_ids:
                flags.add("processing_reference")
            methods = [
                step
                for key in processing_ids
                if key in processing
                for step in processing[key].findall("m:processingMethod", NS)
            ]
            if methods:
                flags.add("resolved_processing")
            if any(x.get("softwareRef") in software for x in methods):
                flags.add("resolved_processing_software")
            if spectrum.get("sourceFileRef") or run.get("defaultSourceFileRef"):
                flags.add("explicit_source_reference")
            if root.findall(".//m:sourceFile", NS):
                flags.add("file_contains_source_records")
            if any(x.get("spectrumRef") for x in spectrum.findall("./m:precursorList/m:precursor", NS)):
                flags.add("precursor_spectrum_reference")
            if spectrum.get("spotID") is not None:
                flags.add("spot_id")
            for node in spectrum.iter():
                children = list(node)
                effective = [x for x in children if local(x) == "cvParam"]
                for child in children:
                    if local(child) == "userParam":
                        users[local(node)] += 1
                        if local(node) not in {"spectrum", "scan"}:
                            flags.add("nested_user_params_outside_v2")
                    if local(child) == "referenceableParamGroupRef":
                        group = groups.get(child.get("ref"))
                        if group is not None:
                            effective.extend(group.findall("m:cvParam", NS))
                            if group.findall("m:userParam", NS):
                                flags.add("referenced_user_params_outside_v2")
                counts = Counter(x.get("accession") for x in effective)
                if any(n > 1 for n in counts.values()):
                    flags.add("repeated_cv_in_effective_group")
                if local(node) == "binaryDataArray":
                    for accession in counts:
                        if accession in TYPE_IDS:
                            types[accession] += 1
                    if node.get("arrayLength") not in {None, spectrum.get("defaultArrayLength")}:
                        flags.add("array_length_override")
            totals.update(flags)
            rows.append({"dataset": entry["dataset"], "id": picked["id"], "features": sorted(flags)})
    assert len(rows) == 127, len(rows)
    return {
        "scope": (
            "Existing 127-spectrum codec selection, metadata presence only, "
            "not an exhaustive mzML conversion audit"
        ),
        "selection_sha256": hashlib.sha256(SELECTION.read_bytes()).hexdigest(),
        "datasets": len(provenance),
        "spectra": len(rows),
        "spectra_with_feature": dict(sorted(totals.items())),
        "declared_binary_array_dtypes": dict(sorted(types.items())),
        "direct_user_params_by_parent": dict(sorted(users.items())),
        "rows": rows,
    }


if __name__ == "__main__":
    report = audit()
    (Path(__file__).parent / "scope-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
