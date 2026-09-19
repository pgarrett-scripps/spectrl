"""Reversible byte-lane shuffle."""

import numpy as np


def shuffle(raw, width, inverse=False):
    if width not in (1, 2, 4, 8) or len(raw) % width:
        raise ValueError("invalid word width or byte length")
    data = np.frombuffer(raw, dtype=np.uint8)
    shape = (width, -1) if inverse else (-1, width)
    return data.reshape(shape).T.copy().tobytes()
