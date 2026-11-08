"""Reanalyse locked tests with a probability baseline, and vary timing and tracking jointly."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import platform
from zipfile import ZipFile

import numpy as np
import scipy
from scipy.optimize import minimize
from scipy.special import expit

from flight import cell_edges, cell_geometry
from predict import pool_phase_tracks, predict, region, summarize

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ("rounded", "tracking")
SEEDS = (8111, 8117)


def archived(archive, study, split, cfg):
    def read(name):
        return json.loads(archive.read(name))

    name = f"{split}-predictions.json.gz"
    compressed = archive.read(name)
    sealed = (read(f"{split}-lock.json")["sha256"] if study == "Z09"
              else read("predictions-lock.json")[name])
    assert hashlib.sha256(compressed).hexdigest() == sealed
    aero = "both" if study == "Z09" else "nominal"
    forecasts = {(row["id"], row["profile"], row["method"]): row
                 for row in json.loads(gzip.decompress(compressed))
                 if row["method"] in (aero, "gravity")}
    inputs = {row["id"]: row for row in read(f"{split}-inputs.json")}
    truth = {row["id"]: row for row in read(f"{split}-truth.json")}
    assert inputs.keys() == truth.keys()
    observations = cfg["official"]
    times = np.array(observations["times"])
    anchor = np.array(observations["r0"])
    g = np.array([0, 0, -cfg["physics"]["g"]])
    centres, _ = cell_geometry(cell_edges(cfg))
    data = {p: [] for p in PROFILES}
    for sid, real in truth.items():
        for p in PROFILES:
            a, b = (forecasts[sid, p, method] for method in (aero, "gravity"))
            reading = np.array(inputs[sid][p])
            velocity = times @ (reading - anchor - .5*times[:, None]**2*g) / (times @ times)
            assert velocity[0] > 0
            t = (observations["gate"] - anchor[0]) / velocity[0]
            y, z = (anchor + t*velocity + .5*t*t*g)[1:]
            margin = min(observations["half_width"] - abs(y),
                         z - cfg["physics"]["radius"], observations["height"] - z)
            p_gravity = b.get("p", b.get("p_in"))
            p_aero = a.get("p", a.get("p_in"))
            if p_aero is None:
                p_aero = a["events"][0]
            if p_gravity is None:
                p_gravity = b["events"][0]
            assert int(margin > 0) == p_gravity
            hit = int(real["event"] == "in")
            mean_error = None
            gravity_error = None
            if hit and split == "blind":
                hist = np.asarray(a["hist"])
                assert np.isclose(hist.sum(), 1) and b["point"] is not None
                assert np.allclose((y, z), b["point"])
                mean_error = float(np.linalg.norm(hist @ centres - real["yz"]))
                gravity_error = float(np.linalg.norm(np.array([y, z]) - real["yz"]))
            data[p].append((margin, hit, p_aero, p_gravity, mean_error, gravity_error, real["family"]))
    return data


def calibrate(calibration):
    """Fit a monotone, ridge-regularized event probability to the gravity margin."""
    margins = np.array([r[0] for r in calibration])
    events = np.array([r[1] for r in calibration])
    center, scale = margins.mean(), margins.std()
    assert scale > 0 and events.min() == 0 and events.max() == 1
    design = np.column_stack((np.ones(len(margins)), (margins-center)/scale))

    def objective(coef):
        score = design @ coef
        cost = np.logaddexp(0, score).sum() - events @ score + .5*coef[1]**2
        grad = design.T @ (expit(score)-events) + np.array([0., coef[1]])
        return cost, grad

    fit = minimize(objective, [0., 1.], jac=True, bounds=[(None,None),(0,None)],
                   method="L-BFGS-B", options={"ftol": 1e-12, "gtol": 1e-8})
    if not fit.success:
        raise RuntimeError(fit.message)
    return dict(center_m=float(center), scale_m=float(scale),
                intercept=float(fit.x[0]), slope=float(fit.x[1]))


def score(rows, fit):
    m, outcome, aero, binary = np.array([r[:4] for r in rows]).T
    soft = expit(fit["intercept"] + fit["slope"]*(m-fit["center_m"])/fit["scale_m"])
    loss = (np.array([aero, binary, soft]) - outcome)**2
    error = np.array([r[4:6] for r in rows if r[1]])
    rng = np.random.default_rng(79151)

    def interval(delta):
        samples = rng.integers(0, len(delta), (4000, len(delta)))
        return np.quantile(delta[samples].mean(axis=1), [.025, .975]).tolist()

    return {
        "shots": len(rows), "entries": len(error), "brier_aero_binary_soft": loss.mean(axis=1).tolist(),
        "brier_aero_minus_soft_interval95": interval(loss[0]-loss[2]),
        "mean_point_error_aero_centroid_gravity_m": error.mean(axis=0).tolist(),
        "centroid_minus_gravity_interval95_m": interval(error[:, 0]-error[:, 1]),
    }


def joint_scenario(cfg, phase, tracking):
    case = copy.deepcopy(cfg)
    case["sampling"]["official_cap"] = 8192
    obs = case["observation"]
    obs.update(release_phase_halfwidth_s=phase, phase_nodes=12)
    if tracking:
        obs["tracking_noise"] = dict(sigma_m=.006, shared_bias_sigma_m=.008)
        case["sampling"]["proposal_halfwidth_m"] = .025
    readings = dict(enumerate(case["official"]["xyz"]))
    draws = [predict(readings, case, seed, official=True) for seed in SEEDS]
    pooled = [pool_phase_tracks(
        [(infos[i], tracks[i]) for infos, tracks in draws], [.5, .5])
        for i in range(len(case["sampling"]["models"]))]
    infos, tracks = zip(*pooled)
    report = summarize(infos, tracks, case)
    hist = np.array(report["hist"])
    centres, cell_area = cell_geometry(cell_edges(case))
    mask = region(hist)
    assert hist.sum() > 0 and report["mixture_ess"] >= case["study"]["official_min_ess"]
    assert all(weight < .1 or info["ess"] >= case["study"]["min_ess"]
               for weight, info in zip(report["model_posterior"], infos))
    arrival = []
    weights = []
    for prior, (event, _, times, mass) in zip(case["sampling"]["prior"], tracks):
        arrival.extend(times[event == 0])
        weights.extend(prior*mass[event == 0])
    order = np.argsort(arrival)
    cumulative = np.cumsum(np.asarray(weights)[order])
    quantiles = np.asarray(arrival)[order][np.searchsorted(cumulative, np.array([.05,.5,.95])*cumulative[-1])]
    seed_means = []
    for args in draws:
        h = np.array(summarize(*args, case)["hist"])
        assert h.sum() > 0
        seed_means.append((h @ centres).tolist())
    return dict(phase_halfwidth_ms=phase*1000, tracking=tracking,
                p_direct=report["events"][0], area_m2=float(cell_area[mask].sum()),
                region_cells=int(mask.sum()), mass=float(hist[mask].sum()),
                centroid_yz_m=(hist @ centres).tolist(), seed_centroid_yz_m=seed_means,
                median_and_central90_ms=(1000*quantiles).tolist(),
                mixture_ess=report["mixture_ess"], model_ess=[info["ess"] for info in infos])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads((ROOT / "design/settings.json").read_bytes())
    result = {"retrospective": {}, "prescribed_scenarios": []}
    for study in ("Z09", "Z10"):
        path = ROOT / "report/evidence" / (study.lower()+"-replay.zip")
        with ZipFile(path) as archive:
            calibration = archived(archive, study, "cal", cfg)
            test = archived(archive, study, "blind", cfg)
        for p in PROFILES:
            fit = calibrate(calibration[p])
            result["retrospective"][study+"/"+p] = {
                "calibration_kicks": len(calibration[p]), "fit": fit, **score(test[p], fit)}
    for tracking in (False, True):
        for phase in (0., .001):
            result["prescribed_scenarios"].append(joint_scenario(cfg, phase, tracking))
    result["settings"] = {
        "seeds": list(SEEDS), "proposals_per_model_per_seed": cfg["sampling"]["n_official"],
        "propagation_cap_per_model_per_seed": 8192, "phase_nodes": 12,
        "tracking_independent_sigma_mm": 6, "tracking_shared_sigma_mm": 8,
        "nominal_proposal_halfwidth_mm": 1000*cfg["sampling"]["proposal_halfwidth_m"],
        "tracking_proposal_halfwidth_mm": 25,
    }
    sources = ("design/settings.json", "report/evidence/z09-replay.zip",
               "report/evidence/z10-replay.zip", "experiment/src/flight.py",
               "experiment/src/predict.py", "experiment/src/observation_layer.py",
               "experiment/src/revision_controls.py")
    result["input_sha256"] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                              for p in sources}
    result["environment"] = dict(python=platform.python_version(), numpy=np.__version__,
                                 scipy=scipy.__version__)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    for key, row in result["retrospective"].items():
        print(key, row["brier_aero_binary_soft"], row["mean_point_error_aero_centroid_gravity_m"])
    for row in result["prescribed_scenarios"]:
        print(row["tracking"], row["phase_halfwidth_ms"], row["region_cells"],
              row["p_direct"], row["mixture_ess"])


if __name__ == "__main__":
    main()
