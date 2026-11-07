"""Independently check D02 from native frames with Python's standard library."""
import argparse
import copy
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def read(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def close(a, b, tol=1e-9):
    if not math.isclose(float(a), float(b), abs_tol=tol, rel_tol=0):
        raise ValueError(f"Mismatch: {a} versus {b}")


def verify(raw, run, settings):
    lock = json.loads((run/"lock.json").read_text())
    for name, digest in lock["early_artifact_sha256"].items():
        if hashlib.sha256((run/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Changed locked file: {name}")
    if hashlib.sha256(settings.read_bytes()).hexdigest() != lock["settings_sha256"]:
        raise ValueError("Changed B03 settings")
    cfg = json.loads(settings.read_text())
    p, g, dt = cfg["physics"], cfg["physics"]["g"], .04
    u = math.sqrt(sum(max(abs(a),abs(b))**2 for a,b in zip(p["velocity_hi"],p["velocity_lo"]))) + p["wind_cap"] + 2*dt*g
    k = p["air_density"] * math.pi * p["radius"]**2 / (2*p["mass"])
    A = g + max(math.hypot(p["kappa"][1]*u**2, p["beta_cap"]*math.sqrt(3)*u),
                k*u**2*math.hypot(.155+.346+p["drag_offset"][1], .38))
    raw_by_shot = defaultdict(list)
    for r in read(raw/"frames.csv"):
        raw_by_shot[r["event_id"]].append(r)
    refs = {r["event_id"]: r for r in read(run/"reference.csv")}
    certs = {r["event_id"]: r for r in read(run/"support.csv")}
    scores = {(r["event_id"],r["mask"],r["method"]): r for r in read(run/"scores.csv")}
    predictions = {r["event_id"]: r for r in json.loads((run/"predictions.json").read_text())}
    inputs = json.loads((run/"inputs.json").read_text())
    if len(inputs) != 3 or len(raw_by_shot) != len(inputs) or len(scores) != 6*len(inputs):
        raise ValueError("Expected all three D01 shots and all 18 estimates")
    model_points = 0
    for entry in inputs:
        id_ = entry["event_id"]
        rows = raw_by_shot[id_]
        i = next(i for i in range(1,len(rows)) if rows[i-1]["ball_status"]=="0" and rows[i]["ball_status"]=="1")
        frames = rows[i:i+3]
        if [int(r["frame"]) for r in frames] != entry["frames"]:
            raise ValueError("Unexpected anchor")
        xyz = [[float(r["x_m"])-41.5, float(r["y_m"]), float(r["z_m"])] for r in frames]
        for j, r in enumerate(frames):
            t = (datetime.fromisoformat(r["utc"])-datetime.fromisoformat(frames[0]["utc"])).total_seconds()
            close(t, dt*j)
            for a,b in zip(xyz[j],entry["xyz_m"][j]):
                close(a,b)
        # First two active consecutive samples bracketing the line, strictly later than the inputs.
        a,b = next((a,b) for a,b in zip(rows,rows[1:]) if a["ball_status"]==b["ball_status"]=="1"
                   and float(a["x_m"])<52.5<=float(b["x_m"]))
        if int(a["frame"]) <= entry["frames"][-1] or int(b["frame"]) != int(a["frame"])+1:
            raise ValueError("Input/target separation or bracket invalid")
        f = (52.5-float(a["x_m"]))/(float(b["x_m"])-float(a["x_m"]))
        target = [(1-f)*float(a[c])+f*float(b[c]) for c in ("y_m","z_m")]
        ref = refs[id_]
        for val, col in zip(target, ["gate_y_m","gate_z_m"]):
            close(val,ref[col])
        close((int(a["frame"])-entry["frames"][0]+f)*dt,ref["gate_after_anchor_s"])
        eps = cfg["observation"]["quantum_m"]/2
        req_second = max(abs(b2-2*b1+b0)-3*eps for b0,b1,b2 in zip(*xyz))/dt**2
        req_vertical = 2*(p["velocity_lo"][2]*dt - (xyz[1][2]-xyz[0][2]+eps))/dt**2
        cert = certs[id_]
        close(A, cert["a_ceiling_all_m_s2"])
        close(max(0.,req_second,req_vertical), cert["min_a_needed_m_s2"])
        if max(req_second,req_vertical) <= A or cert["incompatible_both"] != "1":
            raise ValueError("Missing impossibility certificate")
        for mask, selected in (("both",(1,2)),("late",(2,))):
            model = predictions[id_]["masks"][mask]["aero"]
            row = scores[id_,mask,"aero"]
            if model["events"] is not None:
                close(sum(model["events"]), 1.)
            if model["point"] is None:
                if row["gate_error_m"]:
                    raise ValueError("Missing probability forecast has a finite error")
            else:
                model_points += 1
                close(math.dist(model["point"],target),row["gate_error_m"])
                close(sum(model["cell_mass"].values()), 1.)
                ey=(target[0]+cfg["official"]["half_width"])/(2*cfg["official"]["half_width"])*30
                ez=target[1]/cfg["official"]["height"]*10
                true_cell=math.floor(ey)*10+math.floor(ez)
                if (true_cell in model["raw90_cells"]) != bool(int(row["raw90_includes_reference"])):
                    raise ValueError("Raw-region label mismatch")
            for name, gravity in (("gravity",g),("line",0.)):
                row = scores[id_,mask,name]
                t2 = sum((j*dt)**2 for j in selected)
                v = [sum(j*dt*(xyz[j][axis]-xyz[0][axis]+(.5*gravity*(j*dt)**2 if axis==2 else 0.))
                         for j in selected)/t2 for axis in range(3)]
                t = (11.-xyz[0][0])/v[0]
                plane = [xyz[0][1]+v[1]*t, xyz[0][2]+v[2]*t-.5*gravity*t*t]
                close(math.dist(plane,target),row["plane_error_m"])
                # At forward gate and before the time limit, a concave or linear z(t)
                # with z(0)>=R crosses the floor before the gate iff z(gate)<=R (descending).
                expected = ("ground" if plane[1]<=p["radius"] else
                            "in" if abs(plane[0])<cfg["official"]["half_width"] and plane[1]<cfg["official"]["height"]
                            else "out")
                if expected != row["prediction"] or bool(row["gate_error_m"]) == (expected=="ground"):
                    raise ValueError("First-event/virtual-plane mismatch")
    return {"status":"pass","native_anchors":len(inputs),"later_crossings":len(refs),
            "certificates_checked":len(certs),"scored_method_mask_cases":len(scores),
            "conditional_model_locations_both_and_late":model_points,
            "max_absolute_tolerance":1e-9}


def check_masking(raw, run, settings):
    """With NumPy available, replay the late mask and remove the entire future from extraction."""
    from empirical_penalties import forecast, prepare
    saved = json.loads((run/"inputs.json").read_text())
    cuts = {s["event_id"]: s["frames"][-1] for s in saved}
    early_only = [r for r in read(raw/"frames.csv") if int(r["frame"]) <= cuts[r["event_id"]]]
    if prepare(early_only) != saved:
        raise ValueError("Post-cutoff frames changed forecast inputs")
    hidden_replaced = copy.deepcopy(saved)
    for s in hidden_replaced:
        s["xyz_m"][1] = [111., 222., 333.]
    replay, _ = forecast(hidden_replaced, json.loads(settings.read_text()))
    locked = json.loads((run/"predictions.json").read_text())
    if any(a["masks"]["late"] != b["masks"]["late"] for a,b in zip(replay,locked)):
        raise ValueError("Unobserved 40 ms frame changed the late-only forecast")
    return {"truncated_windows_with_identical_inputs":len(saved),
            "altered_hidden_frames_with_identical_late_forecast":len(saved)}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",type=Path,default=root/"experiment/data/raw/idsse-penalties")
    parser.add_argument("--settings",type=Path,default=root/"design/settings.json")
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--masking",action="store_true",help="also challenge causal masking using NumPy")
    args = parser.parse_args()
    result = verify(args.raw,args.run,args.settings)
    if args.masking:
        result.update(check_masking(args.raw,args.run,args.settings))
    print(json.dumps(result,indent=2))
