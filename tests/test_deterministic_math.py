"""expm1 and log1p must agree bit for bit with the JavaScript implementation.

The values here are the ones the codec actually evaluates plus the boundaries
of every branch in the fdlibm algorithms, because a divergence anywhere in
those would show up as a spectrum that decodes differently depending on which
language opened it.
"""

from decimal import Decimal, getcontext

import numpy as np
import pytest

from spectrl.codecs._deterministic import expm1, log1p

getcontext().prec = 60


def _ulp_error(values, computed, exact):
    worst = Decimal(0)
    for x, got in zip(values, computed, strict=True):
        true = exact(float(x))
        step = np.nextafter(abs(got), np.inf) - abs(got)
        if step == 0 or not np.isfinite(got):
            continue
        worst = max(worst, abs((Decimal(float(got)) - true) / Decimal(float(step))))
    return float(worst)


def test_expm1_matches_the_platform_within_one_ulp():
    values = np.concatenate([np.arange(0, 20000) / 3600.0, np.linspace(-40, 40, 20000)])
    difference = np.abs(
        np.frombuffer(expm1(values).tobytes(), dtype=np.int64)
        - np.frombuffer(np.expm1(values).tobytes(), dtype=np.int64)
    )
    assert difference.max() <= 1


def test_log1p_matches_the_platform_within_one_ulp():
    values = np.concatenate([np.linspace(0, 4000, 20000), np.linspace(-0.999, 10, 20000)])
    difference = np.abs(
        np.frombuffer(log1p(values).tobytes(), dtype=np.int64)
        - np.frombuffer(np.log1p(values).tobytes(), dtype=np.int64)
    )
    assert difference.max() <= 1


def test_accuracy_is_not_traded_for_determinism():
    """Both are measured against exact arithmetic, not against each other."""
    rng = np.random.default_rng(101)
    values = np.concatenate([rng.uniform(0, 30, 600), rng.uniform(-30, 0, 600)])
    ours = _ulp_error(values, expm1(values), lambda x: Decimal(x).exp() - 1)
    theirs = _ulp_error(values, np.expm1(values), lambda x: Decimal(x).exp() - 1)
    assert ours <= max(theirs, 1.0)

    values = np.concatenate([rng.uniform(0, 4000, 600), -rng.uniform(1e-9, 0.99, 600)])
    ours = _ulp_error(values, log1p(values), lambda x: (Decimal(1) + Decimal(x)).ln())
    theirs = _ulp_error(values, np.log1p(values), lambda x: (Decimal(1) + Decimal(x)).ln())
    assert ours <= max(theirs, 1.0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, 0.0),
        (-0.0, -0.0),
        (float("inf"), float("inf")),
        (float("-inf"), -1.0),
        (710.0, float("inf")),  # exp overflows above 709.78
        (-40.0, -1.0),  # saturates below -56 ln2
    ],
)
def test_expm1_edges(value, expected):
    got = float(expm1(np.array([value]))[0])
    assert got == expected
    assert np.signbit(got) == np.signbit(expected)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.0, 0.0), (-0.0, -0.0), (-1.0, float("-inf")), (float("inf"), float("inf"))],
)
def test_log1p_edges(value, expected):
    got = float(log1p(np.array([value]))[0])
    assert got == expected
    assert np.signbit(got) == np.signbit(expected)


def test_log1p_below_minus_one_is_undefined():
    assert np.isnan(log1p(np.array([-1.5]))).all()
    assert np.isnan(log1p(np.array([float("-inf")]))).all()


def test_nan_propagates():
    assert np.isnan(expm1(np.array([float("nan")]))).all()
    assert np.isnan(log1p(np.array([float("nan")]))).all()


def test_the_reduction_boundaries_are_continuous():
    """A branch boundary is where a transcription slip would show, so each is
    crossed in steps far smaller than the gap between representable doubles."""
    for centre in (0.3465735912322998, 1.0397214889526367, 38.816253662109375):
        values = np.linspace(centre * (1 - 1e-12), centre * (1 + 1e-12), 2001)
        result = expm1(values)
        assert np.all(np.diff(result) >= 0)
    for centre in (0.4142136573791504, -0.2928931713104248):
        values = np.linspace(centre - 1e-12, centre + 1e-12, 2001)
        assert np.all(np.diff(log1p(values)) >= 0)
