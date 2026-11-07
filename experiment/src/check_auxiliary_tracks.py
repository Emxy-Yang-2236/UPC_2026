"""Reproduce the D03 video-track check and event-source screen (Python 3.9+)."""

import argparse
import csv
import hashlib
import io
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen


SOURCES = {
    "ISSIA-3D.csv": {
        "url": "https://github.com/mguti97/SoccerNet-v3D/releases/download/v1.0.0/ISSIA-3D.csv",
        "bytes": 451850,
        "sha256": "7f4b33068498d537186f6541a232c0959a23ed0af5bc3bd1ec924ffe8270ddc4",
    },
    "statsbomb_3869685.json": {
        "url": "https://raw.githubusercontent.com/hudl/open-data/0bb2d94a146808c2297936b99b6da8e9b2a05138/data/events/3869685.json",
        "bytes": 3757121,
        "sha256": "a0b0036d50c10a4c8879d1ee9f24a7502ec2cfb264a61951c8d500dfc897ec35",
    },
}
FPS = 25
OBSERVATION_GAP = 2
TARGET_OFFSET = 5


def read_source(name, source_dir):
    spec = SOURCES[name]
    if source_dir is None:
        request = Request(spec["url"], headers={"User-Agent": "UPC-football-research"})
        with urlopen(request, timeout=45) as response:
            data = response.read()
    else:
        data = (source_dir / name).read_bytes()
    if len(data) != spec["bytes"] or hashlib.sha256(data).hexdigest() != spec["sha256"]:
        raise ValueError(f"Input does not match the frozen source: {name}")
    return data.decode("utf-8")


def extrapolate(first, last):
    ahead = (TARGET_OFFSET - OBSERVATION_GAP) / OBSERVATION_GAP
    return [p2 + ahead * (p2 - p0) for p0, p2 in zip(first, last)]


def check_tracks(text):
    frames = 0
    annotated_multiview = 0
    used_camera_counts = Counter()
    segments = issued = 0
    hold_errors, linear_errors = [], []
    previous_row = previous_valid = start = None

    for row in csv.DictReader(io.StringIO(text)):
        frames += 1
        frame = int(row["frame"])
        if previous_row is not None and frame <= previous_row:
            raise ValueError(f"Frames must increase once each: {frame}")
        previous_row = frame
        annotated = int(row["num_cameras"])
        annotated_multiview += annotated >= 2
        if annotated < 2 or not row["ball_3D"]:
            continue
        xyz = json.loads(row["ball_3D"])
        views = set(json.loads(row["cam_list"]))
        if len(xyz) != 3 or not all(map(math.isfinite, xyz)) or len(views) < 2:
            continue
        used_camera_counts[len(views)] += 1
        if previous_valid is None or frame != previous_valid + 1:
            start = frame
            first = xyz
            segments += 1
        previous_valid = frame
        offset = frame - start
        if offset == OBSERVATION_GAP:
            # Each segment issues just once. Neither calculation sees the target.
            last = xyz
            forecast = extrapolate(first, last)
            issued += 1
        if offset == TARGET_OFFSET:
            hold_errors.append(math.dist(last, xyz))
            linear_errors.append(math.dist(forecast, xyz))

    scored = len(linear_errors)
    return {
        "fps": FPS,
        "input_offsets_frames": [0, OBSERVATION_GAP],
        "target_offset_frames": TARGET_OFFSET,
        "forecast_horizon_s": (TARGET_OFFSET - OBSERVATION_GAP) / FPS,
        "annotation_rows": frames,
        "at_least_two_annotating_cameras": annotated_multiview,
        "usable_frames": sum(used_camera_counts.values()),
        "usable_frames_by_cameras_used": dict(used_camera_counts),
        "contiguous_multiview_segments": segments,
        "short_before_second_input": segments - issued,
        "issued": issued,
        "lost_before_target": issued - scored,
        "scored": scored,
        "median_error_m": {
            "constant_velocity": statistics.median(linear_errors),
            "persistence": statistics.median(hold_errors),
        },
        "lower_error_segments": {
            "constant_velocity": sum(a < b for a, b in zip(linear_errors, hold_errors)),
            "persistence": sum(a > b for a, b in zip(linear_errors, hold_errors)),
            "tie": sum(a == b for a, b in zip(linear_errors, hold_errors)),
        },
    }


def check_events(text):
    events = json.loads(text)
    outcomes, by_period = Counter(), Counter()
    at_line, before_line = Counter(), Counter()
    before_x = []
    three_coordinates = 0
    for event in events:
        shot = event.get("shot", {})
        if shot.get("type", {}).get("name") != "Penalty":
            continue
        outcome = shot["outcome"]["name"]
        outcomes[outcome] += 1
        by_period[event["period"]] += 1
        end = shot.get("end_location", [])
        if len(end) == 3 and all(map(math.isfinite, end)):
            three_coordinates += 1
            if end[0] == 120.0:
                at_line[outcome] += 1
            elif end[0] < 120.0:
                before_line[outcome] += 1
                before_x.append(end[0])
    return {
        "match_id": 3869685,
        "total_events": len(events),
        "penalties": sum(outcomes.values()),
        "penalties_by_outcome": dict(outcomes),
        "penalties_by_period": dict(by_period),
        "finite_3d_end_location": three_coordinates,
        "endpoint_at_x120_by_outcome": dict(at_line),
        "endpoint_before_x120_by_outcome": dict(before_line),
        "before_line_x_provider_scale": before_x,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, help="Read the two pinned files locally")
    parser.add_argument("--output", type=Path, required=True, help="New summary JSON file")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("--output already exists")
    result = {
        "sources": SOURCES,
        "issia": check_tracks(read_source("ISSIA-3D.csv", args.source_dir)),
        "statsbomb": check_events(read_source("statsbomb_3869685.json", args.source_dir)),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(result, out, sort_keys=True, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
