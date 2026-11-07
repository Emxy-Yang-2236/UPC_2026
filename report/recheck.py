"""Recompute representative published results from the standalone handoff tables."""
import csv
import json
import math
import statistics
from pathlib import Path

DATA=Path(__file__).resolve().parent/"evidence"


def read_csv(name):
    with (DATA/name).open(newline="",encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    m=json.loads((DATA/"measurements.json").read_text(encoding="utf-8"))
    rows=read_csv("blind.csv")
    predicted=[r for r in rows if r["mask"]=="both"]
    inside=[r for r in predicted if r["truth_event"]=="in"]
    assert len({r["id"] for r in predicted})==len(predicted)==48 and len(inside)==33
    raw=sum(int(r["raw_hit"]) for r in inside)
    adjusted=sum(int(r["cal_hit"]) for r in inside)
    errors=[float(r["point_error_m"]) for r in inside]
    score=statistics.mean(float(r["brier"]) for r in predicted)
    grid=read_csv("grid.csv")
    assert abs(sum(float(r["probability"]) for r in grid)-1)<1e-10
    mode=max(grid,key=lambda r:float(r["probability"]))
    point=[float(mode["y_m"]),float(mode["z_m"])]
    area=sum(int(r["in_raw_90"]) for r in grid)*(.244**2)
    sep=math.dist(*(s["goal_yz_m"] for s in m["pair"]["shots"]))
    assert math.dist(point,m["official"]["point"])<1e-12 and abs(area-m["official"]["raw_area_m2"])<1e-10
    ref=m["blind"]["groups"]["all"]["both"]
    assert raw==ref["raw"]["hit"] and adjusted==ref["cal"]["hit"]
    assert abs(statistics.median(errors)-ref["median_point_m"])<1e-10 and abs(score-ref["brier"])<1e-10
    assert abs(sep/2-m["pair"]["half_separation_m"])<1e-10 and m["matlab"]["status"]=="pass"
    print(json.dumps({"gate_mode_m":point,"region_m2":area,"hit_raw":[raw,len(inside)],"hit_cal":[adjusted,len(inside)],
                      "blind_median_m":statistics.median(errors),"event_brier":score,"paired_bound_m":sep/2,"status":"pass"}))


if __name__=="__main__":
    main()
