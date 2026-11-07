"""D02: causal forecasts in three 25 Hz IDSSE penalty windows, then goal-line scoring."""
import argparse
import copy
import csv
import hashlib
import json
import math
import platform
from itertools import groupby, islice
from pathlib import Path

import numpy as np

from flight import cell_edges, cell_geometry, cell_ids
from predict import predict, region, summarize

ROOT = Path(__file__).resolve().parents[2]
GATE_X = 52.50
PENALTY_X = 41.50
STEP = 0.040
SEEDS = (63041, 63059)
MASKS = {"both": (0, 1), "late": (1,)}


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(path, rows):
    with path.open("x", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_table(path):
    with path.open(newline="", encoding="utf-8") as source:
        yield from csv.DictReader(source)


def prepare(rows):
    """Only consume a shot through its second post-anchor observation. All gates face +X."""
    prepared = []
    for (match, event), group in groupby(rows, lambda row: (row["match_id"], row["event_id"])):
        item = {"match_id": match, "event_id": event}
        prepared.append(item)
        last_status = None
        for row in group:
            if last_status == "0" and row["ball_status"] == "1":
                break
            last_status = row["ball_status"]
        else:
            item["status"] = "missing_dead_to_live_transition"
            continue
        early = [row, *islice(group, 2)]
        frames = [int(r["frame"]) for r in early]
        millis = [int(r["offset_from_event_ms"]) for r in early]
        if (len(early) != 3 or frames != list(range(frames[0], frames[0] + 3))
                or [m - millis[0] for m in millis] != [0, 40, 80]
                or any(r["ball_status"] != "1" for r in early)):
            item["status"] = "unavailable_native_inputs"
            continue
        item.update(status="ready", frames=frames, times_s=[0.0, STEP, 2*STEP],
                    xyz_m=[[round(float(r["x_m"]) - PENALTY_X, 2),
                            float(r["y_m"]), float(r["z_m"])] for r in early])
    return prepared


def acceleration_certificate(shot, cfg):
    """Necessary acceleration from early observations vs a rigorous whole-prior envelope."""
    p = cfg["physics"]
    r0, r1, r2 = np.asarray(shot["xyz_m"])
    eps = cfg["observation"]["quantum_m"] / 2
    vmax = np.maximum(np.abs(p["velocity_lo"]), np.abs(p["velocity_hi"]))
    # In constant wind the lift is orthogonal to u and the drag is dissipative.
    u = float(np.linalg.norm(vmax) + p["wind_cap"] + 2*STEP*p["g"])
    k = p["air_density"] * math.pi * p["radius"]**2 / (2*p["mass"])
    drag = p["kappa"][1] * u**2
    accel_d = p["g"] + drag
    accel_s = p["g"] + math.hypot(drag, math.sqrt(3)*p["beta_cap"]*u)
    cd_max = .155 + .346 + p["drag_offset"][1]
    accel_e = p["g"] + k*u**2 * math.hypot(cd_max, .38)
    envelope = max(accel_d, accel_s, accel_e)
    second_abs = np.abs(r2 - 2*r1 + r0)
    required = np.maximum(0., second_abs - 3*eps) / STEP**2
    # z_1-z_0 >= v_z,min*h - A h^2/2. Only later readings have round-off here.
    vertical_gap = p["velocity_lo"][2]*STEP - (r1[2] - r0[2])
    down = max(0., 2*(vertical_gap - eps)/STEP**2)
    eps_floor = max(0., (max(second_abs) - envelope*STEP**2)/3,
                    vertical_gap - .5*envelope*STEP**2)
    return {"match_id": shot["match_id"], "event_id": shot["event_id"],
            "u_ceiling_m_s": u, "a_ceiling_D_m_s2": accel_d, "a_ceiling_S_m_s2": accel_s,
            "a_ceiling_E_m_s2": accel_e, "a_ceiling_all_m_s2": envelope,
            "min_ax_from_second_difference_m_s2": required[0],
            "min_ay_from_second_difference_m_s2": required[1],
            "min_az_from_second_difference_m_s2": required[2],
            "min_downward_a_from_vz_floor_m_s2": down,
            "min_a_needed_m_s2": max(down, max(required)),
            "minimum_halfwidth_from_necessary_tests_m": eps_floor,
            "incompatible_both": int(max(down, max(required)) > envelope)}


def kinematic(positions, times, r0, gate, cfg, g):
    """Least squares at the measured anchor; retain the virtual free-flight plane after ground."""
    p = cfg["physics"]
    accel = np.array([0., 0., -g])
    d = positions - r0 - .5*times[:, None]**2*accel
    v = times @ d / (times @ times)
    c = r0[2] - p["radius"]
    if c < 0 or (c == 0 and (v[2] < 0 or (v[2] == 0 and g > 0))):
        floor_t = 0.
    elif g:
        floor_t = (v[2] + math.sqrt(v[2]**2 + 2*g*c))/g
    elif v[2] < 0:
        floor_t = -c/v[2]
    else:
        floor_t = math.inf
    plane_t = (gate - r0[0])/v[0] if v[0] > 0 else math.inf
    horizon = cfg["solver"]["horizon"]
    point = None
    if 0 < plane_t <= horizon:
        point = (r0 + plane_t*v + .5*plane_t**2*accel)[1:].tolist()
    if floor_t <= min(plane_t, horizon):
        event = "ground"
    elif point is not None:
        inside = abs(point[0]) < cfg["official"]["half_width"] and 0 < point[1] < cfg["official"]["height"]
        event = "in" if inside else "out"
    else:
        event = "timeout"
    return {"first_event": event, "velocity_m_s": v.tolist(), "plane_point_m": point,
            "plane_time_s": float(plane_t) if point is not None else None,
            "direct_point_m": point if event in ("in", "out") else None}


def sample(visible, cfg, seed):
    infos, tracks = predict(visible, cfg, seed)
    results = summarize(infos, tracks, cfg)
    hist = np.array(results.pop("hist"))
    chosen = region(hist, cfg["study"]["coverage"])
    _, areas = cell_geometry(cell_edges(cfg))
    return dict(results, seed=seed, raw90_cells=np.flatnonzero(chosen).tolist(),
                raw90_area_m2=float(np.sum(areas[chosen])),
                cell_mass={str(int(i)): float(hist[i]) for i in np.flatnonzero(hist)})


def forecast(inputs, cfg):
    """This interface receives early positions, the known pitch geometry and fixed settings only."""
    forecasts, certificates = [], []
    for index, shot in enumerate(inputs):
        result = {"match_id": shot["match_id"], "event_id": shot["event_id"], "status": shot["status"]}
        forecasts.append(result)
        if shot["status"] != "ready":
            continue
        native = copy.deepcopy(cfg)
        anchor, *xyz = shot["xyz_m"]
        native["official"] = {"r0": anchor, "times": shot["times_s"][1:], "gate": GATE_X - PENALTY_X,
                              "height": cfg["official"]["height"], "half_width": cfg["official"]["half_width"]}
        certificates.append(acceleration_certificate(shot, native))
        result["masks"] = {}
        for mask, indices in MASKS.items():
            visible = {i: np.asarray(xyz[i]) for i in indices}
            times = np.asarray([native["official"]["times"][i] for i in indices])
            observed = np.asarray([visible[i] for i in indices])
            estimates = [sample(visible, native, [s, index, len(indices)]) for s in SEEDS]
            baselines = {}
            for name, g in (("line", 0.), ("gravity", cfg["physics"]["g"])):
                baselines[name] = kinematic(observed, times, np.asarray(anchor), native["official"]["gate"], native, g)
            result["masks"][mask] = dict(aero=estimates[0], replicate=estimates[1], **baselines)
    return forecasts, certificates


def references(raw, inputs):
    """Open reference labels only after the forecasts are sealed. Compute in native precision."""
    labels = {(r["match_id"], r["event_id"]): r for r in read_table(raw/"shots.csv")}
    prepared = {(s["match_id"], s["event_id"]): s for s in inputs}
    refs = []
    for key, group in groupby(read_table(raw/"frames.csv"), lambda r: (r["match_id"], r["event_id"])):
        rows = list(group)
        label = labels[key]
        pairs = [(a,b) for a,b in zip(rows, rows[1:]) if a["ball_status"] == b["ball_status"] == "1"
                 and float(a["x_m"]) < GATE_X <= float(b["x_m"])]
        if len(pairs) != 1:
            raise ValueError(f"Unexpected goal-line brackets for {key}")
        a,b = pairs[0]
        n0,n1 = int(a["frame"]),int(b["frame"])
        if n1 != n0+1 or [n0,n1] != [int(label["left_frame"]), int(label["right_frame"])]:
            raise ValueError(f"Goal-line frame mismatch for {key}")
        frac = (GATE_X-float(a["x_m"]))/(float(b["x_m"])-float(a["x_m"]))
        y,z = [float(a[k]) + frac*(float(b[k])-float(a[k])) for k in ("y_m","z_m")]
        if max(abs(y-float(label["gate_y_m"])), abs(z-float(label["gate_z_m"]))) > .0000501:
            raise ValueError(f"Independent goal-line interpolation mismatch for {key}")
        anchor = prepared[key].get("frames", [None])[0]
        if anchor is not None and anchor+2 >= n0:
            raise ValueError(f"Reference window overlaps inputs for {key}")
        refs.append(dict(match_id=key[0], event_id=key[1], provider_outcome=label["result"],
                         left_frame=n0, right_frame=n1, interpolation_fraction=frac,
                         gate_after_anchor_s=(n0-anchor+frac)*STEP if anchor is not None else None,
                         gate_y_m=y, gate_z_m=z, direct_first_event="unverified"))
    if len(refs) != len(inputs) or len(refs) != len(labels):
        raise ValueError("Different candidate denominators")
    return refs


def score(forecasts, refs, cfg):
    by_id = {(r["match_id"], r["event_id"]): r for r in refs}
    edges = cell_edges(cfg)
    rows = []
    for shot in forecasts:
        ref = by_id[(shot["match_id"], shot["event_id"])]
        target = [ref["gate_y_m"], ref["gate_z_m"]]
        cid = int(cell_ids(np.array([target]), edges)[0])
        for mask, methods in shot.get("masks", {}).items():
            for method in ("aero", "line", "gravity"):
                est = methods[method]
                if method == "aero":
                    point = est["point"]
                    plane = point
                    category = "conditional_in" if point is not None else (
                        "no_compatible_sample" if est["events"] is None else "no_direct_in_mass")
                    hit = int(cid in est["raw90_cells"]) if point is not None else None
                else:
                    point = est["direct_point_m"]
                    plane = est["plane_point_m"]
                    category, hit = est["first_event"], None
                distance = math.dist(point, target) if point is not None else None
                extended_distance = math.dist(plane, target) if plane is not None else None
                rows.append(dict(match_id=shot["match_id"], event_id=shot["event_id"], mask=mask, method=method,
                                 prediction=category, point_y_m=point[0] if point is not None else None,
                                 point_z_m=point[1] if point is not None else None, gate_error_m=distance,
                                 plane_y_m=plane[0] if plane is not None else None,
                                 plane_z_m=plane[1] if plane is not None else None,
                                 plane_error_m=extended_distance, raw90_includes_reference=hit))
    return rows


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--raw", type=Path, default=ROOT/"experiment/data/raw/idsse-penalties")
    cli.add_argument("--settings", type=Path, default=ROOT/"design/settings.json")
    cli.add_argument("--out", required=True, type=Path, help="new output directory")
    args = cli.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cfg = load(args.settings)
    inputs = prepare(read_table(args.raw/"frames.csv"))
    dump(args.out/"inputs.json", inputs)
    forecasts, certs = forecast(load(args.out/"inputs.json"), cfg)
    dump(args.out/"predictions.json", forecasts)
    table(args.out/"support.csv", certs)
    lock = {"settings_sha256": sha(args.settings), "native_step_s": STEP,
            "source_sha256": {name: sha(Path(__file__).with_name(name))
                              for name in ("empirical_penalties.py", "predict.py", "flight.py")},
            "early_artifact_sha256": {name: sha(args.out/name) for name in ("inputs.json", "predictions.json", "support.csv")},
            "python": platform.python_version(), "numpy": np.__version__, "backend": "CPU float64"}
    dump(args.out/"lock.json", lock)
    if any(sha(args.out/name) != value for name,value in load(args.out/"lock.json")["early_artifact_sha256"].items()):
        raise ValueError("Forecast lock mismatch before opening references")
    refs = references(args.raw, inputs)
    table(args.out/"reference.csv", refs)
    scores = score(load(args.out/"predictions.json"), refs, cfg)
    table(args.out/"scores.csv", scores)
    summary = {"source_matches": 7, "penalty_windows": len(inputs), "prepared": sum(r["status"]=="ready" for r in inputs),
               "with_measured_crossing": len(refs), "verified_release_within_10ms": 0,
               "with_verified_direct_first_event": 0, "strict_V6_eligible": 0,
               "source_sha256": {name: sha(args.raw/name) for name in ("frames.csv","shots.csv")},
               "predicted_direct_or_conditional_points": {
                   mask: {m: sum(r["gate_error_m"] is not None for r in scores if r["mask"]==mask and r["method"]==m)
                          for m in ("aero","line","gravity")} for mask in MASKS},
               "certified_incompatible_both": sum(row["incompatible_both"] for row in certs)}
    dump(args.out/"summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
