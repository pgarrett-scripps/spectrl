"""Resolve selected-spectrum context from the mzML header without reading array blobs."""

from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .model import SpectrlCvParam, SpectrlUserParam

NS = {"m": "http://psi.hupo.org/ms/mzml"}


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
        users.append(SpectrlUserParam(user.get("name"), user.get("value"), user.get("type"), user.get("unitAccession")))
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

        return cls(
            records("referenceableParamGroup"),
            records("instrumentConfiguration"),
            records("software"),
            records("dataProcessing"),
            records("sourceFile"),
            run,
            spectrum_list,
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
