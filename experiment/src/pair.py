"""Refit two penalty trajectories to the official early readings and compare them."""

import json
import platform
from pathlib import Path

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.optimize import root


CFG = json.loads((Path(__file__).resolve().parents[2] / "design/settings.json").read_text())
START = tuple(CFG["official"]["r0"])
TIMES = np.array(CFG["official"]["times"])
READINGS = np.array(CFG["official"]["xyz"])
FRAMES = (0.15, 0.20, 0.25)
EPSILON = CFG["observation"]["quantum_m"]/2
G = CFG["physics"]["g"]


def goal(t, state):
    return state[0] - 11.0


def ground(t, state):
    return state[2] - START[2]


goal.direction, goal.terminal = 1, True
ground.direction, ground.terminal = -1, True


def integrate(params, beta_x, end, method="DOP853", max_step=np.inf):
    velocity = params[:3]
    drag = params[3]
    beta = np.array([beta_x, *params[4:]])

    def rhs(t, state):
        v = state[3:]
        accel = np.cross(beta, v) - drag * np.linalg.norm(v) * v
        accel[2] -= G
        return np.concatenate((v, accel))

    sol = solve_ivp(rhs, (0, end), (*START, *velocity), method=method,
                    dense_output=True, events=(goal, ground), max_step=max_step,
                    rtol=2e-12, atol=1e-13)
    if not sol.success:
        raise RuntimeError(sol.message)
    return sol


def fit_shot(beta_x):
    def residual(params):
        early = integrate(params, beta_x, TIMES[-1])
        if early.t[-1] < TIMES[-1]:
            raise ValueError("An early trial trajectory stopped before both readings.")
        return (early.sol(TIMES)[:3].T - READINGS).ravel()

    estimate = root(residual, [30.4, 9.4, 6.9, 0.019, 0, -0.4], tol=1e-11)
    if not estimate.success or estimate.x[3] <= 0:
        raise ValueError(f"Invalid fit: {estimate.message}")

    ph = CFG["physics"]
    assert ph["kappa"][0] <= estimate.x[3] <= ph["kappa"][1]
    assert np.all((np.array(ph["velocity_lo"]) <= estimate.x[:3]) & (estimate.x[:3] <= ph["velocity_hi"]))
    assert max(abs(beta_x), *abs(estimate.x[4:])) <= ph["beta_cap"]
    endpoint_checks = []
    for method, step in (("DOP853", np.inf), ("RK45", 0.005)):
        shot = integrate(estimate.x, beta_x, 1.0, method, step)
        if shot.t_events[0].size != 1 or shot.t_events[1].size != 0:
            raise ValueError("A goal-plane crossing before ground contact is required.")
        q = shot.y_events[0][0, 1:3]
        if not (-3.66 < q[0] < 3.66 and 0 < q[1] < 2.44):
            raise ValueError("The witness must enter the goal.")
        error = float(np.max(np.abs(shot.sol(TIMES)[:3].T - READINGS)))
        if error > 1e-8:
            raise ValueError(f"Early positions failed the 1e-8 m fit criterion: {error}")
        endpoint_checks.append((q, error))

    q, error = endpoint_checks[-1]
    discrepancy = float(np.linalg.norm(q - endpoint_checks[0][0]))
    if discrepancy > 1e-8:
        raise ValueError(f"Goal-plane integrators disagree by {discrepancy} m.")
    return {
        "velocity0_m_s": estimate.x[:3].tolist(),
        "kappa_per_m": float(estimate.x[3]),
        "beta_per_s": [beta_x, *estimate.x[4:].tolist()],
        "max_early_residual_m": max(error, endpoint_checks[0][1]),
        "arrival_s": float(shot.t_events[0][0]),
        "goal_yz_m": q.tolist(),
        "goal_solver_difference_m": discrepancy,
        "third_frame_xyz_m": shot.sol(FRAMES)[:3].T.tolist(),
    }


def main():
    shots = [fit_shot(beta_x) for beta_x in (-0.5, 0.5)]
    a, b = shots
    gap = float(np.linalg.norm(np.subtract(b["goal_yz_m"], a["goal_yz_m"])))
    frames = []
    for t, pa, pb in zip(FRAMES, a["third_frame_xyz_m"], b["third_frame_xyz_m"]):
        delta = np.subtract(pb, pa)
        largest = float(np.max(np.abs(delta)))
        frames.append({"t_s": t, "distance_m": float(np.linalg.norm(delta)),
                       "max_coordinate_difference_m": largest,
                       "hard_error_boxes_disjoint": largest > 2 * EPSILON,
                       "round_to_cm_differs": bool(np.any(np.rint(100 * np.array(pa))
                                                          != np.rint(100 * np.array(pb))))})
    print(json.dumps({
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "scipy": scipy.__version__},
        "g_m_s2": G, "start_m": START, "times_s": TIMES.tolist(),
        "readings_m": READINGS.tolist(), "hard_coordinate_error_m": EPSILON,
        "shots": shots, "goal_separation_m": gap, "half_separation_m": gap / 2,
        "third_frames": frames,
    }, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
