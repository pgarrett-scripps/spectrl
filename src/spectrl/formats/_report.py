"""What a conversion could not represent, reported rather than discarded.

A token carries more spectrum-level structure than any of the text formats it
can be written to, so every export except mzML drops something. The format
contract is that a conversion never silently invents or discards semantics, so
each writer returns what it wrote together with what it could not, using the
same issue shape as mzml.conversion_report: code, path, message, severity.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConversionResult:
    """Converted text plus an inventory of what the target format cannot hold.

    Attributes:
        text: The converted document.
        format: Short format name, such as "mzml", "mgf", or "ms2".
        issues: One entry per omission or substitution. Severity is "warning"
            when information present in the token is absent from the output,
            and "info" when something was represented differently but not lost.
    """

    text: str
    format: str
    issues: list[dict] = field(default_factory=list)

    def add(self, code: str, path: str, message: str, severity: str = "warning") -> None:
        self.issues.append({"code": code, "path": path, "message": message, "severity": severity})

    @property
    def omitted(self) -> list[str]:
        """Messages for information the output does not carry."""
        return [i["message"] for i in self.issues if i["severity"] == "warning"]

    @property
    def lossless(self) -> bool:
        """True when nothing present in the token was left out."""
        return not self.omitted

    def summary(self) -> str:
        """A short report for a command line, empty when nothing was dropped."""
        if not self.omitted:
            return ""
        lines = [f"Not represented by {self.format.upper()}:"]
        lines += [f"  - {message}" for message in self.omitted]
        return "\n".join(lines)
