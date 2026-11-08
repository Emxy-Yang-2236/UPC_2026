"""Apply both previously fitted 90% cutoffs to each archived stable-spin test cohort."""
import argparse
import csv
from io import StringIO
import gzip
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
NY, NZ = 30, 10
DY, DZ = 7.32/NY, 2.44/NZ
CELL_AREA = DY*DZ
CENTRES = [(-3.66+(iy+.5)*DY, (iz+.5)*DZ) for iy in range(NY) for iz in range(NZ)]


def records(path, study):
    with ZipFile(path) as archive:
        get = lambda key: json.loads(archive.read(key))
        cuts = get("thresholds.json")
        if study == "Z09":
            pos = get("config.json")["levels"].index(.9)
            thresholds = {m:cuts["tracking/"+code][pos] for m,code in [("aero","both"),("gravity","gravity")]}
            seal = get("blind-lock.json")["sha256"]
        else:
            thresholds = {m:cuts["pooled"]["tracking"][code]["threshold"]
                          for m,code in [("aero","nominal"),("gravity","gravity")]}
            seal = get("predictions-lock.json")["blind-predictions.json.gz"]
        frozen = archive.read("blind-predictions.json.gz")
        assert hashlib.sha256(frozen).hexdigest() == seal
        truth = {r["id"]:r for r in get("blind-truth.json") if r["family"]=="stable_spin" and r["event"]=="in"}
        rows = {(r["id"],r["method"]):r for r in json.loads(gzip.decompress(frozen))
                if r["profile"] == "tracking" and r["id"] in truth and r["method"] in ("nominal","both","gravity")}
        archived = {}
        for r in csv.DictReader(StringIO(archive.read("scores.csv").decode())):
            if r["id"] not in truth or r["profile"]!="tracking" or r.get("calibration","pooled")!="pooled":
                continue
            if (r["id"],r["method"]) in rows:
                archived[r["id"],r["method"]] = int(r.get("hit",r.get("hit_0.9")))
    return thresholds, truth, rows, archived


def select_cells(row, threshold):
    if row["point"] is None:
        return set()
    if row["method"] == "gravity":
        L = math.hypot(7.32,2.44)
        d = [math.dist(c,row["point"]) for c in CENTRES]
        return {k for k,x in enumerate(d) if x/(L+x)<=threshold}
    prob = row["hist"]
    if not any(prob):
        return set()
    if threshold >= 1:
        return set(range(NY*NZ))
    total = 0.
    chosen = set()
    for k in sorted(range(len(prob)), key=lambda k:-prob[k]):
        if prob[k] == 0 or total > threshold:
            break
        chosen.add(k)
        total += prob[k]
    return chosen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--z09",type=Path,default=HERE/"evidence/z09-replay.zip")
    parser.add_argument("--z10",type=Path,default=HERE/"evidence/z10-replay.zip")
    args=parser.parse_args()
    runs={name:records(path,name) for name,path in [("Z09",args.z09),("Z10",args.z10)]}
    out = []
    for cohort, (_,truth,rows,archived) in runs.items():
        own_decisions = {}
        all_points = {}
        for origin, (cuts,*_) in runs.items():
            for role, code in [("aero","both" if cohort=="Z09" else "nominal"),("gravity","gravity")]:
                decisions,areas={},[]
                for sid,target in truth.items():
                    y,z=target["yz"]
                    cell=math.floor((y+3.66)/DY)*NZ+math.floor(z/DZ)
                    cells=select_cells(rows[sid,code],cuts[role])
                    decisions[sid]=int(cell in cells)
                    areas.append(len(cells)*CELL_AREA)
                    if origin==cohort:
                        assert decisions[sid]==archived[sid,code]
                if origin==cohort:
                    own_decisions[role]=decisions
                all_points[origin,role]=(cuts[role],decisions,areas)
        for (origin,role),(cut,hits,areas) in all_points.items():
            base=own_decisions[role]
            out.append(dict(test=cohort,calibration=origin,method=role,threshold=cut,goals=len(hits),
                            hits=sum(hits.values()),mean_area_m2=mean(areas),
                            gains_vs_own=sum(h and not base[s] for s,h in hits.items()),
                            losses_vs_own=sum(base[s] and not h for s,h in hits.items())))
    print(json.dumps(out,indent=2,allow_nan=False))


if __name__ == "__main__":
    main()
