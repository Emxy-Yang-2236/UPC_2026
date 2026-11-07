"""Z10 split calibration and kick-level scoring. Only score_run opens holdout truth."""
import csv
import gzip
import hashlib
import json
import math
import os
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np

from evaluate import truth_cell, wilson
from flight import EVENTS, cell_edges, cell_geometry
from predict import prefix_masses, ranking
from reference import baselines


FAMILIES = ("no_spin", "stable_spin", "wake")
SIGNAL_BINS = ("low", "high")
PRIORS = ("narrow", "wide", "spin_rich")
METHODS = {"tracking": ("nominal", "gravity", *PRIORS), "rounded": ("nominal", "gravity")}


@contextmanager
def new_output(path):
    """Publish a complete file, allowing an identical replay after an interrupted score."""
    with NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent,
                            prefix=path.name + ".", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            yield stream
            stream.close()
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != temporary.read_bytes():
                    raise ValueError(f"Existing output differs: {path}")
        finally:
            stream.close()
            temporary.unlink(missing_ok=True)


def write_json(path, obj):
    with new_output(path) as stream:
        json.dump(obj, stream, indent=2, allow_nan=False)
        stream.write("\n")


def write_csv(path, rows, fields=None):
    with new_output(path) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def locked_bytes(out, name, seal):
    data = (out / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != seal[name]:
        raise ValueError(f"Checksum mismatch: {name}")
    return data


def index_shots(records):
    result = {row["id"]: row for row in records}
    if len(result) != len(records):
        raise ValueError("Duplicate kick ID")
    return result


def read_split(out, split, spec, prediction_bytes):
    inputs = index_shots(json.loads((out / f"{split}-inputs.json").read_bytes()))
    truth = index_shots(json.loads((out / f"{split}-truth.json").read_bytes()))
    if inputs.keys() != truth.keys() or len(inputs) != spec[split]:
        raise ValueError(f"{split}: observed and reference kick IDs or planned count disagree")
    predictions = json.loads(gzip.decompress(prediction_bytes))
    keys = [(p["id"], p["profile"], p["method"]) for p in predictions]
    expected = {(sid, profile, method) for sid in inputs for profile in METHODS
                for method in METHODS[profile]}
    if split == "blind":
        expected.update((sid, "tracking", "repeat") for sid in list(inputs)[:spec["repeat_blind_first"]])
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValueError(f"{split}: missing, duplicate or unexpected method/reading/ID combination")
    for shot in truth.values():
        if shot["family"] not in FAMILIES or shot["event"] not in EVENTS:
            raise ValueError(f"Unexpected reference family/event for {shot['id']}")
    return inputs, truth, predictions


def frame_interval(cfg):
    h, t2 = cfg["official"]["times"]
    if h <= 0 or not math.isclose(2*h, t2, rel_tol=1e-12):
        raise ValueError("The curvature diagnostic requires two equally spaced frames after release")
    return h


def acceleration(frames, origin, h):
    frames = np.asarray(frames, dtype=float)
    if frames.shape != (2, 3) or not np.isfinite(frames).all():
        raise ValueError("Expected two finite three-dimensional positions")
    return (frames[1] - 2*frames[0] + origin) / h**2


def axis_sd(profile, cfg, spec):
    variance = 5 * cfg["observation"]["quantum_m"]**2 / 12
    if profile == "tracking":
        variance += 5 * spec["independent_sigma_m"]**2 + spec["shared_sigma_m"]**2
    return math.sqrt(variance) / frame_interval(cfg)**2


def observable_signal(frames, cfg, spec):
    a = acceleration(frames, cfg["official"]["r0"], frame_interval(cfg))
    return float(np.hypot(a[1], a[2] + cfg["physics"]["g"]) / axis_sd("tracking", cfg, spec))


def signal_bin(value, spec):
    return "low" if value < spec["observable_cut"] else "high"


def grid(cfg):
    edges = cell_edges(cfg)
    centres, areas = cell_geometry(edges)
    diagonal = float(np.hypot(np.ptp(edges[0]), np.ptp(edges[1])))
    return edges, centres, areas, diagonal


def reference_cell(actual, edges):
    if actual["event"] != "in":
        return None
    y, z = actual["yz"]
    if not (edges[0][0] < y < edges[0][-1] and edges[1][0] < z < edges[1][-1]):
        raise ValueError(f"Direct goal outside the open goal aperture: {actual['id']}")
    return truth_cell((y, z), edges)


def cell_distribution(prediction, centres, diagonal):
    """Return (score, stable ordering, conditional mass) or None for an empty region."""
    point = prediction["point"]
    if point is not None and (np.shape(point) != (2,) or not np.isfinite(point).all()):
        raise ValueError(f"Invalid predicted crossing for {prediction['id']}")
    if prediction["method"] == "gravity":
        if point is None:
            return None
        distance = np.linalg.norm(centres - point, axis=1)
        return distance / (diagonal + distance), np.argsort(distance, kind="stable"), None
    if prediction["hist"] is None:
        return None
    hist = np.asarray(prediction["hist"], dtype=float)
    if hist.shape != (len(centres),) or not np.isfinite(hist).all() or np.any(hist < 0):
        raise ValueError(f"Invalid goal histogram for {prediction['id']}")
    mass = hist.sum()
    if mass == 0:
        return None
    if not np.isclose(mass, 1., atol=1e-10, rtol=1e-10):
        raise ValueError(f"Goal histogram is not normalized: {prediction['id']}")
    order = ranking(hist)
    occupied = hist[order] > 0
    scores = np.ones(len(centres))
    scores[order[occupied]] = np.minimum(prefix_masses(hist, order)[occupied], 1.)
    return scores, order, hist


def quantile_entry(scores, target):
    # Keep every calibration goal in the rank. Missing regions can never hit, even at 1.
    ranked = sorted(1. if value is None else value for value in scores)
    n = len(ranked)
    rank = math.ceil(target*(n+1))
    threshold = ranked[rank-1] if rank <= n else 1.
    return {"n": n, "rank": rank, "threshold": threshold, "rank_exceeds_n": rank > n,
            "missing_distribution_n": sum(value is None for value in scores),
            "hits": sum(value is not None and value <= threshold for value in scores)}


def fit_thresholds(out: Path, cfg: dict, spec: dict):
    """Fit the preregistered cuts using exactly the three calibration files."""
    out = Path(out)
    predictions_bytes = (out / "cal-predictions.json.gz").read_bytes()
    inputs, truth, predictions = read_split(out, "cal", spec, predictions_bytes)
    edges, centres, areas, diagonal = grid(cfg)
    target = spec["target"]
    if not 0 < target <= 1:
        raise ValueError("Expected a calibration target in (0, 1]")
    pools = defaultdict(list)
    families = defaultdict(list)
    observable = defaultdict(list)
    for p in predictions:
        actual = truth[p["id"]]
        cid = reference_cell(actual, edges)
        if cid is None:
            continue
        distribution = cell_distribution(p, centres, diagonal)
        score = None if distribution is None else float(distribution[0][cid])
        pools[p["profile"], p["method"]].append(score)
        if (p["profile"], p["method"]) == ("tracking", "nominal"):
            families[actual["family"]].append(score)
            signal = observable_signal(inputs[p["id"]]["tracking"], cfg, spec)
            observable[signal_bin(signal, spec)].append(score)
    by_family = {f: quantile_entry(families[f], target) for f in FAMILIES}
    worst = max(entry["threshold"] for entry in by_family.values())
    thresholds = {
        "target": target, "goal_area_m2": float(areas.sum()),
        "observable_cut": spec["observable_cut"], "tracking_axis_sd_m_s2": axis_sd("tracking", cfg, spec),
        "pooled": {profile: {m: quantile_entry(pools[profile, m], target) for m in methods}
                   for profile, methods in METHODS.items()},
        "family": by_family,
        "worst_family": {"threshold": worst, "families_at_max": [f for f in FAMILIES
                         if by_family[f]["threshold"] == worst]},
        "observable": {s: quantile_entry(observable[s], target) for s in SIGNAL_BINS},
    }
    write_json(out / "thresholds.json", thresholds)
    return thresholds


def calibration_choices(profile, method, family, stratum, thresholds):
    if method != "repeat":
        yield "pooled", "all", thresholds["pooled"][profile][method]["threshold"]
    if profile == "tracking" and method == "nominal":
        yield "family", family, thresholds["family"][family]["threshold"]
        yield "worst_family", "all", thresholds["worst_family"]["threshold"]
        yield "observable", stratum, thresholds["observable"][stratum]["threshold"]
    if profile == "tracking" and method in (*PRIORS, "repeat"):
        yield "fixed_nominal", "all", thresholds["pooled"]["tracking"]["nominal"]["threshold"]


def score_rows(inputs, truth, predictions, thresholds, cfg, spec):
    edges, centres, areas, diagonal = grid(cfg)
    signals = {sid: observable_signal(inp["tracking"], cfg, spec) for sid, inp in inputs.items()}
    rows = []
    for p in predictions:
        sid, profile, method = p["id"], p["profile"], p["method"]
        actual = truth[sid]
        family = actual["family"]
        cid = reference_cell(actual, edges)
        goal = cid is not None
        point, prob, ess = p["point"], p["p"], p["ess"]
        if prob is not None and not 0 <= prob <= 1:
            raise ValueError(f"Invalid event probability for {sid}")
        if ess is not None and (not math.isfinite(ess) or ess < 0):
            raise ValueError(f"Invalid ESS for {sid}")
        distribution = cell_distribution(p, centres, diagonal)
        scored = goal and distribution is not None
        score = float(distribution[0][cid]) if scored else None
        rank = int(np.flatnonzero(distribution[1] == cid)[0]) + 1 if scored else None
        cell_p = float(distribution[2][cid]) if scored and method != "gravity" else None
        signal = signals[sid] if profile == "tracking" else None
        stratum = signal_bin(signal, spec) if signal is not None else None
        q = actual["yz"]
        base = {
            "id": sid, "family": family, "event": actual["event"], "goal": int(goal),
            "profile": profile, "method": method, "signal": signal, "signal_stratum": stratum,
            "truth_y_m": None if q is None else q[0], "truth_z_m": None if q is None else q[1],
            "truth_cell": cid, "point_available": int(point is not None),
            "distribution_available": int(distribution is not None), "event_available": int(prob is not None),
            "point_y_m": None if point is None else point[0], "point_z_m": None if point is None else point[1],
            "p": prob, "ess": ess, "low_ess": None if ess is None else int(ess < cfg["study"]["min_ess"]),
            "brier": None if prob is None else (prob - int(goal))**2,
            "point_error_m": float(np.linalg.norm(np.subtract(point, q))) if goal and point is not None else None,
            "true_cell_score": score, "true_cell_rank": rank, "true_cell_mass": cell_p,
        }
        for name, source, threshold in calibration_choices(profile, method, family, stratum, thresholds):
            hit = cells = area = None
            if goal:
                hit = int(scored and score <= threshold)
                if scored:
                    selected = distribution[0] <= threshold
                    cells, area = int(np.count_nonzero(selected)), float(areas[selected].sum())
                else:
                    cells, area = 0, 0.
            rows.append(dict(base, calibration=name, threshold_stratum=source, threshold=threshold,
                             hit=hit, cells=cells, area_m2=area))
    return rows


def numbers(rows, key):
    return [r[key] for r in rows if r[key] is not None]


def mean(values):
    return float(np.mean(values)) if len(values) else None


def median(values):
    return float(np.median(values)) if len(values) else None


def group_summary(rows, cell_count):
    goals = [r for r in rows if r["goal"]]
    hits, errors, scores = numbers(goals, "hit"), numbers(goals, "point_error_m"), numbers(goals, "true_cell_score")
    brier, ess, areas = numbers(rows, "brier"), numbers(rows, "ess"), numbers(goals, "area_m2")
    if len(hits) != len(goals) or len(areas) != len(goals):
        raise ValueError("Every direct goal must contribute a region hit and an area")
    return {
        "shots": len(rows), "goals": len(goals), "region_n": len(hits), "hits": sum(hits),
        "coverage": mean(hits), "wilson95": wilson(sum(hits), len(hits)),
        "area_n": len(areas), "mean_area_m2": mean(areas), "median_area_m2": median(areas),
        "threshold_one_goals": sum(r["threshold"] == 1. for r in goals),
        "full_goal_regions": sum(r["cells"] == cell_count for r in goals),
        "point_n": len(errors), "mean_point_error_m": mean(errors), "median_point_error_m": median(errors),
        "missing_goal_point": len(goals) - len(errors), "missing_point": len(rows) - sum(r["point_available"] for r in rows),
        "score_n": len(scores), "mean_true_cell_score": mean(scores), "median_true_cell_score": median(scores),
        "mean_true_cell_rank": mean(numbers(goals, "true_cell_rank")),
        "score_one_goals": sum(s == 1. for s in scores),
        "truth_zero_mass_goals": sum(s == 0. for s in numbers(goals, "true_cell_mass")),
        "truth_mass_n": len(numbers(goals, "true_cell_mass")),
        "missing_goal_distribution": len(goals) - len(scores),
        "missing_distribution": len(rows) - sum(r["distribution_available"] for r in rows),
        "brier_n": len(brier), "mean_brier": mean(brier), "missing_event": len(rows) - len(brier),
        "ess_n": len(ess), "low_ess": sum(numbers(rows, "low_ess")),
    }


def bootstrap_indices(n, spec):
    # Every comparison on the same kick population gets the same whole-kick draws.
    if not n:
        return np.empty((spec["bootstrap_draws"], 0), dtype=int)
    rng = np.random.default_rng(spec["bootstrap_seed"])
    return rng.integers(n, size=(spec["bootstrap_draws"], n))


def paired_difference(left, right, ids, key, draw, scale=1.):
    # A shot with a missing point stays in the resampling population; that metric
    # uses the complete pairs inside each resample and publishes its own denominator.
    delta = np.full(len(ids), np.nan)
    for i, sid in enumerate(ids):
        a, b = left[sid][key], right[sid][key]
        if a is not None and b is not None:
            delta[i] = scale * (a - b)
    paired = delta[np.isfinite(delta)]
    ci, valid_draws = None, 0
    if len(paired):
        boot = delta[draw]
        n = np.isfinite(boot).sum(axis=1)
        valid = n > 0
        valid_draws = int(np.count_nonzero(valid))
        values = np.nansum(boot[valid], axis=1) / n[valid]
        ci = np.quantile(values, [.025, .975]).tolist()
    return {"n": len(paired), "difference": mean(paired), "ci95": ci, "valid_draws": valid_draws,
            "a_lower": int(np.count_nonzero(paired < 0)), "a_higher": int(np.count_nonzero(paired > 0)),
            "equal": int(np.count_nonzero(paired == 0))}


def hit_changes(left, right, ids):
    both = sum(left[i]["hit"] == right[i]["hit"] == 1 for i in ids)
    neither = sum(left[i]["hit"] == right[i]["hit"] == 0 for i in ids)
    a_only = sum(left[i]["hit"] == 1 and right[i]["hit"] == 0 for i in ids)
    b_only = sum(left[i]["hit"] == 0 and right[i]["hit"] == 1 for i in ids)
    if both + neither + a_only + b_only != len(ids):
        raise ValueError("Missing coverage outcome on a direct goal")
    return {"both_hit": both, "neither_hit": neither, "a_only_hit": a_only, "b_only_hit": b_only}


def stable_comparisons(scenarios, stable_ids, spec):
    base = ("tracking", "nominal", "pooled")
    controls = [("tracking_aero_minus_gravity", base, ("tracking", "gravity", "pooled")),
                ("rounded_aero_minus_gravity", ("rounded", "nominal", "pooled"), ("rounded", "gravity", "pooled"))]
    for m in PRIORS:
        own, fixed = ("tracking", m, "pooled"), ("tracking", m, "fixed_nominal")
        controls.extend([(f"{m}_minus_nominal_pooled", own, base),
                         (f"{m}_minus_nominal_fixed", fixed, base),
                         (f"{m}_pooled_minus_fixed", own, fixed)])
    for m in ("nominal", "gravity"):
        controls.append((f"rounded_minus_tracking_{m}", ("rounded", m, "pooled"), ("tracking", m, "pooled")))
    for cut in ("family", "worst_family", "observable"):
        controls.append((f"{cut}_minus_pooled", ("tracking", "nominal", cut), base))
    draw = bootstrap_indices(len(stable_ids), spec)
    comparisons = []
    for name, a, b in controls:
        left, right = scenarios[a], scenarios[b]
        metrics = {output: paired_difference(left, right, stable_ids, field, draw, scale)
                   for output, field, scale in [("hit_pp", "hit", 100.), ("area_m2", "area_m2", 1.),
                                                ("point_error_m", "point_error_m", 1.),
                                                ("true_cell_rank", "true_cell_rank", 1.)]}
        # The bounded ballistic distance and the aero probability prefix have different meanings.
        if (a[1] == "gravity") == (b[1] == "gravity"):
            metrics["true_cell_score"] = paired_difference(left, right, stable_ids, "true_cell_score", draw)
        keys = ("profile", "method", "calibration")
        comparisons.append({"name": name, "a": dict(zip(keys, a)), "b": dict(zip(keys, b)),
                            "family": "stable_spin", "goals": len(stable_ids),
                            **hit_changes(left, right, stable_ids), **metrics})
    return comparisons


def constant_control(last, a, cfg, h):
    """Keep the measured endpoint and exact release. Solve the existing first-event control."""
    origin = np.asarray(cfg["official"]["r0"])
    v0 = (last - origin)/(2*h) - h*a
    if origin[2] == cfg["physics"]["radius"] and (v0[2] < 0 or (v0[2] == 0 and a[2] <= 0)):
        return {"event": "ground", "point": None, "T": 0.}
    # r1 = (r2 + r0 - h² a)/2 is the unique synthesized first frame for this intervention.
    first = (last + origin - h**2*a)/2
    return baselines([first, last], cfg)["constant_a"]


def curvature_rows(inputs, truth, cfg, spec):
    h = frame_interval(cfg)
    origin = np.asarray(cfg["official"]["r0"])
    sd = {profile: axis_sd(profile, cfg, spec) for profile in METHODS}
    rows = []
    for sid, shot in inputs.items():
        actual = truth[sid]
        exact = acceleration(actual["exact_xyz"], origin, h)
        goal = actual["event"] == "in"
        for profile in METHODS:
            frames = np.asarray(shot[profile])
            observed = acceleration(frames, origin, h)
            error = observed - exact
            signal = observable_signal(frames, cfg, spec) if profile == "tracking" else None
            row = {"id": sid, "family": actual["family"], "event": actual["event"], "goal": int(goal),
                   "profile": profile, "axis_reference_sd_m_s2": sd[profile], "signal": signal,
                   "signal_stratum": signal_bin(signal, spec) if signal is not None else None}
            for axis, component in enumerate("xyz"):
                row[f"observed_a{component}_m_s2"] = float(observed[axis])
                row[f"exact_a{component}_m_s2"] = float(exact[axis])
            row.update(error_y_m_s2=float(error[1]), error_z_m_s2=float(error[2]),
                       error_norm_m_s2=float(np.hypot(error[1], error[2])))
            for label, a in (("ca_measured", observed), ("ca_exact", exact)):
                result = constant_control(frames[-1], a, cfg, h) if profile == "tracking" else None
                point = None if result is None else result["point"]
                row.update({f"{label}_event": None if result is None else result["event"],
                            f"{label}_t_s": None if result is None else result["T"],
                            f"{label}_y_m": None if point is None else point[0],
                            f"{label}_z_m": None if point is None else point[1],
                            f"{label}_point_error_m": float(np.linalg.norm(np.subtract(point, actual["yz"])))
                            if point is not None and goal else None})
            rows.append(row)
    return rows


def curvature_summary(rows, stable_ids, cfg, spec):
    groups, controls = [], []
    lookup = {}
    for profile in METHODS:
        by_id = index_shots([r for r in rows if r["profile"] == profile])
        lookup[profile] = by_id
        for family in ("all", *FAMILIES):
            family_rows = [r for r in by_id.values() if family == "all" or r["family"] == family]
            goals = [r for r in family_rows if r["goal"]]
            for sample, sub in (("all_events", family_rows), ("direct_goals", goals)):
                component = {}
                for axis in ("y", "z", "norm"):
                    errors = np.asarray(numbers(sub, f"error_{axis}_m_s2"))
                    component[f"rmse_{axis}_m_s2"] = float(np.sqrt(np.mean(errors**2))) if len(errors) else None
                component["pooled_axis_rmse_m_s2"] = (component["rmse_norm_m_s2"]/math.sqrt(2) if sub else None)
                groups.append({"family": family, "profile": profile, "sample": sample, "n": len(sub),
                               "goals": len(goals), "reference_axis_sd_m_s2": axis_sd(profile, cfg, spec),
                               "mean_error_norm_m_s2": mean(numbers(sub, "error_norm_m_s2")),
                               "median_error_norm_m_s2": median(numbers(sub, "error_norm_m_s2")), **component})
            if profile == "tracking":
                for label in ("ca_measured", "ca_exact"):
                    errors = numbers(goals, f"{label}_point_error_m")
                    controls.append({"family": family, "profile": profile, "method": label,
                                     "shots": len(family_rows), "goals": len(goals), "point_n": len(errors),
                                     "missing_goal_point": len(goals)-len(errors), "mean_point_error_m": mean(errors),
                                     "median_point_error_m": median(errors),
                                     "predicted_events": {e: sum(r[f"{label}_event"] == e for r in family_rows) for e in EVENTS},
                                     "predicted_events_on_goals": {e: sum(r[f"{label}_event"] == e for r in goals) for e in EVENTS}})
    draw = bootstrap_indices(len(stable_ids), spec)
    tracked = lookup["tracking"]
    measured = {sid: {"error": tracked[sid]["ca_measured_point_error_m"]} for sid in stable_ids}
    exact = {sid: {"error": tracked[sid]["ca_exact_point_error_m"]} for sid in stable_ids}
    return {"groups": groups, "controls": controls,
            "stable_spin_direct_pairs": {
                "goals": len(stable_ids),
                "rounded_minus_tracking_error_norm_m_s2": paired_difference(
                    lookup["rounded"], tracked, stable_ids, "error_norm_m_s2", draw),
                "ca_exact_minus_measured_point_error_m": paired_difference(exact, measured, stable_ids, "error", draw),
                "ca_exact_only_point": sum(exact[i]["error"] is not None and measured[i]["error"] is None for i in stable_ids),
                "ca_measured_only_point": sum(exact[i]["error"] is None and measured[i]["error"] is not None for i in stable_ids),
            }}


REPEAT_FIELDS = ("id", "family", "event", "goal", "threshold", "nominal_ess", "repeat_ess",
                 "nominal_low_ess", "repeat_low_ess", "nominal_point_y_m", "nominal_point_z_m",
                 "repeat_point_y_m", "repeat_point_z_m", "point_shift_m", "nominal_hit", "repeat_hit",
                 "nominal_area_m2", "repeat_area_m2")


def repeat_results(scenarios, expected_ids, spec):
    first = scenarios["tracking", "nominal", "pooled"]
    second = scenarios.get(("tracking", "repeat", "fixed_nominal"), {})
    if set(expected_ids) != second.keys():
        raise ValueError("Repeat seed must cover exactly the fixed prefix")
    rows = []
    for sid in expected_ids:
        a, b = first[sid], second[sid]
        if a["threshold"] != b["threshold"]:
            raise ValueError("Repeat seed did not use the first seed's threshold")
        distance = None
        if a["point_available"] and b["point_available"]:
            distance = float(np.hypot(a["point_y_m"] - b["point_y_m"], a["point_z_m"] - b["point_z_m"]))
        row = {k: a[k] for k in ("id", "family", "event", "goal", "threshold")}
        for label, r in (("nominal", a), ("repeat", b)):
            row.update({f"{label}_{k}": r[k] for k in ("ess", "low_ess", "point_y_m", "point_z_m", "hit", "area_m2")})
        rows.append(dict(row, point_shift_m=distance))
    stats = []
    for family in ("all", *FAMILIES):
        pool = [r for r in rows if family == "all" or r["family"] == family]
        goals = [r for r in pool if r["goal"]]
        ids = [r["id"] for r in goals]
        shifts = numbers(pool, "point_shift_m")
        goal_shifts = numbers(goals, "point_shift_m")
        stats.append({"family": family, "profile": "tracking", "method_a": "repeat", "method_b": "nominal",
                      "calibration": "first_seed_pooled", "shots": len(pool), "goals": len(goals),
                      "point_pair_n": len(shifts), "mean_point_shift_m": mean(shifts),
                      "median_point_shift_m": median(shifts), "max_point_shift_m": max(shifts, default=None),
                      "p95_point_shift_m": float(np.quantile(shifts, .95)) if shifts else None,
                      "same_point": sum(s == 0. for s in shifts), "goal_point_pair_n": len(goal_shifts),
                      "mean_goal_point_shift_m": mean(goal_shifts),
                      "nominal_ess_n": len(numbers(pool, "nominal_ess")), "repeat_ess_n": len(numbers(pool, "repeat_ess")),
                      "nominal_low_ess": sum(numbers(pool, "nominal_low_ess")), "repeat_low_ess": sum(numbers(pool, "repeat_low_ess")),
                      "nominal_hits": sum(numbers(goals, "nominal_hit")), "repeat_hits": sum(numbers(goals, "repeat_hit")),
                      **hit_changes(second, first, ids),
                      "hit_pp": paired_difference(second, first, ids, "hit", bootstrap_indices(len(ids), spec), 100.)})
    return rows, stats


def score_run(out: Path, cfg: dict, spec: dict):
    """Verify both forecast locks and the cutoff lock before reading any holdout truth."""
    out = Path(out)
    pred_seal = json.loads((out / "predictions-lock.json").read_bytes())
    cut_seal = json.loads((out / "thresholds-lock.json").read_bytes())
    thresholds = json.loads(locked_bytes(out, "thresholds.json", cut_seal))
    locked_bytes(out, "cal-predictions.json.gz", pred_seal)
    blind_bytes = locked_bytes(out, "blind-predictions.json.gz", pred_seal)
    inputs, truth, predictions = read_split(out, "blind", spec, blind_bytes)
    if thresholds["target"] != spec["target"]:
        raise ValueError("Threshold target differs from the frozen experiment")
    rows = score_rows(inputs, truth, predictions, thresholds, cfg, spec)
    scenarios = defaultdict(dict)
    for r in rows:
        scenarios[r["profile"], r["method"], r["calibration"]][r["id"]] = r
    cell_count = math.prod(cfg["study"]["grid"])
    stable_ids = sorted(i for i, r in truth.items() if r["family"] == "stable_spin" and r["event"] == "in")
    summary_groups, signal_groups = [], []
    for (profile, method, calibration), by_id in sorted(scenarios.items()):
        identity = {"profile": profile, "method": method, "calibration": calibration}
        for family in ("all", *FAMILIES):
            sub = [r for r in by_id.values() if family == "all" or r["family"] == family]
            summary_groups.append(dict(identity, family=family, **group_summary(sub, cell_count)))
        if profile == "tracking" and method == "nominal" and calibration in ("pooled", "observable"):
            for stratum in SIGNAL_BINS:
                sub = [r for r in by_id.values() if r["signal_stratum"] == stratum]
                signal_groups.append(dict(identity, signal_stratum=stratum, **group_summary(sub, cell_count)))
    curvature = curvature_rows(inputs, truth, cfg, spec)
    repeated, repeat_summary = repeat_results(scenarios, list(inputs)[:spec["repeat_blind_first"]], spec)
    summary = {
        "study": spec["study"], "split": "blind", "shots": len(inputs), "target": spec["target"],
        "goals": sum(r["event"] == "in" for r in truth.values()),
        "grid": cfg["study"]["grid"], "goal_area_m2": thresholds["goal_area_m2"], "min_ess": cfg["study"]["min_ess"],
        "bootstrap": {"draws": spec["bootstrap_draws"], "seed": spec["bootstrap_seed"],
                      "unit": "kick", "interval": "pointwise percentile 95%, conditional on calibration",
                      "difference": "a minus b; each draw uses the available paired observations for its metric"},
        "groups": summary_groups, "observable_groups": signal_groups,
        "stable_spin_pairs": stable_comparisons(scenarios, stable_ids, spec),
        "curvature": curvature_summary(curvature, stable_ids, cfg, spec),
        "repeat": repeat_summary,
    }
    write_csv(out / "scores.csv", rows)
    write_csv(out / "curvature.csv", curvature)
    write_csv(out / "repeat.csv", repeated, REPEAT_FIELDS)
    write_json(out / "summary.json", summary)
    return summary
