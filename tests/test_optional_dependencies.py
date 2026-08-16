"""Core spectrl remains usable without optional integration packages."""

import os
import subprocess
import sys
from pathlib import Path


def test_core_import_does_not_require_mzmlpy():
    """Simulate an environment where mzmlpy cannot be imported."""
    source = Path(__file__).parent.parent / "src"
    code = """
import sys
from importlib.abc import MetaPathFinder

class BlockMzmlpy(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mzmlpy" or fullname.startswith("mzmlpy."):
            raise ModuleNotFoundError("blocked optional dependency", name=fullname)
        return None

sys.meta_path.insert(0, BlockMzmlpy())

import spectrl
import numpy as np
from spectrl.model import InlineSpectrum

token = spectrl.encode_spectrum(
    InlineSpectrum(
        default_array_length=1,
        mz=np.array([100.0]),
        intensity=np.array([10.0]),
    ),
    lossless=True,
)
assert spectrl.decode_token(token).default_array_length == 1

try:
    spectrl.from_mzmlpy(object())
except ModuleNotFoundError as exc:
    assert "spectrl[mzml]" in str(exc)
else:
    raise AssertionError("from_mzmlpy should require the optional dependency")
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(source), env.get("PYTHONPATH"))))
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
