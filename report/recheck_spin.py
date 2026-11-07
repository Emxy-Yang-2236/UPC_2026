"""Rescore the frozen Z10 forecasts using only Python's standard library.

Run from any directory with `python recheck_spin.py --run /path/to/Z10` or
pass the report's z10-replay.zip. The default is the archive beside this script
in evidence/. No forecast engine or random trajectory generator is imported.
thresholds.json, scores.csv and summary.json supply cross-checks for results
reconstructed from observations, truth and the two locked forecast files.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import statistics
from bisect import bisect_right
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile


FAMILIES = ("no_spin", "stable_spin", "wake")
PRIORS = ("narrow", "wide", "spin_rich")
PROFILES = ("rounded", "tracking")
ORIGIN = (0.0, 0.0, 0.11)
H = 0.05
G = 9.81
HALF_WIDTH, HEIGHT = 3.66, 2.44
NY, NZ = 30, 10
DY, DZ = 2 * HALF_WIDTH / NY, HEIGHT / NZ
CELL_AREA = DY * DZ
DIAGONAL = math.hypot(2 * HALF_WIDTH, HEIGHT)
CENTRES = [
    ((iy + 0.5) * DY - HALF_WIDTH, (iz + 0.5) * DZ)
    for iy in range(NY) for iz in range(NZ)
]


def require(test, message):
    if not test:
        raise ValueError(message)


@contextmanager
def run_reader(path):
    if path.is_dir():
        yield lambda name: (path / name).read_bytes()
    else:
        with ZipFile(path) as archive:
            yield archive.read


def verify_locks(read):
    required = {
        "predictions-lock.json": {"cal-predictions.json.gz", "blind-predictions.json.gz"},
        "thresholds-lock.json": {"thresholds.json"},
        "inputs-lock.json": {f"{split}-{kind}.json" for split in ("cal", "blind")
                             for kind in ("inputs", "truth")},
    }
    manifests = {name: json.loads(read(name)) for name in required}
    for manifest, names in required.items():
        hashes = manifests[manifest]
        require(names <= hashes.keys(), f"Missing lock entries in {manifest}")
        for name in names:
            digest = hashlib.sha256(read(name)).hexdigest()
            require(digest == hashes[name], f"SHA-256 mismatch for {name}")


def by_id(rows):
    result = {row["id"]: row for row in rows}
    require(len(result) == len(rows), "Duplicate kick ID")
    return result


def goal_cell(yz):
    y, z = yz
    require(abs(y) < HALF_WIDTH and 0 < z < HEIGHT, f"Direct entry outside opening: {yz}")
    iy = min(NY - 1, math.floor((y + HALF_WIDTH) / DY))
    iz = min(NZ - 1, math.floor(z / DZ))
    return iy * NZ + iz


def check_gravity(prediction, readings):
    # Fixed release, gravity and a least-squares launch speed fitted to both frames.
    v = [
        math.fsum(t * (frame[i] - ORIGIN[i] - 0.5 * a * t * t)
                  for t, frame in zip((H, 2 * H), readings)) / (5 * H * H)
        for i, a in enumerate((0, 0, -G))
    ]
    gate = 11 / v[0] if v[0] > 0 else math.inf
    ground = 2 * v[2] / G  # release height equals radius
    expected = None
    if gate < ground and gate <= 1.25:
        expected = (v[1] * gate, ORIGIN[2] + v[2] * gate - 0.5 * G * gate**2)
    point = prediction["point"]
    same = (point is None) if expected is None else (
        point is not None and math.dist(point, expected) < 1e-10)
    inside = expected is not None and abs(expected[0]) < HALF_WIDTH and 0 < expected[1] < HEIGHT
    require(same and prediction["p"] == float(inside), f"Gravity mismatch: {prediction['id']}")


def cell_scores(prediction):
    """Return a score per physical cell. An unavailable forecast has no cells."""
    point = prediction["point"]
    if prediction["method"] == "gravity":
        if point is None:
            return []
        distances = (math.dist(point, centre) for centre in CENTRES)
        return [d / (DIAGONAL + d) for d in distances]

    masses = prediction["hist"]
    if not masses or not any(masses):
        require(point is None, f"Empty histogram with a point: {prediction['id']}")
        return []
    require(len(masses) == NY * NZ and all(m >= 0 for m in masses) and
            abs(math.fsum(masses) - 1) < 1e-9, f"Invalid histogram: {prediction['id']}")
    order = sorted(range(len(masses)), key=lambda i: (-masses[i], i))
    require(point is not None and math.dist(point, CENTRES[order[0]]) < 1e-10,
            f"Point differs from modal cell: {prediction['id']}")
    result = [1.0] * len(masses)
    prefix = 0.0
    for i in order:
        if masses[i] == 0:
            break
        result[i] = min(prefix, 1.0)
        prefix += masses[i]
    return result


def acceleration(frames, i):
    return (frames[1][i] - 2 * frames[0][i] + ORIGIN[i]) / H**2


def axis_noise(sigma, shared, quantum):
    # The two independent errors have coefficients -2 and +1. A shared bias
    # has coefficient -1 because release is known exactly. Independent uniform
    # rounding errors give the approximation quantum**2/12 per reading.
    variance = (5 * sigma**2 + shared**2 + 5 * quantum**2 / 12) / H**4
    return math.sqrt(variance)


@dataclass
class Forecast:
    shot: str
    family: str
    goal: bool
    stratum: str
    profile: str
    method: str
    probability: float | None
    error: float | None
    true_score: float
    ordered_scores: list


def load_split(read, split, plan, noise_sd):
    inputs = by_id(json.loads(read(f"{split}-inputs.json")))
    truth = by_id(json.loads(read(f"{split}-truth.json")))
    predictions = json.loads(gzip.decompress(read(f"{split}-predictions.json.gz")))
    ids = sorted(inputs)
    require(inputs.keys() == truth.keys() and len(ids) == plan[split], f"{split}: input/truth IDs")
    for i in range(0, len(ids), 3):
        require({truth[s]["family"] for s in ids[i:i + 3]} == set(FAMILIES),
                f"{split}: family block at {ids[i]}")
    combinations = {(p, m) for p in PROFILES for m in ("nominal", "gravity")}
    combinations.update(("tracking", m) for m in PRIORS)
    expected = {(s, p, m) for s in ids for p, m in combinations}
    if split == "blind":
        expected.update((s, "tracking", "repeat") for s in ids[:plan["repeat_blind_first"]])
    keys = {(p["id"], p["profile"], p["method"]) for p in predictions}
    require(len(keys) == len(predictions) and keys == expected, f"{split}: prediction IDs/methods")
    rows = []
    for p in predictions:
        shot, profile, method = p["id"], p["profile"], p["method"]
        require(p["p"] is None or -1e-12 <= p["p"] <= 1 + 1e-12, f"Invalid probability: {shot}")
        observation = inputs[shot]
        actual = truth[shot]
        if method == "gravity":
            check_gravity(p, observation[profile])
        tracking = observation["tracking"]
        signal = math.hypot(acceleration(tracking, 1), acceleration(tracking, 2) + G) / noise_sd
        stratum = "low" if signal < plan["observable_cut"] else "high"
        goal = actual["event"] == "in"
        scores = cell_scores(p) if goal else []
        score = scores[goal_cell(actual["yz"])] if scores else 1.0
        error = math.dist(actual["yz"], p["point"]) if goal and p["point"] is not None else None
        rows.append(Forecast(shot, actual["family"], goal, stratum, profile, method,
                             p["p"], error, score, sorted(scores)))
    return inputs, truth, rows


def fit_thresholds(rows):
    samples = defaultdict(list)
    for f in rows:
        if f.goal:
            samples[f"{f.profile}/{f.method}"].append(f)
            if (f.profile, f.method) == ("tracking", "nominal"):
                samples[f"family/{f.family}"].append(f)
                samples[f"observable/{f.stratum}"].append(f)
    for key in [*(f"family/{g}" for g in FAMILIES), "observable/low", "observable/high"]:
        samples.setdefault(key, [])
    cuts = {}
    for key, group in sorted(samples.items()):
        n = len(group)
        rank = (9 * (n + 1) + 9) // 10  # ceil(9(n+1)/10) in integer arithmetic
        q = sorted(f.true_score for f in group)[rank - 1] if rank <= n else 1.0
        cuts[key] = {"n": n, "rank": rank, "q": q,
                     "missing_distribution_n": sum(not f.ordered_scores for f in group),
                     "hits": sum(bool(f.ordered_scores) and f.true_score <= q for f in group)}
    return cuts


def compare_thresholds(archived, cuts, plan, noise):
    reference = {f"{p}/{m}": row for p, methods in archived["pooled"].items()
                 for m, row in methods.items()}
    for category in ("family", "observable"):
        reference.update({f"{category}/{name}": row for name, row in archived[category].items()})
    require(reference.keys() == cuts.keys(), "Calibration groups differ")
    for key, rebuilt in cuts.items():
        row = reference[key]
        same_counts = all(row[k] == rebuilt[k] for k in ("n", "rank", "hits", "missing_distribution_n"))
        require(same_counts and abs(row["threshold"] - rebuilt["q"]) < 1e-12
                and row["rank_exceeds_n"] == (rebuilt["rank"] > rebuilt["n"]),
                f"Threshold mismatch: {key}")
    highest = max(cuts[f"family/{f}"]["q"] for f in FAMILIES)
    require(abs(archived["worst_family"]["threshold"] - highest) < 1e-12
            and abs(archived["tracking_axis_sd_m_s2"] - noise) < 1e-11
            and abs(archived["goal_area_m2"] - NY * NZ * CELL_AREA) < 1e-11
            and archived["observable_cut"] == plan["observable_cut"] and archived["target"] == plan["target"],
            "Group maximum, noise scale, goal area or target mismatch")


def operating_points(f, cuts):
    key = f"{f.profile}/{f.method}"
    base = "tracking/nominal"
    if f.method == "repeat":
        yield "fixed_nominal", cuts[base]["q"]
        return
    yield "pooled", cuts[key]["q"]
    if f.method in PRIORS:
        yield "fixed_nominal", cuts[base]["q"]
    if key == base:
        yield "family", cuts[f"family/{f.family}"]["q"]
        yield "worst_family", max(cuts[f"family/{g}"]["q"] for g in FAMILIES)
        yield "observable", cuts[f"observable/{f.stratum}"]["q"]


def average(values):
    return statistics.fmean(values) if values else None


def tally(rows, cuts, scored_csv):
    fields = ("id", "profile", "method", "calibration")
    archive = {}
    for row in csv.DictReader(io.StringIO(scored_csv.decode("utf-8"))):
        key = tuple(row[k] for k in fields)
        require(key not in archive, f"Duplicate score row: {key}")
        archive[key] = row
    n_rows = len(archive)
    groups = defaultdict(list)
    for f in rows:
        for rule, q in operating_points(f, cuts):
            hit = bool(f.ordered_scores) and f.true_score <= q
            cells = bisect_right(f.ordered_scores, q)
            key = (f.shot, f.profile, f.method, rule)
            ref = archive.pop(key)
            require(abs(q - float(ref["threshold"])) < 1e-12 and f.family == ref["family"]
                    and int(ref["goal"]) == f.goal, f"Blind threshold or labels: {key}")
            if f.goal:
                require(hit == int(ref["hit"]) and cells == int(ref["cells"])
                        and abs(cells * CELL_AREA - float(ref["area_m2"])) < 1e-11
                        and abs(f.true_score - float(ref["true_cell_score"])) < 1e-12,
                        f"Blind cell membership or area: {key}")
            else:
                require(all(ref[k] == "" for k in ("hit", "area_m2", "cells", "true_cell_score")),
                        f"Location scored on a non-entry: {key}")
            for group in ("all", f.family):
                groups[f"{f.profile}/{f.method}/{rule}/{group}"].append((f, hit, cells))
    require(not archive, "Extra rows in frozen score table")
    result = {}
    for key, group in sorted(groups.items()):
        goals = [(f, hit, cells) for f, hit, cells in group if f.goal]
        brier = [(f.probability - int(f.goal))**2 for f, _, _ in group if f.probability is not None]
        errors = [f.error for f, _, _ in goals if f.error is not None]
        result[key] = {
            "attempts": len(group), "goals": len(goals), "hits": sum(hit for _, hit, _ in goals),
            "area_m2": average([cells * CELL_AREA for _, _, cells in goals]),
            "without_region": sum(not f.ordered_scores for f, _, _ in goals),
            "full_goal_regions": sum(cells == NY * NZ for _, _, cells in goals),
            "point_n": len(errors), "mean_error_m": average(errors),
            "event_n": len(brier), "brier": average(brier),
        }
    return result, n_rows


def curvature(inputs, truth):
    # Compute errors directly from coordinate residuals relative to unrounded truth.
    by_group = defaultdict(list)
    for s, observation in inputs.items():
        actual = truth[s]
        exact = actual["exact_xyz"]
        for profile in PROFILES:
            measured = observation[profile]
            delta = [(measured[1][i] - exact[1][i] - 2 * (measured[0][i] - exact[0][i])) / H**2
                     for i in (1, 2)]
            for group in ("all", actual["family"]):
                by_group[f"{profile}/{group}"].append(delta)
    result = {}
    for key, values in sorted(by_group.items()):
        y2 = statistics.fmean(dy**2 for dy, dz in values)
        z2 = statistics.fmean(dz**2 for dy, dz in values)
        result[key] = {"n": len(values), "rmse_y": math.sqrt(y2), "rmse_z": math.sqrt(z2),
                       "rmse_per_axis": math.sqrt((y2 + z2) / 2),
                       "mean_l2": statistics.fmean(math.hypot(*v) for v in values)}
    return result


def compare_summary(summary, groups, noise_groups):
    fields = {"attempts": "shots", "goals": "goals", "hits": "hits", "area_m2": "mean_area_m2",
              "without_region": "missing_goal_distribution", "full_goal_regions": "full_goal_regions",
              "point_n": "point_n", "mean_error_m": "mean_point_error_m", "event_n": "brier_n",
              "brier": "mean_brier"}
    archived = {"/".join(row[k] for k in ("profile", "method", "calibration", "family")): row
                for row in summary["groups"]}
    require(len(archived) == len(summary["groups"]) and archived.keys() == groups.keys(),
            "Missing or duplicate forecast summary group")
    for key, row in archived.items():
        for new, old in fields.items():
            a, b = groups[key][new], row[old]
            same = a == b or (a is not None and b is not None and abs(a - b) < 1e-10)
            require(same, f"Summary mismatch: {key}/{old}")
    reference = {f"{r['profile']}/{r['family']}": r for r in summary["curvature"]["groups"]
                 if r["sample"] == "all_events"}
    require(reference.keys() == noise_groups.keys(), "Missing or extra curvature summary groups")
    for key, values in noise_groups.items():
        row = reference[key]
        for a, b in (("n", "n"), ("rmse_y", "rmse_y_m_s2"), ("rmse_z", "rmse_z_m_s2"),
                     ("rmse_per_axis", "pooled_axis_rmse_m_s2"), ("mean_l2", "mean_error_norm_m_s2")):
            require(abs(values[a] - row[b]) < 1e-10, f"Curvature summary mismatch: {key}/{b}")


def recheck(read):
    verify_locks(read)
    cfg = json.loads(read("config.json"))
    plan = cfg["plan"]
    require(plan["study"] == "Z10" and plan["target"] == 0.9, "Expected Z10 and 90% target")
    settings = cfg["settings"]
    official = settings["official"]
    require(tuple(official["r0"]) == ORIGIN and official["times"] == [H, 2 * H] and
            (official["half_width"], official["height"], official["gate"]) == (HALF_WIDTH, HEIGHT, 11)
            and settings["study"]["grid"] == [NY, NZ] and settings["physics"]["g"] == G
            and settings["physics"]["radius"] == ORIGIN[2] and settings["solver"]["horizon"] == 1.25,
            "Unexpected Z10 geometry, gravity or observation times")
    quantum = settings["observation"]["quantum_m"]
    noise = axis_noise(plan["independent_sigma_m"], plan["shared_sigma_m"], quantum)
    _, cal_truth, calibration = load_split(read, "cal", plan, noise)
    cuts = fit_thresholds(calibration)
    compare_thresholds(json.loads(read("thresholds.json")), cuts, plan, noise)
    blind_inputs, blind_truth, blind = load_split(read, "blind", plan, noise)
    require(cal_truth.keys().isdisjoint(blind_truth.keys()), "Split IDs overlap")
    fingerprints = [tuple(tuple(frame) for frame in r["exact_xyz"])
                    for split in (cal_truth, blind_truth) for r in split.values()]
    require(len(set(fingerprints)) == len(fingerprints), "Repeated exact input trajectory")
    groups, n_scores = tally(blind, cuts, read("scores.csv"))
    noise_groups = curvature(blind_inputs, blind_truth)
    compare_summary(json.loads(read("summary.json")), groups, noise_groups)
    return {
        "sha256_locks_match": True,
        "calibration_groups_checked": len(cuts),
        "blind_score_rows_checked": n_scores,
        "blind_summary_groups_checked": len(groups),
        "thresholds": cuts,
        "direct_entries": {split: dict(Counter(v["family"] for v in truth.values() if v["event"] == "in"))
                           for split, truth in (("cal", cal_truth), ("blind", blind_truth))},
        "blind": groups,
        "curvature_m_s2": {"tracking_theoretical_sd": noise,
                           "rounded_theoretical_sd": axis_noise(0, 0, quantum),
                           "stratification_boundary": plan["observable_cut"] * noise,
                           "blind": noise_groups},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path,
                        default=Path(__file__).resolve().parent / "evidence" / "z10-replay.zip")
    args = parser.parse_args()
    with run_reader(args.run) as read:
        result = recheck(read)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
