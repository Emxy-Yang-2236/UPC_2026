"""Z10. Generate independent kicks, lock the two-frame forecasts, calibrate, then score."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import monotonic

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np
import scipy
from additional_information import fixed_step_reference
from flight import EVENTS
from predict import predict, summarize
from reference import baselines, solve, synthetic

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).resolve().parent
FORECAST_FILES = ("stable_spin.py", "flight.py", "predict.py", "observation_layer.py",
                  "reference.py", "additional_information.py", "evaluate.py")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, obj, *, compressed=False):
    if path.exists():
        raise FileExistsError(f"Refusing to replace an existing study artifact: {path}")
    text = json.dumps(obj, allow_nan=False, separators=(",", ":")) + "\n"
    data = gzip.compress(text.encode(), compresslevel=6, mtime=0) if compressed else text.encode()
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(data)
    temporary.replace(path)


def load(path):
    return json.loads(path.read_bytes())


def provenance(folder, paths):
    return {p: digest(folder / p) for p in paths}


def verify(folder, recorded):
    for filename, checksum in recorded.items():
        if digest(folder / filename) != checksum:
            raise ValueError(f"Checksum mismatch: {folder / filename}")


def study_settings():
    cfg = load(ROOT / "design/settings.json")
    spec = load(ROOT / "design/stable-spin.json")
    cfg["study"].update(cal=spec["cal"], blind=spec["blind"])
    cfg["study"]["seeds"].update(spec["truth_seeds"])
    cfg["sampling"].update(n_both=spec["proposal_count"], resample_cap=spec["propagation_cap"])
    return cfg, spec


def make_measurements(exact, cfg, spec, rng):
    q = cfg["observation"]["quantum_m"]
    measured = exact + rng.normal(0, spec["shared_sigma_m"], (1, 3))
    measured += rng.normal(0, spec["independent_sigma_m"], exact.shape)
    def quantize(points):
        return (q * np.floor(points / q + 0.5)).round(8).tolist()
    return {"rounded": quantize(exact), "tracking": quantize(measured)}


def gravity_checks(cfg):
    t = np.asarray(cfg["official"]["times"])[:, None]
    origin = np.asarray(cfg["official"]["r0"])
    g = cfg["physics"]["g"]
    records = []
    for velocity, expected in [([28, 2, 5], "in"), ([28, 11, 5], "out"), ([22, 0, 1.7], "ground")]:
        v = np.asarray(velocity)
        points = origin + t * v + 0.5 * t**2 * np.array([0, 0, -g])
        actual = baselines(points, cfg)["gravity"]
        arrival = min(cfg["official"]["gate"] / v[0], 2 * v[2] / g)
        assert actual["event"] == expected and abs(actual["T"] - arrival) < 1e-9
        if expected != "ground":
            yz = (origin + v * arrival + [0, 0, -0.5 * g * arrival**2])[1:]
            assert np.linalg.norm(yz - actual["point"]) < 1e-9
        records.append({"velocity_m_s": velocity, "event": expected, "arrival_s": arrival})
    return records


def generate(out, cfg, spec, workers):
    out.mkdir(parents=True, exist_ok=False)
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                           stderr=subprocess.DEVNULL, text=True).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        revision = None
    save_json(out / "config.json", {"plan": spec, "settings": cfg, "starting_commit": revision,
              "source": provenance(SOURCE, FORECAST_FILES),
              "design_files": provenance(ROOT / "design", ("stable-spin.json", "settings.json", "stable-spin.md")),
              "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
              "machine": platform.machine(), "system": platform.system(), "workers": workers,
              "numeric": "float64, one BLAS thread per process"})
    checks = []
    def audited_reference(v0, force, settings):
        sol, e, yz, arrival = solve(v0, force, settings)
        if len(checks) < 6:
            ref, f, other_yz, other_arrival = fixed_step_reference(v0, force, settings)
            frames = settings["official"]["times"]
            sep = np.linalg.norm(sol.sol(frames)[:3].T - ref.sol(frames)[:3].T, axis=1).max()
            dyz = None if yz is None else float(np.linalg.norm(np.subtract(yz, other_yz)))
            dt = abs(arrival - other_arrival)
            assert e == f and sep < 1e-4 and (dyz is None or dyz < 1e-4) and dt < 1e-4
            checks.append({"id": f"Z10-cal-{len(checks)+1:04d}", "event": EVENTS[e],
                           "early_max_m":float(sep), "crossing_diff_m":dyz, "time_diff_s":dt})
        return sol, e, yz, arrival
    files = []
    for split in ("cal", "blind"):
        exact, truth = synthetic(split, cfg, rounded=False, solver=audited_reference if split == "cal" else solve)
        rng = np.random.default_rng(spec["noise_seeds"][split])
        inputs, outcomes = [], []
        for i, (frame, target) in enumerate(zip(exact, truth), 1):
            assert frame["id"] == target["id"]
            shot = f"Z10-{split}-{i:04d}"
            inputs.append({"id": shot, **make_measurements(np.array(frame["xyz"]), cfg, spec, rng)})
            outcomes.append(dict(target, id=shot, exact_xyz=frame["xyz"]))
        save_json(out / f"{split}-inputs.json", inputs)
        save_json(out / f"{split}-truth.json", outcomes)
        files.extend((f"{split}-inputs.json", f"{split}-truth.json"))
        print(f"Generated {len(inputs)} {split} kicks.", flush=True)
    save_json(out / "reference-checks.json", {"gravity":gravity_checks(cfg), "reference":checks})
    save_json(out / "inputs-lock.json", provenance(out, files))


def forecast_config(cfg, spec, profile, scale=1.0):
    settings = deepcopy(cfg)
    if profile == "tracking":
        settings["observation"]["tracking_noise"] = {"sigma_m": spec["independent_sigma_m"],
                                                     "shared_bias_sigma_m": spec["shared_sigma_m"]}
        settings["sampling"]["proposal_halfwidth_m"] = spec["tracking_proposal_halfwidth_m"]
    settings["physics"]["beta_cap"] *= scale
    settings["physics"]["omega_cap"] *= scale
    return settings


def one_shot(job):
    i, shot, split, cfg, spec = job
    records = []
    def aerodynamic(profile, method, settings, seed, reuse=None):
        measured = dict(enumerate(shot[profile]))
        tracks = predict(measured, settings, [seed, i]) if reuse is None else reuse
        summary = summarize(*tracks, settings)
        records.append({"id": shot["id"], "profile": profile, "method": method,
                        "point": summary["point"], "hist": summary["hist"],
                        "p": None if summary["events"] is None else summary["events"][0],
                        "ess": summary["mixture_ess"]})
        return tracks
    seed = spec["inference_seeds"][split]
    for profile in ("rounded", "tracking"):
        settings = forecast_config(cfg, spec, profile)
        draws = aerodynamic(profile, "nominal", settings, seed)
        gravity = baselines(shot[profile], cfg)["gravity"]
        records.append({"id":shot["id"], "profile":profile, "method":"gravity", "point":gravity["point"],
                        "p":float(gravity["event"] == "in"), "ess":None})
        if profile == "tracking":
            for method, scale in spec["lift_scale"].items():
                aerodynamic(profile, method, forecast_config(cfg, spec, profile, scale), seed)
            weighted = deepcopy(settings)
            weighted["sampling"]["prior"] = spec["spin_rich_weights"]
            aerodynamic(profile, "spin_rich", weighted, seed, reuse=draws)
            if split == "blind" and i < spec["repeat_blind_first"]:
                aerodynamic(profile, "repeat", settings, spec["repeat_seed"])
    return records


def forecast_all(out, cfg, spec, workers):
    conf = load(out / "config.json")
    verify(SOURCE, conf["source"])
    verify(ROOT / "design", conf["design_files"])
    seals = load(out / "inputs-lock.json")
    predictions = []
    for split in ("cal", "blind"):
        name = f"{split}-inputs.json"
        verify(out, {name: seals[name]})
        inputs = load(out / name)
        jobs = ((i, s, split, cfg, spec) for i, s in enumerate(inputs))
        rows = []
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for index, forecast in enumerate(pool.map(one_shot, jobs, chunksize=2),1):
                rows.extend(forecast)
                if index % 100 == 0:
                    print(f"Forecasts {split}: {index}/{len(inputs)}", flush=True)
        dest = f"{split}-predictions.json.gz"
        save_json(out / dest, rows, compressed=True)
        predictions.append(dest)
    save_json(out / "predictions-lock.json", provenance(out, predictions))


def score_locked(out, cfg, spec):
    from stable_spin_score import fit_thresholds, score_run
    verify(out, load(out / "predictions-lock.json"))
    seals = load(out / "inputs-lock.json")
    verify(out, {name: sha for name, sha in seals.items() if name.startswith("cal-")})
    fit_thresholds(out, cfg, spec)
    save_json(out / "thresholds-lock.json", provenance(out, ("thresholds.json",)))
    verify(out, load(out / "thresholds-lock.json"))
    verify(out, seals)
    score_run(out, cfg, spec)
    outputs = [f.name for f in sorted(out.iterdir()) if f.is_file() and f.name != "complete.json"]
    save_json(out / "complete.json", {"files": provenance(out, outputs),
              "scorer_sha256":digest(SOURCE/"stable_spin_score.py")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--stage", choices=["all", "prepare", "forecast", "score"], default="all")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    cfg, spec = study_settings()
    start = monotonic()
    if args.stage in ("all", "prepare"):
        generate(args.out, cfg, spec, args.workers)
    if args.stage in ("all", "forecast"):
        forecast_all(args.out, cfg, spec, args.workers)
    if args.stage in ("all", "score"):
        if (args.out/"complete.json").exists() or (args.out/"thresholds-lock.json").exists():
            parser.error("Scoring requires a fresh result stage. Use a new output directory for a replay.")
        score_locked(args.out, cfg, spec)
    print(f"{args.stage} completed in {monotonic()-start:.1f} s", flush=True)


if __name__ == "__main__":
    main()
