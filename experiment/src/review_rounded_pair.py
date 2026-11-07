"""Find the widest pair among the archived B03 crossings and verify its two flights."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.spatial import ConvexHull
from scipy.spatial.distance import pdist

ROOT = Path(__file__).resolve().parents[2]


def widest_archived_pair(path):
    with np.load(path) as archive:
        locations, ids = [], []
        for model in ("D", "S", "E"):
            rows = np.flatnonzero(archive[f"{model}_event"] == 0)
            locations.extend(archive[f"{model}_yz"][rows])
            ids.extend((model, int(i)) for i in rows)
    points = np.array(locations)
    vertices = ConvexHull(points).vertices
    upper = np.triu_indices(len(vertices), k=1)
    distances = pdist(points[vertices])
    k = distances.argmax()
    pair = sorted(ids[vertices[axis[k]]] for axis in upper)
    return pair, float(distances[k]), len(points)


def verify_flight(draw, settings, method, max_step):
    physical, problem = settings["physics"], settings["official"]
    wind = np.array(draw["wind_m_s"])
    beta = np.array(draw["beta_s_inv"])
    kappa = draw["kappa_m_inv"]
    v0 = np.array(draw["v0_m_s"])
    assert draw["model"] == "S" and wind[2] == 0 and np.linalg.norm(wind) <= physical["wind_cap"]
    assert np.max(abs(beta)) <= physical["beta_cap"] and physical["kappa"][0] <= kappa <= physical["kappa"][1]
    assert np.all(v0 >= physical["velocity_lo"]) and np.all(v0 <= physical["velocity_hi"])

    def derivative(t, state):
        u = state[3:] - wind
        acceleration = np.cross(beta, u) - kappa * np.linalg.norm(u) * u
        acceleration[2] -= physical["g"]
        return np.r_[state[3:], acceleration]

    def goal(t, state):
        return state[0] - problem["gate"]

    def ground(t, state):
        return state[2] - physical["radius"]

    goal.direction, ground.direction = 1, -1
    goal.terminal = ground.terminal = True
    trajectory = solve_ivp(
        derivative, (0, settings["solver"]["horizon"]), [*problem["r0"], *v0],
        method=method, rtol=2e-12, atol=1e-14, max_step=max_step,
        events=(goal, ground), dense_output=True)
    assert trajectory.success and len(trajectory.t_events[0]) == 1 and len(trajectory.t_events[1]) == 0
    early = trajectory.sol(problem["times"])[:3].T
    margin = settings["observation"]["quantum_m"] / 2 - abs(early - problem["xyz"])
    assert np.all(margin > 0)
    crossing = trajectory.y_events[0][0]
    assert abs(crossing[1]) < problem["half_width"] and 0 < crossing[2] < problem["height"]
    return early, crossing[1:3], float(trajectory.t_events[0][0]), float(margin.min())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    settings = json.loads((ROOT / "design/settings.json").read_text())
    candidates = json.loads((ROOT / "report/evidence/review-inference.json").read_text())["rounded_pair_candidates"]
    ids, separation, count = widest_archived_pair(ROOT / "experiment/runs/B03/official_tracks.npz")
    assert sorted((d["model"], d["pooled_model_index"]) for d in candidates) == ids
    verified = []
    for draw in candidates:
        early, point, time, margin = verify_flight(draw, settings, "DOP853", 0.01)
        other, point_check, time_check, _ = verify_flight(draw, settings, "RK45", 0.001)
        discrepancy = float(np.max(abs(early - other)))
        assert discrepancy < margin / 100 and np.linalg.norm(point - point_check) < 1e-8 and abs(time - time_check) < 1e-9
        verified.append({
            "model": draw["model"], "pooled_model_index": draw["pooled_model_index"],
            "early_m": early.tolist(), "goal_yz_m": point.tolist(), "arrival_s": time,
            "smallest_clearance_inside_display_bin_m": margin,
            "max_early_solver_discrepancy_m": discrepancy,
            "goal_solver_discrepancy_m": float(np.linalg.norm(point - point_check)),
            "event_time_solver_discrepancy_s": abs(time - time_check),
            "goal_change_from_frozen_RK4_m": float(np.linalg.norm(point - draw["frozen_yz_m"])),
        })
    distance = float(np.linalg.norm(np.subtract(verified[0]["goal_yz_m"], verified[1]["goal_yz_m"])))
    result = {"positive_weight_direct_crossings_searched": count,
              "archived_maximum_pair_distance_m": separation, "verified_flights": verified,
              "verified_separation_m": distance, "witness_worst_case_floor_m": distance / 2,
              "scope": "Two direct model-S flights giving the prescribed rounded readings with exact timestamps. Other admissible flights could separate farther."}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
