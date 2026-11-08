"""Z11. Separate the lift priors and repeat calibration on independent synthetic batches."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import platform
from statistics import mean
from zipfile import ZipFile

from stable_spin import (ROOT, forecast_config, make_measurements, save_json,
                         study_settings)

import numpy as np
import scipy

from predict import posterior_tracks, summarize
from reference import baselines, synthetic
from stable_spin_score import cell_distribution, grid, quantile_entry, reference_cell

ARMS = {
    "nominal": (1., 1.),
    "S_half": (.5, 1.),
    "E_half": (1., .5),
    "both_half": (.5, .5),
}
METHODS = (*ARMS, "gravity")
BATCHES = 8
SHOTS_PER_BATCH = 90
SEEDS = [{"truth": 128003 + 11*i, "measurement": 128004 + 11*i,
          "inference": 128005 + 11*i} for i in range(BATCHES)]
BOOTSTRAP_SEED = 128113
BOOTSTRAP_REPEATS = 4000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def forecast(job):
    reading, seed, index, cfg = job
    spec = cfg["sampling"]
    obs = dict(enumerate(np.asarray(reading["tracking"])))
    children = np.random.SeedSequence([seed, index]).spawn(3)
    assert spec["models"] == ["D", "S", "E"]
    # A prior change in one force model leaves the other models' draws untouched.
    pieces = {}
    for kind, child, field in zip(spec["models"], children, (None, "beta_cap", "omega_cap")):
        for scale in ((1.,) if field is None else (1., .5)):
            case = cfg if scale == 1. else deepcopy(cfg)
            if scale != 1.:
                case["physics"][field] *= scale
            pieces[kind, scale] = posterior_tracks(
                obs, kind, case, spec["n_both"], spec["resample_cap"],
                np.random.default_rng(child))
    rows = []
    for method, (s, e) in ARMS.items():
        parts = [pieces["D", 1.], pieces["S", s], pieces["E", e]]
        result = summarize(*zip(*parts), cfg)
        rows.append(dict(id=reading["id"], method=method, point=result["point"], hist=result["hist"],
                         p=None if result["events"] is None else result["events"][0],
                         ess=result["mixture_ess"]))
    g = baselines(reading["tracking"], cfg)["gravity"]
    rows.append(dict(id=reading["id"], method="gravity", point=g["point"],
                     p=float(g["event"] == "in"), ess=None))
    return rows


def make_batch(batch, cfg, spec):
    setup = deepcopy(cfg)
    seeds = SEEDS[batch]
    setup["study"]["cal"] = SHOTS_PER_BATCH
    setup["study"]["seeds"]["cal"] = seeds["truth"]
    exact, truth = synthetic("cal", setup, rounded=False)
    rng = np.random.default_rng(seeds["measurement"])
    readings, targets = [], []
    for i, (frame, actual) in enumerate(zip(exact, truth), 1):
        assert frame["id"] == actual["id"]
        sid = f"Z11-{batch+1:02d}-{i:03d}"
        reading = make_measurements(np.array(frame["xyz"]), setup, spec, rng)["tracking"]
        readings.append({"id": sid, "tracking": reading})
        targets.append(dict(actual, id=sid))
    return readings, targets


def open_z10(path):
    with ZipFile(path) as z:
        def read(name, lock):
            data = z.read(name)
            assert sha(data) == json.loads(z.read(lock))[name]
            return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)

        inputs = read("blind-inputs.json", "inputs-lock.json")
        truth = read("blind-truth.json", "inputs-lock.json")
        old = read("blind-predictions.json.gz", "predictions-lock.json")
        cuts_bytes = z.read("thresholds.json")
        assert sha(cuts_bytes) == json.loads(z.read("thresholds-lock.json"))["thresholds.json"]
    retained = {(r["id"], r["method"]): r for r in old if r["profile"] == "tracking"
                and r["method"] in ("nominal", "narrow", "gravity")}
    threshold = json.loads(cuts_bytes)["pooled"]["tracking"]["nominal"]["threshold"]
    return inputs, truth, retained, threshold


def check_replay(predictions, old):
    retained = {"nominal": "nominal", "both_half": "narrow", "gravity": "gravity"}
    for row in predictions:
        if row["method"] not in retained:
            continue
        ref = old[row["id"], retained[row["method"]]]
        for field in ("point", "hist", "p", "ess"):
            if field not in row:
                continue
            a, b = row[field], ref[field]
            assert ((a is None and b is None) or
                    (a is not None and b is not None and np.allclose(a, b, atol=1e-10, rtol=1e-9))), (
                        row["id"], row["method"], field)
    return sum(r["method"] in retained for r in predictions)


def forecasts(readings, seeds, cfg, pool, label):
    jobs = ((r, seed, i, cfg) for i, (r, seed) in enumerate(zip(readings, seeds)))
    out = []
    for i, rows in enumerate(pool.map(forecast, jobs, chunksize=3), 1):
        out.extend(rows)
        if i % 100 == 0 or i == len(readings):
            print(f"{label}: {i}/{len(readings)} forecasts", flush=True)
    return out


def evaluate_goals(predictions, truth, geometry):
    edges, centres, _, diagonal = geometry
    targets = {r["id"]: r for r in truth if r["event"] == "in"}
    for p in predictions:
        if p["id"] not in targets:
            continue
        actual = targets[p["id"]]
        distribution = cell_distribution(p, centres, diagonal)
        cid = reference_cell(actual, edges)
        score = None if distribution is None else float(distribution[0][cid])
        rank = None if distribution is None else int(np.flatnonzero(distribution[1] == cid)[0])+1
        error = None if p["point"] is None else float(np.linalg.norm(np.subtract(p["point"], actual["yz"])))
        yield {"id": p["id"], "family": actual["family"], "method": p["method"], "score": score,
               "rank": rank, "error_m": error,
               "sorted_scores": None if distribution is None else np.sort(distribution[0])}


def calibration(batches, cfg, target, out):
    rows = []
    geometry = grid(cfg)
    cuts = []
    for i, (predictions, truth) in enumerate(batches, 1):
        goals = list(evaluate_goals(predictions, truth, geometry))
        cuts.append({m: quantile_entry([r["score"] for r in goals if r["method"] == m], target)
                     for m in METHODS})
        for r in goals:
            rows.append(dict(batch=i, id=r["id"], family=r["family"], method=r["method"], score=r["score"]))
    write_csv(out/"calibration-scores.csv", rows)
    return cuts


def write_csv(path, rows):
    with path.open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_scores(predictions, truth, cuts, cfg, fixed_threshold, out):
    geometry = grid(cfg)
    _, _, areas, _ = geometry
    area = float(areas[0])
    assert np.allclose(areas, area)
    goals = list(evaluate_goals(predictions, truth, geometry))
    rows = []
    for r in goals:
        cells = r.pop("sorted_scores")
        r["fixed_z10_nominal_hit"] = ("" if r["method"] == "gravity" else
                                    int(r["score"] is not None and r["score"] <= fixed_threshold))
        for i, cut in enumerate(cuts, 1):
            limit = cut[r["method"]]["threshold"]
            r[f"cells_{i}"] = 0 if cells is None else int(np.searchsorted(cells, limit, side="right"))
        rows.append(r)
    write_csv(out/"test-goal-scores.csv", rows)
    summaries = []
    for i, cut in enumerate(cuts, 1):
        by_group = {}
        for scope in ("all", "stable_spin"):
            group = [r for r in rows if scope == "all" or r["family"] == scope]
            by_group[scope] = {}
            for m in METHODS:
                subset = [r for r in group if r["method"] == m]
                limit = cut[m]["threshold"]
                by_group[scope][m] = {
                    "goals": len(subset),
                    "hits": sum(r["score"] is not None and r["score"] <= limit for r in subset),
                    "available": sum(r["score"] is not None for r in subset),
                    "mean_area_m2": area * mean(r[f"cells_{i}"] for r in subset),
                }
        summaries.append(dict(batch=i, calibration_entries=cut["nominal"]["n"], cuts=cut, test=by_group))
    return rows, summaries


def paired_prior(rows):
    stable = [r for r in rows if r["family"] == "stable_spin" and r["method"] in ARMS]
    indexed = {(r["id"], r["method"]): r for r in stable}
    ids = sorted({r["id"] for r in stable})
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    result = {}
    for m in ARMS:
        current = [indexed[s, m] for s in ids]
        common = [s for s in ids if all(indexed[s, k]["error_m"] is not None for k in (m, "nominal"))]
        delta = np.array([indexed[s, m]["error_m"]-indexed[s, "nominal"]["error_m"] for s in common])
        draw = rng.integers(0, len(common), size=(BOOTSTRAP_REPEATS, len(common)))
        result[m] = {
            "goals": len(ids), "paired_points": len(common),
            "fixed_nominal_hits": sum(r["fixed_z10_nominal_hit"] for r in current),
            "mean_error_m": mean(r["error_m"] for r in current if r["error_m"] is not None),
            "mean_true_rank": mean(r["rank"] for r in current if r["rank"] is not None),
            "error_difference_m": float(delta.mean()),
            "error_difference_interval95_m": np.quantile(delta[draw].mean(axis=1), [.025,.975]).tolist(),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    out = args.out
    out.mkdir(parents=True, exist_ok=False)
    config, spec = study_settings()
    cfg = forecast_config(config, spec, "tracking")
    archive = ROOT/"report/evidence/z10-replay.zip"
    files = ["design/settings.json", "design/stable-spin.json", "design/calibration-robustness.md",
             "report/evidence/z10-replay.zip",
             *[f"experiment/src/{name}.py" for name in ("calibration_robustness", "stable_spin",
                "stable_spin_score", "reference", "predict", "observation_layer", "flight")]]
    plan = dict(study="Z11", batch_shots=SHOTS_PER_BATCH, seeds=SEEDS, arm_scales=ARMS,
                bootstrap_seed=BOOTSTRAP_SEED, bootstrap_repeats=BOOTSTRAP_REPEATS, target=spec["target"],
                proposals_per_model=spec["proposal_count"], cap_per_model=spec["propagation_cap"],
                test_inference_seed=spec["inference_seeds"]["blind"],
                sources_sha256={name: sha((ROOT/name).read_bytes()) for name in files},
                versions=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__))
    save_json(out/"config.json", plan)
    inputs, truth, old, nominal_cut = open_z10(archive)
    generated = [make_batch(i, config, spec) for i in range(BATCHES)]
    save_json(out/"calibration-inputs.json.gz", [r[0] for r in generated], compressed=True)
    save_json(out/"calibration-truth.json.gz", [r[1] for r in generated], compressed=True)
    # Forecasts use position data only. Lock all forecasts before fitting cutoffs.
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        batch_predictions = [forecasts(readings, [s["inference"]]*len(readings), cfg, pool, f"batch {i}")
                             for i, ((readings, _), s) in enumerate(zip(generated, SEEDS), 1)]
        test = forecasts(inputs, [spec["inference_seeds"]["blind"]]*len(inputs), cfg, pool, "fixed Z10 test")
    save_json(out/"calibration-predictions.json.gz", batch_predictions, compressed=True)
    save_json(out/"test-predictions.json.gz", test, compressed=True)
    names = ("calibration-predictions.json.gz", "test-predictions.json.gz")
    locks = {n: sha((out/n).read_bytes()) for n in names}
    save_json(out/"prediction-lock.json", locks)
    replay = check_replay(test, old)
    cuts = calibration(list(zip(batch_predictions, [r[1] for r in generated])), cfg, spec["target"], out)
    save_json(out/"cutoffs.json", cuts)
    cutoff_lock = sha((out/"cutoffs.json").read_bytes())
    assert all(sha((out/n).read_bytes()) == d for n, d in locks.items())
    rows, batches = test_scores(test, truth, cuts, cfg, nominal_cut, out)
    assert sha((out/"cutoffs.json").read_bytes()) == cutoff_lock
    result = dict(plan=plan, test_shots=len(inputs), replay_rows_checked=replay, prediction_sha256=locks,
                  cutoffs_sha256=cutoff_lock, z10_nominal_cutoff=nominal_cut,
                  stable_spin_prior=paired_prior(rows), calibration_batches=batches)
    save_json(out/"summary.json", result)
    print(json.dumps(result["stable_spin_prior"], indent=2), flush=True)


if __name__ == "__main__":
    main()
