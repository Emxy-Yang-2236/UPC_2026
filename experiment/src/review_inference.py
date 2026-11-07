"""Reproduce B03 release-parameter marginals and integrate a shared frame-time offset."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
from tempfile import NamedTemporaryFile

for thread_variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[thread_variable] = "1"

import numpy as np
import scipy
from scipy.spatial import ConvexHull

from event_sensitivity import fit_and_cross
from flight import draw_nuisance, early, finish, gravity
from predict import phase_cases, posterior_tracks
from reference import baselines


ROOT = Path(__file__).resolve().parents[2]
QUANTILES = (0.05, 0.50, 0.95)
PHASE_WIDTH_S = 0.001
PHASE_GRIDS = (12, 24)
PHASE_BUDGET_MULTIPLIER = 4


def quantiles(values, weights=None):
    """Left-continuous inverse empirical CDF, as in official.run_official."""
    if not len(values):
        return None
    if weights is None:
        return np.quantile(values, QUANTILES, method="inverted_cdf").tolist()
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order])
    return values[order][np.searchsorted(cumulative, np.asarray(QUANTILES)*cumulative[-1])].tolist()


def effective_size(weights):
    return float(weights.sum()**2 / (weights @ weights)) if len(weights) else 0.


def quantities(v0, wind, drag, spin, kind, physics):
    values = {"wind_speed_m_s": np.linalg.norm(wind[:, :2], axis=1),
              "wind_x_m_s": wind[:, 0], "wind_y_m_s": wind[:, 1]}
    if kind == "S":
        values.update(kappa_m_inv=drag, beta_norm_s_inv=np.linalg.norm(spin, axis=1),
                      beta_max_abs_component_s_inv=np.max(np.abs(spin), axis=1))
    elif kind == "E":
        u0 = v0-wind
        speed2 = np.einsum("ij,ij->i", u0, u0)
        cross_speed = np.linalg.norm(np.cross(spin, u0), axis=1)
        values.update(release_C_L=.38*np.tanh(5*physics["radius"]*cross_speed/speed2),
                      omega_norm_rad_s=np.linalg.norm(spin, axis=1),
                      omega_max_abs_component_rad_s=np.max(np.abs(spin), axis=1), drag_offset=drag)
    return values


def replay_model(cfg, kind, stream):
    """Replay B03's exact-time proposal in draw order, retaining release quantities."""
    p, sp, o = cfg["physics"], cfg["sampling"], cfg["official"]
    xyz, origin = np.asarray(o["xyz"]), np.asarray(o["r0"])
    lo, hi = np.asarray(p["velocity_lo"]), np.asarray(p["velocity_hi"])
    n, last, batch = sp["n_official"], o["times"][-1], sp["batch"]
    width, fraction = sp["proposal_halfwidth_m"]/last, sp["prior_proposal"]
    pv = 1/np.prod(hi-lo)
    half_bin = cfg["observation"]["quantum_m"]/2
    rng = np.random.default_rng(stream)
    prior_chunks, kept_chunks = [], []
    for offset in range(0, n, batch):
        count = min(n-offset, batch)
        eta = draw_nuisance(rng, count, kind, cfg)
        prior_velocity = rng.uniform(lo, hi, (count, 3))
        if kind != "D":
            prior_chunks.append(quantities(prior_velocity, *eta, kind, p))
        center = np.broadcast_to((xyz[-1]-origin)/last - .5*last*gravity(cfg), (count, 3)).copy()
        for _ in range(sp["inverse_steps"]):
            frames, _, _ = early(center, eta, kind, cfg)
            center += (xyz[-1]-frames[-1])/last
        local = center+rng.uniform(-width, width, (count, 3))
        v0 = np.where((rng.random(count) < fraction)[:, None], prior_velocity, local)
        in_prior = np.all((lo <= v0) & (v0 <= hi), axis=1)
        in_local = np.all(np.abs(v0-center) <= width, axis=1)
        density = fraction*pv*in_prior + (1-fraction)/(2*width)**3*in_local
        frames, velocities, alive = early(v0, eta, kind, cfg)
        keep = in_prior & alive[-1]
        for frame, measured in zip(frames, xyz):
            error = frame-measured
            keep &= np.all((-half_bin <= error) & (error < half_bin), axis=1)
        if np.any(keep):
            weight = pv/density[keep]
            kept_chunks.append((weight, v0[keep], *(a[keep] for a in eta), frames[-1][keep], velocities[-1][keep]))
    prior_values = {key: np.concatenate([chunk[key] for chunk in prior_chunks])
                    for key in prior_chunks[0]} if prior_chunks else {}
    if kept_chunks:
        weights, v0, wind, drag, spin, last_r, last_v = [np.concatenate(a) for a in zip(*kept_chunks)]
    else:
        weights, v0, wind, drag, spin, last_r, last_v = (np.empty((0, *tail)) for tail in
                                                          [(), (3,), (3,), (), (3,), (3,), (3,)])
    if len(weights) > sp["official_cap"]:
        raise RuntimeError("Nominal replay unexpectedly requires resampling.")
    event, yz, time = finish(last_r, last_v, (wind, drag, spin), kind, cfg, last)
    return {"prior": prior_values, "posterior_values": quantities(v0, wind, drag, spin, kind, p),
            "v0": v0, "wind": wind, "drag": drag, "spin": spin, "event": event, "yz": yz, "time": time,
            "mass": weights/n}


def arrivals(samples, cfg):
    """Columns: model, phase, first event, physical arrival, joint evidence mass."""
    last_time = cfg["official"]["times"][-1]
    model, phase, event, time, mass = samples.T
    inside = event == 0
    names = cfg["sampling"]["models"]
    model_probability = [float(mass[model == i].sum()/mass.sum()) for i in range(len(names))]
    model_ess = {name: effective_size(mass[model == i]) for i, name in enumerate(names)}
    ess = effective_size(mass)
    support = (ess >= cfg["study"]["official_min_ess"] and
               all(p < .1 or model_ess[name] >= cfg["study"]["min_ess"]
                   for name, p in zip(names, model_probability)))
    return {
        "positive_draws": len(samples),
        "ess": ess, "passes_prescribed_case_support_rule": support,
        "hits_by_model": {name: int(np.sum(model == i)) for i, name in enumerate(names)},
        "ess_by_model": model_ess,
        "direct_draws": int(inside.sum()),
        "direct_ess": effective_size(mass[inside]),
        "direct_probability": float(mass[inside].sum()/mass.sum()),
        "model_posterior": model_probability,
        "direct_release_q05_q50_q95_s": quantiles(time[inside], mass[inside]),
        "direct_remaining_q05_q50_q95_s": quantiles(time[inside]-last_time-phase[inside], mass[inside]),
    }


def phase_run(job):
    cfg, nodes, seed = job
    phase_cfg = dict(cfg, observation=dict(cfg["observation"], release_phase_halfwidth_s=PHASE_WIDTH_S,
                                           phase_nodes=nodes))
    sp, official = cfg["sampling"], cfg["official"]
    measured = {i: np.array(row) for i, row in enumerate(official["xyz"])}
    cases = phase_cases(measured, phase_cfg)
    model_streams = np.random.SeedSequence(seed).spawn(len(sp["models"]))
    size, extra = divmod(sp["n_official"], nodes)
    cap, cap_extra = divmod(sp["official_cap"], nodes)
    pieces = []
    for model_id, (kind, prior, stream) in enumerate(zip(sp["models"], sp["prior"], model_streams)):
        for i, ((node_prior, case), child) in enumerate(zip(cases, stream.spawn(nodes))):
            info, (event, _, time, mass) = posterior_tracks(measured, kind, case, size+(i < extra),
                                                           cap+(i < cap_extra), np.random.default_rng(child))
            if len(event) != info["hits"]:
                raise RuntimeError("Expected all positive proposals to fit inside the propagation cap.")
            shift = case["official"]["times"][-1]-official["times"][-1]
            pieces.append(np.column_stack((np.full(len(event), model_id), np.full(len(event), shift),
                                           event, time, prior*node_prior*mass)))
    return nodes, seed, np.concatenate(pieces)


def timing_report(cfg, runs):
    last = cfg["official"]["times"][-1]
    results = {}
    for nodes in PHASE_GRIDS:
        samples = [rows for size, _, rows in runs if size == nodes]
        pooled = np.concatenate(samples)
        pooled[:, -1] /= len(samples)
        result = arrivals(pooled, cfg)
        result["by_seed"] = {str(seed): arrivals(rows, cfg) for size, seed, rows in runs if size == nodes}
        result["mixture_evidence"] = float(pooled[:, -1].sum())
        total = pooled[:, -1].sum()
        result["phase_posterior_mean_ms"] = float(1000*np.average(pooled[:, 1], weights=pooled[:, -1]))
        result["phase_positive_probability"] = float(pooled[pooled[:, 1] > 0, -1].sum()/total)
        node_rows = []
        for node, quadrature_weight in zip(*np.polynomial.legendre.leggauss(nodes)):
            shift = (last+PHASE_WIDTH_S*node)-last
            selected = pooled[pooled[:, 1] == shift]
            node_rows.append({
                "phase_ms": float(1000*shift),
                "prior_probability": float(quadrature_weight/2),
                "hits_D_S_E": [int(np.sum(selected[:, 0] == i)) for i in range(len(cfg["sampling"]["models"]))],
                "posterior_probability": float(selected[:, -1].sum()/total),
                "model_mixture_evidence_at_phase": float(2*selected[:, -1].sum()/quadrature_weight),
                "ess": effective_size(selected[:, -1]),
            })
        if not np.isclose(sum(row["posterior_probability"] for row in node_rows), 1):
            raise RuntimeError("Quadrature node masses do not sum to one.")
        result["quadrature_nodes"] = node_rows
        results[str(nodes)] = result
    return results


def release_lift_support(p):
    """Largest E release C_L under the prescribed velocity box and wind disk."""
    # Write u/|u| = e and |u| = u_x/e_x. For a fixed omega, maximising
    # e_x |omega x e| gives (|omega| + |omega_perpendicular_to_x|)/2.
    # For n the normalized projection of omega perpendicular to e,
    # 2 e_x (omega.n) = xhat.(en^T+ne^T).omega + (xhat x omega).(e x n).
    # The symmetric operator has norm one. A cube corner attains both bounds.
    min_x = p["velocity_lo"][0]-p["wind_cap"]
    cap = p["omega_cap"]
    if min_x <= 0:
        raise ValueError("The prescribed release support assumes positive downfield airspeed.")
    ratio = cap*(np.sqrt(3)+np.sqrt(2))/(2*min_x)
    ceiling = .38*np.tanh(5*p["radius"]*ratio)
    # Equality occurs for u_y = u_z = (sqrt(6)/2-1)u_x and omega = (A,-A,-A).
    cross_axis = (np.sqrt(6)/2-1)*min_x
    v0 = np.array([p["velocity_lo"][0], cross_axis, cross_axis])
    if not np.all((np.asarray(p["velocity_lo"]) <= v0) & (v0 <= p["velocity_hi"])):
        raise ValueError("The velocity box excludes the claimed lift maximizer.")
    wind = np.array([[p["wind_cap"], 0., 0.]])
    spin = np.array([[cap, -cap, -cap]])
    feasible = quantities(v0[None, :], wind, np.zeros(1), spin, "E", p)["release_C_L"][0]
    np.testing.assert_allclose(feasible, ceiling, rtol=2e-15)
    return {"upper": float(ceiling), "saturation_scale": .38,
            "derivation": "For u_x>0 and e=u/|u|, e_x |omega cross e| <= "
                          "(|omega|+|omega_perp_to_x|)/2. The cube and u_x >= v_x,min-w_cap "
                          "give max |omega cross u|/|u|^2 = A(sqrt(3)+sqrt(2))/(2(v_x,min-w_cap)).",
            "attaining_limit_v0_m_s": v0.tolist(), "attaining_limit_wind_m_s": wind[0].tolist(),
            "attaining_limit_omega_rad_s": spin[0].tolist()}


def marginal(reference, values, weights, limits):
    lo, hi = limits
    lower, upper = lo+.02*(hi-lo), hi-.02*(hi-lo)
    prior_p98 = np.quantile(reference, .98, method="inverted_cdf")
    return {
        "support": list(limits), "low_2pct_cut": lower, "high_2pct_cut": upper,
        "prior_q05_q50_q95": quantiles(reference),
        "posterior_q05_q50_q95": quantiles(values, weights),
        "prior_mass_low_high_2pct": [float(np.mean(reference <= lower)), float(np.mean(reference >= upper))],
        "posterior_mass_low_high_2pct": [float(np.average(values <= lower, weights=weights)),
                                         float(np.average(values >= upper, weights=weights))],
        "prior_p98": float(prior_p98),
        "posterior_mass_at_or_above_prior_p98": float(np.average(values >= prior_p98, weights=weights)),
    }


def parameter_report(cfg, nominal):
    p, sp = cfg["physics"], cfg["sampling"]
    cl = release_lift_support(p)
    wc, bc, oc = p["wind_cap"], p["beta_cap"], p["omega_cap"]
    wind_limits = {"wind_speed_m_s": (0., wc), "wind_x_m_s": (-wc, wc), "wind_y_m_s": (-wc, wc)}
    limits = {
        "S": dict(wind_limits, kappa_m_inv=p["kappa"], beta_norm_s_inv=(0., np.sqrt(3)*bc)),
        "E": dict(wind_limits, release_C_L=(0., cl["upper"]), omega_norm_rad_s=(0., np.sqrt(3)*oc),
                  drag_offset=p["drag_offset"]),
    }
    output = {}
    for name, ranges in limits.items():
        rows = [nominal[name, seed] for seed in sp["official_seeds"]]
        weights = np.concatenate([row["mass"] for row in rows])
        parameters = {}
        for key, bounds in ranges.items():
            prior = np.concatenate([row["prior"][key] for row in rows])
            values = np.concatenate([row["posterior_values"][key] for row in rows])
            parameters[key] = marginal(prior, values, weights, bounds)
        cap, key = ((bc, "beta_max_abs_component_s_inv") if name == "S" else
                    (oc, "omega_max_abs_component_rad_s"))
        threshold = cap-.02*(2*cap)
        prior_max = np.concatenate([row["prior"][key] for row in rows])
        post_max = np.concatenate([row["posterior_values"][key] for row in rows])
        boundaries = {"signed_component_support": [-cap, cap], "max_abs_component_cut": threshold,
                      "analytic_prior_probability": 1-.96**3,
                      "sampled_prior_probability": float(np.mean(prior_max >= threshold)),
                      "posterior_probability": float(np.average(post_max >= threshold, weights=weights))}
        output[name] = {"unconditioned_prior_draws": len(prior_max), "positive_draws": len(weights),
                        "marginals": parameters, "any_component_within_2pct_of_signed_box_face": boundaries}
    erows = [nominal["E", seed] for seed in sp["official_seeds"]]
    masses = np.concatenate([row["mass"] for row in erows])
    prior_cl = np.concatenate([row["prior"]["release_C_L"] for row in erows])
    post_cl = np.concatenate([row["posterior_values"]["release_C_L"] for row in erows])
    prior_spin = np.concatenate([row["prior"]["omega_norm_rad_s"] for row in erows])
    post_spin = np.concatenate([row["posterior_values"]["omega_norm_rad_s"] for row in erows])
    output["E"]["release_C_L_support"] = cl
    output["E"]["release_C_L_saturation_check"] = {
        "cut": .98*.38, "sampled_prior_probability": float(np.mean(prior_cl >= .98*.38)),
        "posterior_probability": float(np.average(post_cl >= .98*.38, weights=masses))}
    output["E"]["omega_norm_above_single_component_cap"] = {
        "cut_rad_s": oc, "analytic_prior_probability": 1-np.pi/6,
        "sampled_prior_probability": float(np.mean(prior_spin > oc)),
        "posterior_probability": float(np.average(post_spin > oc, weights=masses))}
    output["analytic_checks"] = {
        "S_kappa_prior_q05_q50_q95": (p["kappa"][0]+np.array(QUANTILES)*np.ptp(p["kappa"])).tolist(),
        "uniform_disk_speed_prior_q05_q50_q95_m_s": (wc*np.sqrt(QUANTILES)).tolist(),
        "uniform_disk_speed_prior_low_high_2pct": [.02**2, 1-.98**2]}
    return output


def verify_nominal(cfg, nominal, b03):
    """Compare evidence and each propagated track in original official.py order."""
    sp = cfg["sampling"]
    official = json.loads((b03/"official.json").read_bytes())
    errors, seeds, sampled = {}, {seed: {} for seed in sp["official_seeds"]}, []
    with np.load(b03/"official_tracks.npz") as frozen:
        for i, (kind, prior) in enumerate(zip(sp["models"], sp["prior"])):
            for j, seed in enumerate(sp["official_seeds"]):
                row = nominal[kind, seed]
                mass = row["mass"]
                metrics = {"n": sp["n_official"], "hits": len(mass), "evidence": float(mass.sum()),
                           "second": float(mass @ mass), "ess": effective_size(mass)}
                seeds[seed][kind] = metrics
                stored = official["replicates"][j]["models"][i]
                for key, value in metrics.items():
                    np.testing.assert_allclose(value, stored[key], rtol=2e-12, atol=0)
            rows = [nominal[kind, seed] for seed in sp["official_seeds"]]
            errors[kind] = {}
            for key, field, atol in [("event", "event", 0), ("yz", "yz", 1e-11),
                                     ("time", "time", 1e-12), ("mass", "evidence_mass", 0)]:
                replay = np.concatenate([row[key] for row in rows])
                if key == "mass":
                    replay = replay/len(rows)
                stored = frozen[f"{kind}_{field}"]
                np.testing.assert_allclose(replay, stored, rtol=1e-13 if key == "mass" else 0, atol=atol)
                errors[kind][key] = float(np.max(np.abs(replay-stored), initial=0))
            for row in rows:
                count = len(row["mass"])
                sampled.append(np.column_stack((np.full(count, i), np.zeros(count), row["event"],
                                                row["time"], prior*row["mass"]/len(rows))))
    result = arrivals(np.concatenate(sampled), cfg)
    np.testing.assert_allclose(result["direct_release_q05_q50_q95_s"], official["gate_time_q05_q50_q95_s"],
                               rtol=0, atol=1e-12)
    np.testing.assert_allclose(result["ess"], official["mixture_ess"], rtol=2e-12)
    np.testing.assert_allclose(result["model_posterior"], official["model_posterior"], rtol=2e-12)
    return {"per_seed_per_model": seeds, "max_absolute_error_against_frozen_tracks": errors,
            "pooled": result}


def rounded_pair(cfg, nominal):
    """Find the diameter of the finite B03 direct-entry point cloud and restore its launches."""
    labels, points = [], []
    for kind in cfg["sampling"]["models"]:
        offset = 0
        for seed in cfg["sampling"]["official_seeds"]:
            row = nominal[kind, seed]
            direct = np.flatnonzero(row["event"] == 0)
            labels.extend((kind, seed, index, offset+index) for index in direct)
            points.extend(row["yz"][direct])
            offset += len(row["event"])
    points = np.asarray(points)
    hull_ids = ConvexHull(points).vertices
    hull = points[hull_ids]
    distances = np.linalg.norm(hull[:, None, :]-hull[None, :, :], axis=2)
    indices = np.unravel_index(np.argmax(distances), distances.shape)
    entries = []
    for point_id in sorted(hull_ids[list(indices)]):
        kind, seed, index, pooled_index = labels[point_id]
        if kind != "S":
            raise RuntimeError("The frozen B03 diameter pair has changed force models.")
        row = nominal[kind, seed]
        entries.append({"model": kind, "pooled_model_index": int(pooled_index), "seed": seed,
                        "within_seed_index": int(index), "v0_m_s": row["v0"][index].tolist(),
                        "wind_m_s": row["wind"][index].tolist(), "kappa_m_inv": float(row["drag"][index]),
                        "beta_s_inv": row["spin"][index].tolist(), "frozen_yz_m": row["yz"][index].tolist(),
                        "frozen_T_s": float(row["time"][index])})
    return entries, {"searched_direct_crossings": len(points), "convex_hull_vertices": len(hull),
                     "frozen_RK4_separation_m": float(distances[indices]),
                     "scope": "Diameter of the finitely sampled B03 crossings under rounded observations."}


def timing_controls(cfg):
    """Exact coordinate centres, freely fitted constant acceleration, same true-time convention."""
    o = cfg["official"]
    times, xyz, origin = np.asarray(o["times"]), np.asarray(o["xyz"]), np.asarray(o["r0"])
    t, _, velocity, acceleration = fit_and_cross(xyz, origin, times[0], o["gate"])
    scaled = t/times[0]
    interpolation = np.array([scaled*(2-scaled), scaled*(scaled-1)/2])
    derivative = (interpolation @ (velocity[0]+times*acceleration[0]))/(velocity[0]+t*acceleration[0])

    def refit(shift):
        altered = dict(cfg, official=dict(o, times=times+shift))
        return baselines(xyz, altered)["constant_a"]

    step = 1e-7
    central = (refit(step)["T"]-refit(-step)["T"])/(2*step)
    np.testing.assert_allclose(central, derivative, rtol=1e-8)
    endpoints = {}
    for shift in (-PHASE_WIDTH_S, 0., PHASE_WIDTH_S):
        result = refit(shift)
        endpoints[f"{1000*shift:+.0f}ms"] = dict(result, remaining_s=result["T"]-(times[-1]+shift))
    return {"condition": "Fixed coordinate centres; solve a fresh constant-acceleration control at "
                         "the two true times. T from release, remaining from the shifted second frame.",
            "local_dT_dphase_s_per_s": float(derivative), "central_difference_s_per_s": float(central),
            "fixed_phase_controls": endpoints}


def fixed_aero_offsets(cfg, filename):
    output = {}
    with filename.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["scenario"] not in ("phase_minus1ms", "phase_plus1ms", "phase_minus5ms", "phase_plus5ms"):
                continue
            supported = row["ess_pass"].lower() == "true"
            output[row["scenario"]] = {
                "ess": float(row["mixture_ess"]), "passes_prescribed_case_support_rule": supported,
                "direct_release_q05_q50_q95_s": ([float(row[key]) for key in
                                                  ("time_q05_s", "time_median_s", "time_q95_s")]
                                                 if supported else None)}
    if len(output) != 4:
        raise ValueError("Expected four archived Z05 fixed offsets.")
    return {"proposals_per_model_per_seed": cfg["sampling"]["n_official"],
            "rule": "Frozen Z05 fixed-phase sensitivity. Quantiles are shown only if the prescribed "
                    "support rule passed; each row conditions on its stated phase.",
            "cases": output}


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT/"report/evidence/review-inference.json")
    parser.add_argument("--workers", type=int, default=2, help="Parallel seed/grid jobs for the timing calculation")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    settings, b03 = ROOT/"design/settings.json", ROOT/"experiment/runs/B03"
    fixed = ROOT/"experiment/runs/Z05/factors.csv"
    cfg = json.loads(settings.read_bytes())
    sp, observations = cfg["sampling"], cfg["official"]
    if "tracking_noise" in cfg["observation"] or len(observations["times"]) != 2:
        raise ValueError("This diagnostic expects B03's two rounded frames.")
    expected = json.loads((b03/"complete.json").read_bytes())["sha256"]
    input_files = [settings, b03/"official.json", b03/"official_tracks.npz", fixed]
    digests = {path.relative_to(ROOT).as_posix(): checksum(path) for path in input_files}
    if (digests["design/settings.json"] != json.loads((b03/"start.json").read_bytes())["settings_sha256"]
            or any(checksum(b03/key) != expected[key] for key in ("official.json", "official_tracks.npz"))):
        raise ValueError("The nominal settings or B03 evidence differ from the frozen manifests.")
    nominal = {}
    for seed in sp["official_seeds"]:
        streams = np.random.SeedSequence(seed).spawn(len(sp["models"]))
        for kind, stream in zip(sp["models"], streams):
            nominal[kind, seed] = replay_model(cfg, kind, stream)
    replay = verify_nominal(cfg, nominal, b03)
    marginals = parameter_report(cfg, nominal)
    pair, diameter = rounded_pair(cfg, nominal)
    del nominal
    phase_sampling = dict(sp, n_official=sp["n_official"]*PHASE_BUDGET_MULTIPLIER,
                          official_cap=sp["official_cap"]*PHASE_BUDGET_MULTIPLIER)
    phase_cfg = dict(cfg, sampling=phase_sampling)
    jobs = [(phase_cfg, n, seed) for n in PHASE_GRIDS for seed in sp["official_seeds"]]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        runs = list(pool.map(phase_run, jobs))
    grids = timing_report(phase_cfg, runs)
    differences = {key: float(1000*np.max(np.abs(np.asarray(grids[str(PHASE_GRIDS[0])][key])-
                                                  grids[str(PHASE_GRIDS[1])][key])))
                   for key in ("direct_release_q05_q50_q95_s", "direct_remaining_q05_q50_q95_s")}
    sources = [Path(__file__), *(ROOT/"experiment/src"/name for name in
                                ("flight.py", "predict.py", "reference.py", "event_sensitivity.py"))]
    processor = (subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
                 if platform.system() == "Darwin" else platform.processor())
    data = {
        "command": "python experiment/src/review_inference.py",
        "scope": "One prescribed kick. Model-conditional parameter marginals, finite rounded-fit "
                 "witness candidates and arrival-time sensitivity; no measured spin, wind or goal outcome.",
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
                        "architecture": platform.machine(), "processor": processor,
                        "backend": "CPU, vectorized float64, one BLAS thread per worker"},
        "input_sha256": digests, "source_sha256": {p.relative_to(ROOT).as_posix(): checksum(p) for p in sources},
        "models": sp["models"], "model_prior": sp["prior"], "seeds": sp["official_seeds"],
        "quantiles": list(QUANTILES), "nominal_replay": replay,
        "parameter_method": {
            "condition": "Exact release and frame times, 5 mm coordinate half-bins, positive B03 likelihood. "
                         "Within each model all positive draws retain their original importance weights. "
                         "D has zero accepted draws; kappa is a free parameter of S and D, omega and C_L are E-specific.",
            "prior_reference": "All unselected per-model nuisance and independent original-prior velocities "
                               "drawn by the two official proposal streams; one unit of mass per prior draw. "
                               "Independent velocity components use B03's launch box. Wind is uniform by disk area. "
                               "Beta and omega have three independent uniform components within their respective signed cubes.",
            "release_C_L": "0.38 tanh(5 R |omega cross (v0-w)| / |v0-w|^2); compute from each true prior "
                           "or posterior launch velocity. Beta in S is an effective force coefficient.",
            "boundary_bands": "Each scalar band is 2% of the full interval of the reported scalar. For a cube "
                              "face the width is 2% of one signed component's full width (e.g. max|omega_i|>=62.4). "
                              "The spin norm has its own upper limit sqrt(3)*65. C_L uses its induced prior "
                              "support and separately reports distance to the 0.38 saturation scale.",
        },
        "parameter_marginals": marginals, "rounded_pair_search": diameter, "rounded_pair_candidates": pair,
        "timing": {
            "condition": "Uniform phase on [-1,+1] ms before conditioning; actual times are (50,100) ms "
                         "+ the same phase. Hold both displayed positions fixed. Marginalize with "
                         "Gauss-Legendre prior weights and each phase/model's importance evidence. Quantiles "
                         "condition on first direct entry. Remaining time is T minus the actual second-frame time.",
            "sampler": "Each seed spawns one stream per model and independent streams per quadrature node. "
                       "At every node refit the local velocity proposal to the shifted last frame, using "
                       "the full original prior mixture and the original 5 mm hard-box likelihood. "
                       "Pool equal seed budgets; retain every positive draw. ESS uses squared joint masses.",
            "proposals_per_model_per_seed_per_grid": phase_sampling["n_official"],
            "overall_propagation_cap_per_model_per_seed_per_grid": phase_sampling["official_cap"],
            "batch_max": phase_sampling["batch"], "primary_nodes": PHASE_GRIDS[-1],
            "thresholds": {"pooled_ess": cfg["study"]["official_min_ess"],
                           "model_ess_if_model_posterior_at_least_0.1": cfg["study"]["min_ess"]},
            "grids": grids, "max_abs_grid_difference_ms": differences,
            "fixed_phase_aerodynamic_reference": fixed_aero_offsets(cfg, fixed),
            "quadratic_control": timing_controls(cfg),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    output = json.dumps(data, allow_nan=False, indent=2)+"\n"
    with NamedTemporaryFile("w", dir=args.out.parent, encoding="utf-8", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(output)
            stream.close()
            temporary.replace(args.out)
        finally:
            temporary.unlink(missing_ok=True)
    print(f"Nominal hits {replay['pooled']['hits_by_model']}; "
          f"phase-marginal release quantiles {grids[str(PHASE_GRIDS[-1])]['direct_release_q05_q50_q95_s']}")


if __name__ == "__main__":
    main()
