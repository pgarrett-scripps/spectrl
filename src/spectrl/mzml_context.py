"""Resolve selected-spectrum context from the mzML header without reading array blobs."""

from __future__ import annotations

import gzip
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .model import SpectrlCvParam
from .mzml_values import user_param

NS = {"m": "http://psi.hupo.org/ms/mzml"}

# mzML lets each file choose its own <cv> @id, and files disagree: the same
# PSI-MS release is declared id="MS" in one and id="PSI-MS" in another, while
# both write MS: accessions throughout. cv_versions is keyed by the accession
# prefix, so fold the spellings seen in the wild back onto it. An @id that is
# already a usable prefix passes through, which covers ontologies not listed.
_CV_ID_ALIASES = {"PSI-MS": "MS", "UNIT-ONTOLOGY": "UO", "UNIT": "UO"}
_PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


def cv_prefix(cv_id):
    """Map an mzML <cv> @id onto the accession prefix it describes, or None."""
    if not cv_id:
        return None
    alias = _CV_ID_ALIASES.get(cv_id.upper())
    if alias:
        return alias
    return cv_id if _PREFIX_RE.fullmatch(cv_id) else None


def params(element, groups=None):
    cvs, users = [], []
    if element is None:
        return cvs, users
    ns = {"m": element.tag.split("}")[0][1:] if "}" in element.tag else ""}
    for ref in element.findall("m:referenceableParamGroupRef", ns):
        key = ref.get("ref")
        if key not in (groups or {}):
            raise ValueError(f"unresolved parameter group {key!r}")
        c, u = params(groups[key])
        cvs.extend(c)
        users.extend(u)
    for cv in element.findall("m:cvParam", ns):
        value = cv.get("value")
        cvs.append(SpectrlCvParam(cv.get("accession"), None if value in (None, "") else value, cv.get("unitAccession")))
    for user in element.findall("m:userParam", ns):
        users.append(user_param(user))
    return cvs, users


def parameter_record(element, groups):
    cv, user = params(element, groups)
    return {**({"params": cv} if cv else {}), **({"user_params": user} if user else {})}


@dataclass
class MzMLContext:
    groups: dict
    instruments: dict
    software: dict
    processing: dict
    sources: dict
    run: dict
    spectrum_list: dict
    cv_versions: dict

    @classmethod
    def from_file(cls, path):
        path = Path(path)
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rb") as stream:
            parser = ET.iterparse(stream, events=("start", "end"))
            root = None
            run = {}
            spectrum_list = {}
            for event, elem in parser:
                if root is None:
                    root = elem
                if event == "start" and elem.tag.endswith("}run"):
                    run = dict(elem.attrib)
                if event == "start" and elem.tag.endswith("}spectrumList"):
                    spectrum_list = dict(elem.attrib)
                    break

        def records(tag):
            return {x.get("id"): x for x in root.findall(f".//m:{tag}", NS)}

        # Version strings stay exactly as declared. Real files write "4.1.142",
        # "12:10:2011", and "releases/2020-03-10", so there is no shared syntax
        # to normalize and nothing to gain by trying.
        cv_versions = {}
        for elem in root.findall(".//m:cvList/m:cv", NS):
            prefix, version = cv_prefix(elem.get("id")), elem.get("version")
            if prefix and version:
                cv_versions.setdefault(prefix, version)

        return cls(
            records("referenceableParamGroup"),
            records("instrumentConfiguration"),
            records("software"),
            records("dataProcessing"),
            records("sourceFile"),
            run,
            spectrum_list,
            cv_versions,
        )

    def source(self, key, spectrum_ref=None):
        if key is None:
            return {"spectrum_ref": spectrum_ref} if spectrum_ref else None
        if key not in self.sources:
            raise ValueError(f"unresolved sourceFileRef {key!r}")
        elem = self.sources[key]
        out = {k: elem.get(k) for k in ("id", "name", "location") if elem.get(k) is not None}
        out.update(parameter_record(elem, self.groups))
        if spectrum_ref:
            out["spectrum_ref"] = spectrum_ref
        return out

    def software_record(self, key):
        if key not in self.software:
            raise ValueError(f"unresolved softwareRef {key!r}")
        elem = self.software[key]
        return {
            **{k: elem.get(k) for k in ("id", "version") if elem.get(k) is not None},
            **parameter_record(elem, self.groups),
        }

    def acquisition(self, key):
        if key is None:
            return None
        if key not in self.instruments:
            raise ValueError(f"unresolved instrumentConfigurationRef {key!r}")
        elem = self.instruments[key]
        out = {"id": key, **parameter_record(elem, self.groups)}
        components = []
        for component in elem.findall("./m:componentList/*", NS):
            components.append(
                {
                    "kind": component.tag.rsplit("}", 1)[-1],
                    "order": int(component.get("order")),
                    **parameter_record(component, self.groups),
                }
            )
        if components:
            out["components"] = sorted(components, key=lambda x: x["order"])
        software = elem.find("m:softwareRef", NS)
        if software is not None:
            out["software"] = self.software_record(software.get("ref"))
        return {"instrument": out}

    def processing_steps(self, key):
        if key is None:
            return []
        if key not in self.processing:
            raise ValueError(f"unresolved dataProcessingRef {key!r}")
        methods = sorted(self.processing[key].findall("m:processingMethod", NS), key=lambda x: int(x.get("order")))
        return [
            {**parameter_record(method, self.groups), "software": self.software_record(method.get("softwareRef"))}
            for method in methods
        ]


def resolve_context(run):
    if run is None or isinstance(run, MzMLContext):
        return run
    if isinstance(run, (str, Path)):
        return MzMLContext.from_file(run)
    context = getattr(run, "_spectrl_context", None)
    if context is None:
        context = MzMLContext.from_file(run.file_path)
        run._spectrl_context = context
    return context
