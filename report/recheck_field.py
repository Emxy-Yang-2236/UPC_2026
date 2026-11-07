"""Independently reconstruct gate crossings and feasibility bounds from native field frames."""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent / "evidence"
FIELD = EVIDENCE / "field"


def read_table(name):
    with (FIELD / name).open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def close(a, b):
    assert math.isclose(a, float(b), abs_tol=1e-9, rel_tol=1e-12), (a, b)


def main():
    frames = defaultdict(list)
    for row in read_table("frames.csv"):
        frames[(row["match_id"], row["event_id"])].append(row)
    reference = {(r["match_id"], r["event_id"]): r for r in read_table("reference.csv")}
    certificates = {(r["match_id"], r["event_id"]): r for r in read_table("support.csv")}
    scores = read_table("scores.csv")
    cfg = json.loads((EVIDENCE / "measurements.json").read_text())["config"]["physics"]
    h, eps = 0.04, 0.005
    g = cfg["g"]
    speed = math.sqrt(sum(max(abs(lo), abs(hi))**2 for lo, hi in
                          zip(cfg["velocity_lo"], cfg["velocity_hi"]))) + cfg["wind_cap"] + 2*h*g
    k = cfg["air_density"] * math.pi * cfg["radius"]**2 / (2 * cfg["mass"])
    drag = cfg["kappa"][1] * speed**2
    cd = 0.155 + 0.346 + cfg["drag_offset"][1]
    ceiling = g + max(drag, math.hypot(drag, math.sqrt(3)*cfg["beta_cap"]*speed),
                      k * speed**2 * math.hypot(cd, 0.38))
    values = []
    for key, series in frames.items():
        assert len(series) == 101
        series.sort(key=lambda r: int(r["frame"]))
        start = next(i for i in range(1, len(series))
                     if series[i-1]["ball_status"] == "0" and series[i]["ball_status"] == "1")
        early = series[start:start+3]
        assert [int(d["frame"])-int(early[0]["frame"]) for d in early] == [0, 1, 2]
        assert [int(d["offset_from_event_ms"])-int(early[0]["offset_from_event_ms"])
                for d in early] == [0, 40, 80]
        axes = [[float(d[name]) for d in early] for name in ("x_m", "y_m", "z_m")]
        second = max((abs(r2 - 2*r1 + r0) - 3*eps)/h**2 for r0, r1, r2 in axes)
        z0, z1, _ = axes[2]
        lower = max(0, second, 2*(cfg["velocity_lo"][2]*h - (z1 - z0) - eps)/h**2)
        close(ceiling, certificates[key]["a_ceiling_all_m_s2"])
        close(lower, certificates[key]["min_a_needed_m_s2"])
        assert lower > ceiling and int(certificates[key]["incompatible_both"]) == 1
        left, right = next((a, b) for a, b in zip(series[start+2:], series[start+3:])
                           if a["ball_status"] == b["ball_status"] == "1"
                           and float(a["x_m"]) < 52.5 <= float(b["x_m"]))
        assert int(left["frame"]) > int(early[-1]["frame"])
        f = (52.5 - float(left["x_m"])) / (float(right["x_m"]) - float(left["x_m"]))
        yz = [(1-f)*float(left[c]) + f*float(right[c]) for c in ("y_m","z_m")]
        close(yz[0], reference[key]["gate_y_m"])
        close(yz[1], reference[key]["gate_z_m"])
        per_shot = [r for r in scores if (r["match_id"], r["event_id"]) == key]
        assert len(per_shot) == 6
        for r in per_shot:
            if r["point_y_m"]:
                close(math.dist(yz, (float(r["point_y_m"]), float(r["point_z_m"]))), r["gate_error_m"])
            else:
                assert not r["gate_error_m"]
        assert any(r["method"] == "aero" and r["mask"] == "both"
                   and r["prediction"] == "no_compatible_sample" for r in per_shot)
        values.append({"match": key[0], "gate_m": yz, "lower_accel_m_s2": lower})
    assert len(values) == 3
    late = [float(r["gate_error_m"]) for r in scores
            if r["method"] == "aero" and r["mask"] == "late" and r["gate_error_m"]]
    assert len(late) == 1
    print(json.dumps({"status": "pass", "cases": values, "native_accel_ceiling_m_s2": ceiling,
                      "late_point_errors_m": late, "compatible_two_frame_cases": 0}))


if __name__ == "__main__":
    main()
