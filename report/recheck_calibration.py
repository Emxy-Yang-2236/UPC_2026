"""Recheck the published Z11 calibration ranks and held-out summaries with the standard library."""
import argparse
from collections import defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from statistics import mean
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
METHODS = ("nominal", "S_half", "E_half", "both_half", "gravity")


def score(value):
    return None if value == "" else float(value)


def verify(archive):
    with ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read("sha256.json"))
        for name, digest in manifest.items():
            assert hashlib.sha256(bundle.read(name)).hexdigest() == digest, name
        summary = json.loads(bundle.read("summary.json"))

        def rows(name):
            return list(csv.DictReader(io.StringIO(bundle.read(name).decode("utf-8"))))

        calibration = rows("calibration-scores.csv")
        test = rows("test-goal-scores.csv")
    grouped = defaultdict(list)
    seen = set()
    for r in calibration:
        key = (r["batch"], r["id"], r["method"])
        assert key not in seen
        seen.add(key)
        grouped[int(r["batch"]), r["method"]].append(score(r["score"]))
    indexed = {(r["id"], r["method"]): r for r in test}
    assert len(indexed) == len(test) == 368 * len(METHODS)
    assert all({r["id"] for r in test if r["method"] == m} == {r["id"] for r in test} for m in METHODS)
    area_per_cell = (7.32/30) * (2.44/10)
    wins = defaultdict(list)
    for b in summary["calibration_batches"]:
        i = b["batch"]
        for m in METHODS:
            values = grouped[i, m]
            n = len(values)
            rank = math.ceil(.9 * (n + 1))
            ordered = sorted(1. if x is None else x for x in values)
            threshold = ordered[rank - 1] if rank <= n else 1.
            archived = b["cuts"][m]
            assert (archived["n"], archived["rank"], archived["threshold"]) == (n, rank, threshold)
            assert archived["missing_distribution_n"] == values.count(None)
            for name in ("all", "stable_spin"):
                subset = [r for r in test if r["method"] == m and (name == "all" or r["family"] == name)]
                vals = [score(r["score"]) for r in subset]
                s = b["test"][name][m]
                assert (s["goals"], s["available"]) == (len(subset), len(vals)-vals.count(None))
                assert s["hits"] == sum(x is not None and x <= threshold for x in vals)
                cells = [int(r[f"cells_{i}"]) for r in subset]
                assert all(0 <= c <= 300 for c in cells)
                assert math.isclose(s["mean_area_m2"], area_per_cell*mean(cells), abs_tol=1e-12)
        for name, values in b["test"].items():
            aero, gravity = values["nominal"], values["gravity"]
            hit_delta = aero["hits"] - gravity["hits"]
            wins[name].append(hit_delta)
            assert hit_delta * (aero["mean_area_m2"] - gravity["mean_area_m2"]) > 0
    nominal = summary["z10_nominal_cutoff"]
    for m, s in summary["stable_spin_prior"].items():
        subset = [r for r in test if r["method"] == m and r["family"] == "stable_spin"]
        values = [score(r["score"]) for r in subset]
        assert s["fixed_nominal_hits"] == sum(x is not None and x <= nominal for x in values)
        errors = [float(r["error_m"]) for r in subset if r["error_m"]]
        deltas = [float(r["error_m"])-float(indexed[r["id"], "nominal"]["error_m"])
                  for r in subset if r["error_m"] and indexed[r["id"], "nominal"]["error_m"]]
        assert (s["goals"], s["paired_points"]) == (len(subset), len(deltas))
        assert math.isclose(s["mean_error_m"], mean(errors), abs_tol=1e-12)
        assert math.isclose(s["error_difference_m"], mean(deltas), abs_tol=1e-12)
        assert math.isclose(s["mean_true_rank"], mean(int(r["rank"]) for r in subset if r["rank"]))
    return {"status": "pass", "cutoffs": len(grouped), "calibration_score_rows": len(calibration),
            "test_goal_score_rows": len(test), "hit_differences": dict(wins)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT/"evidence/z11-scores.zip")
    print(json.dumps(verify(parser.parse_args().archive)))
