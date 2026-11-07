"""Reproduce early curvature, phase controls, exact-fit witnesses and match diagnostics.

Run from the repository root with the experiment dependencies:
    python experiment/src/review_geometry.py > report/evidence/review-geometry.json
"""
import csv
import itertools
import json
import math
from pathlib import Path

import numpy as np

from pair import fit_shot


ROOT = Path(__file__).resolve().parents[2]
CFG = json.loads((ROOT / "design/settings.json").read_text())


def det(a, b):
    return a[0] * b[1] - a[1] * b[0]


def wind_threshold(p1, p2, h):
    return abs(det(p1, p2)) / (h * np.linalg.norm(2 * p1 - p2))


def chord_normal(p1, p2, h, wind):
    # The upper tangent to the wind disk gives the largest air-chord heading.
    phi = math.atan2(p2[1], p2[0]) + math.asin(2 * h * wind / np.linalg.norm(p2))
    n = np.array([-math.sin(phi), math.cos(phi)])
    acceleration = (p2 - 2 * p1) / h**2
    assert np.all(acceleration < 0) and 0 < phi < math.pi / 2
    return {
        "chord_heading_deg": math.degrees(phi),
        "wind_m_s": (-wind * n).tolist(),
        "triangular_mean_horizontal_acceleration_m_s2": acceleration.tolist(),
        "negative_normal_component_m_s2": float(-n @ acceleration),
        "midframe_displacement_along_positive_normal_m": float(n @ (p1 + h * wind * n)),
    }


def geometry():
    obs, p = CFG["official"], CFG["physics"]
    h, t2 = obs["times"]
    assert t2 == 2 * h
    positions = np.array(obs["xyz"])[:, :2] - np.array(obs["r0"])[:2]
    eps = CFG["observation"]["quantum_m"] / 2
    wind = p["wind_cap"]
    corners = [positions + np.reshape(offsets, (2, 2))
               for offsets in itertools.product((-eps, eps), repeat=4)]
    assert all(det(a, b) < 0 and np.all(b > t2 * wind) for a, b in corners)

    # For any fixed w, the collinearity determinant is multiaffine in the four
    # coordinates. A negative sign at every corner rules out its zero on the box.
    critical = min(corners, key=lambda pair: wind_threshold(*pair, h))
    capped_determinant = max(det(a, b) + h * wind * np.linalg.norm(2 * a - b)
                             for a, b in corners)
    assert capped_determinant < 0

    # For fixed p2 and direction phi in the first quadrant, the smallest
    # -n.(p2-2p1) uses largest x1 and smallest y1. It decreases with phi
    # since both components of p2-2p1 are negative. At the upper tangent,
    # n.p2=-2hW, so only n.p1 varies; it decreases as phi increases.
    # Smallest x2 and largest y2 maximise phi over the second box.
    limiting = positions + eps * np.array([[1, -1], [-1, 1]])
    rounded = chord_normal(*limiting, h, wind)
    nominal = chord_normal(*positions, h, wind)
    assert np.isclose(rounded["negative_normal_component_m_s2"],
                      min(chord_normal(a, b, h, wind)["negative_normal_component_m_s2"]
                          for a, b in corners))

    vmax = np.maximum(np.abs(p["velocity_lo"]), np.abs(p["velocity_hi"]))
    speed_cap = np.linalg.norm(vmax) + wind + t2 * p["g"]
    k = p["air_density"] * math.pi * p["radius"]**2 / (2 * p["mass"])
    cd_cap = .155 + .346 + p["drag_offset"][1]
    rate_cap = max(p["kappa"][1], k * cd_cap) * speed_cap
    # Let y=n.(p_h-wt) and A=2y(h)/h². y-b has three zeros for
    # b=A*t*(2h-t)/2. By Rolle, (y-b)' has two zeros, hence the derivative
    # of exp(integral c)*(y-b)' vanishes somewhere. There the actual
    # non-drag component y''+c*y' equals -A*(1-c*(h-t)).
    # The same bound holds in a weighted mean: the positive Dirichlet Green
    # kernel of -(d²/dt² + c*d/dt) evaluated at h integrates -(y-b)'' -
    # c*(y-b)' to (y-b)(h)=0 for these common endpoint values.
    factor = 1 - h * rate_cap
    assert factor > 0
    return {
        "coordinate_halfwidth_m": eps,
        "equally_spaced_step_s": h,
        "wind_cap_m_s": wind,
        "collinearity_threshold_m_s": {
            "central": wind_threshold(*positions, h),
            "rounded_infimum": wind_threshold(*critical, h),
            "limiting_closed_corner_xy_m": critical.tolist(),
            "maximum_signed_determinant_at_or_below_cap_m2": capped_determinant,
        },
        "chord_normal": {
            "definition": "Left normal to the 0--100 ms horizontal air chord; mean net acceleration weighted by min(t,2h-t)/h².",
            "central_still_air": chord_normal(*positions, h, 0.),
            "central_least_magnitude_with_wind": nominal,
            "rounded_infimum_with_wind": rounded,
            "rounding_limiting_closed_corner_xy_m": limiting.tolist(),
        },
        "non_drag_acceleration_certificate": {
            "scope": "Nominal D/S/E parameter ranges and constant wind. The negative chord-normal non-drag acceleration has at least the stated value at some time in the first 100 ms, and on average under the trajectory-specific positive Dirichlet Green kernel at the middle frame.",
            "air_speed_cap_m_s": speed_cap, "drag_rate_cap_per_s": rate_cap,
            "lower_fraction_of_chord_magnitude": factor,
            "central_lower_bound_m_s2": factor * nominal["negative_normal_component_m_s2"],
            "rounded_lower_bound_m_s2": factor * rounded["negative_normal_component_m_s2"],
        },
    }


def longitudinal_fit(times, x, gate):
    t1, t2 = times
    a = 2 * (x[1] / t2 - x[0] / t1) / (t2 - t1)
    v = x[0] / t1 - a * t1 / 2
    return 2 * gate / (v + math.sqrt(v*v + 2*a*gate)), v, a


def phase_control():
    obs = CFG["official"]
    times = np.array(obs["times"])
    x = np.array(obs["xyz"])[:, 0] - obs["r0"][0]
    gate = obs["gate"] - obs["r0"][0]
    t, v, a = longitudinal_fit(times, x, gate)
    s = t / times[0]
    weights = np.array([s * (2 - s), s * (s - 1) / 2])
    dx = weights @ (v + a * times)
    derivative = -dx / (v + a * t)

    def crossings(offset):
        shifted = times + offset
        generated_x = shifted * (v + a * shifted / 2)
        return np.array([longitudinal_fit(times, generated_x, gate)[0],
                         longitudinal_fit(shifted, x, gate)[0]])

    step = 1.e-7
    np.testing.assert_allclose((crossings(step) - crossings(-step)) / (2 * step),
                               [derivative, -derivative], rtol=1.e-7)
    return {
        "scope": "First forward plane roots of a constant-acceleration control; scenario values.",
        "crossing_s": t, "gate_speed_x_m_s": v + a * t,
        "generated_readings_fixed_time_derivative_x_m_s": dx,
        "generated_readings_crossing_derivative_s_per_s": derivative,
        "fixed_readings_reassigned_times_crossing_derivative_s_per_s": -derivative,
        "offset_ms": [-1, 0, 1],
        "generate_at_shifted_times_fit_at_nominal_crossing_s":
            [crossings(ms / 1000)[0] for ms in (-1, 0, 1)],
        "keep_readings_fit_at_shifted_times_crossing_s":
            [crossings(ms / 1000)[1] for ms in (-1, 0, 1)],
    }


def witnesses():
    results = []
    for cap in (.5, CFG["physics"]["beta_cap"]):
        shots = [fit_shot(bx) for bx in (-cap, cap)]
        gap = math.dist(*(shot["goal_yz_m"] for shot in shots))
        results.append({
            "beta_x_magnitudes_per_s": cap,
            "fits": [{key: value for key, value in shot.items() if key != "third_frame_xyz_m"}
                     for shot in shots],
            "separation_m": gap, "minimax_lower_bound_from_this_pair_m": gap / 2,
        })
    return results


def match_records():
    folder = ROOT / "report/evidence/field"
    with (folder / "support.csv").open() as handle:
        support = {r["match_id"]: r for r in csv.DictReader(handle)}
    with (folder / "reference.csv").open() as handle:
        references = {r["match_id"]: r for r in csv.DictReader(handle)}
    with (folder / "scores.csv").open() as handle:
        scores = list(csv.DictReader(handle))
    rows = []
    eps = CFG["observation"]["quantum_m"] / 2
    for shot in json.loads((ROOT / "experiment/runs/D02/inputs.json").read_text()):
        match = shot["match_id"]
        times, x = np.array(shot["times_s"]), np.array(shot["xyz_m"])[:, 0]
        h = times[1] - times[0]
        assert np.isclose(times[2] - times[1], h)
        increments = np.diff(x)
        second = increments[1] - increments[0]
        a_floor = max(0., abs(second) - 3 * eps) / h**2
        assert np.isclose(a_floor, float(support[match]["min_ax_from_second_difference_m_s2"]))
        row = {
            "match_id": match, "times_from_first_live_s": times.tolist(),
            "x_from_spot_m": x.tolist(), "x_increments_m": increments.tolist(),
            "signed_second_x_difference_m": second, "min_abs_ax_m_s2": a_floor,
            "min_acceleration_all_necessary_tests_m_s2": float(support[match]["min_a_needed_m_s2"]),
            "acceleration_ceiling_m_s2": float(support[match]["a_ceiling_all_m_s2"]),
            "gate_time_from_first_live_s": float(references[match]["gate_after_anchor_s"]),
            "late_only_gate_errors_m": {
                r["method"]: float(r["gate_error_m"]) for r in scores
                if r["match_id"] == match and r["mask"] == "late" and r["gate_error_m"]
            },
        }
        if second > 0:
            # Holding endpoints exact and moving only the middle time in an
            # exactly uniform longitudinal flight gives second=-2*v*offset.
            v = (x[2] - x[0]) / (times[2] - times[0])
            row["middle_time_shift_examples_not_estimates"] = {
                "linearization_at_30_m_s_ms": -1000 * second / (2 * 30),
                "uniform_speed_from_endpoints_m_s": v,
                "exact_offset_for_uniform_endpoint_speed_ms": -1000 * second / (2 * v),
            }
        rows.append(row)
    return rows


if __name__ == "__main__":
    print(json.dumps({"geometry": geometry(), "timing_control": phase_control(),
                      "exact_fit_witnesses": witnesses(), "match_records": match_records()},
                     indent=2, allow_nan=False))
