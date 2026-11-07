"""Portable B-1.0 intake check. Run with only Python's standard library."""
import itertools
import json
import math
from pathlib import Path


def wind_floor(xy, times, eps):
    """Minimum disk radius giving possible collinearity, for an independent box."""
    t1, t2 = times
    ratios, signs = [], []
    for delta in itertools.product((-eps, eps), repeat=4):
        a, b, c, d = [value + error for value, error in zip(xy, delta)]
        determinant = a * d - b * c
        norm = math.hypot(t2 * a - t1 * c, t2 * b - t1 * d)
        signs.append(determinant)
        ratios.append(abs(determinant) / norm if norm else 0.0)
    return 0.0 if min(signs) <= 0 <= max(signs) else min(ratios)


def main():
    cfg = json.loads(Path(__file__).with_name("settings.json").read_text())
    o = cfg["official"]
    xy = [d for row in o["xyz"] for d in row[:2]]
    bounds = [wind_floor(xy, o["times"], e) for e in (0, cfg["observation"]["quantum_m"] / 2)]
    lo, hi = 0.0, 0.02
    for _ in range(52):
        mid = (lo + hi) / 2
        if wind_floor(xy, o["times"], mid) == 0:
            hi = mid
        else:
            lo = mid
    assert abs(bounds[0] - 14.8492424) < 1e-5
    assert abs(bounds[1] - 4.353207) < 1e-5
    assert abs(hi * 1000 - 7.27903) < 1e-4
    print(json.dumps({"version": cfg["version"], "wind_floor_m_s": bounds,
                      "still_air_threshold_mm": hi * 1000, "status": "pass"}))


if __name__ == "__main__":
    main()
