"""Rebuild the three IDSSE penalty windows and their goal-line references (Python 3.9+)."""
import argparse
import csv
from datetime import datetime, timedelta
from hashlib import md5, sha256
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

MANIFEST = Path(__file__).resolve().parents[1] / "data/raw/idsse-penalties/source-manifest.json"


def fetch(base, file):
    url = base + file["name"]
    headers = {"User-Agent": "UPC research source check"}
    bounds = file.get("range_inclusive")
    if bounds:
        start, end = bounds
        headers["Range"] = f"bytes={start}-{end}"
        url += f"?v6range={start}-{end}"
    with urlopen(Request(url, headers=headers), timeout=40) as reply:
        if bounds and reply.headers.get("Content-Range") != f"bytes {start}-{end}/{file['bytes']}":
            raise ValueError(f"Unexpected byte range for {file['name']}")
        data = reply.read()
    if bounds:
        valid = len(data) == end-start+1 and sha256(data).hexdigest() == file["range_sha256"]
    else:
        valid = len(data) == file["bytes"] and md5(data).hexdigest() == file["md5"]
    if not valid:
        raise ValueError(f"Source checksum mismatch for {file['name']}")
    return data


def window(event, fragment):
    stamp = datetime.fromisoformat(event.get("EventTime"))
    selected = []
    for item in re.finditer(rb"<Frame\s[^>]*?/>", fragment):
        if b"BallStatus=" not in item[0]:
            continue
        f = ET.fromstring(item[0])
        delay = datetime.fromisoformat(f.get("T")) - stamp
        if abs(delay) <= timedelta(seconds=2):
            selected.append(dict(match_id=event.get("MatchId"), event_id=event.get("EventId"),
                                 frame=int(f.get("N")), utc=f.get("T"),
                                 offset_from_event_ms=delay // timedelta(milliseconds=1),
                                 x_m=f.get("X"), y_m=f.get("Y"), z_m=f.get("Z"),
                                 ball_status=int(f.get("BallStatus"))))
    if [r["offset_from_event_ms"] for r in selected] != list(range(-2000, 2001, 40)):
        raise ValueError("Incomplete or irregular 25 Hz observation window")
    if any(b["frame"] != a["frame"]+1 for a,b in zip(selected,selected[1:])):
        raise ValueError("Frame numbers are not consecutive")
    return selected


def gate_reference(rows, half_length):
    candidates = []
    for i, (a, b) in enumerate(zip(rows, rows[1:])):
        if not (a["ball_status"] and b["ball_status"]):
            continue
        x0, x1 = float(a["x_m"]), float(b["x_m"])
        for sign in (-1, 1):
            if sign*x0 < half_length <= sign*x1:
                fraction = (sign*half_length-x0)/(x1-x0)
                y, z = [float(a[k])+fraction*(float(b[k])-float(a[k])) for k in ("y_m","z_m")]
                first = i
                while first > 0 and rows[first-1]["ball_status"]:
                    first -= 1
                candidates.append(dict(gate_x_m=sign*half_length, first_active_frame=rows[first]["frame"],
                                       first_active_offset_ms=rows[first]["offset_from_event_ms"],
                                       first_active_x_m=rows[first]["x_m"], first_active_z_m=rows[first]["z_m"],
                                       left_frame=a["frame"], right_frame=b["frame"],
                                       gate_offset_ms=round(a["offset_from_event_ms"]+40*fraction,2),
                                       gate_y_m=round(y,4), gate_z_m=round(z,4)))
    if len(candidates) != 1:
        raise ValueError(f"Expected one outward goal-line bracket, found {len(candidates)}")
    return candidates[0]


def write_csv(path, rows):
    with path.open("x", encoding="utf-8", newline="") as f:
        writer=csv.DictWriter(f, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="new directory for both CSVs")
    args=parser.parse_args()
    if args.out.exists():
        parser.error("Choose a new output directory")
    spec=json.loads(MANIFEST.read_text(encoding="utf-8"))
    frames, shots = [], []
    for match, files in spec["matches"].items():
        raw=ET.fromstring(fetch(spec["mirror"], files["events"]))
        penalties=[e for e in raw.iter("Event") if e.find("Penalty/ShotAtGoal") is not None]
        if bool(penalties) != ("position" in files):
            raise ValueError(f"Unexpected penalty selection for {match}")
        for event in penalties:
            shot=event.find("Penalty/ShotAtGoal")
            if shot.get("DistanceToGoal") != "11.00" or shot.find("SuccessfulShot") is None:
                raise ValueError(f"Unexpected shot type for {match}")
            info=ET.fromstring(fetch(spec["mirror"], files["matchinfo"]))
            fixture=next(info.iter("General"))
            length=float(next(info.iter("Environment")).get("PitchX"))
            rows=window(event, fetch(spec["mirror"], files["position"]))
            frames.extend(rows)
            shots.append(dict(match_id=event.get("MatchId"), event_id=event.get("EventId"),
                              home=fixture.get("HomeTeamName"), away=fixture.get("GuestTeamName"),
                              event_time=event.get("EventTime"), result="SuccessfulShot",
                              **gate_reference(rows,length/2)))
    args.out.mkdir(parents=True)
    write_csv(args.out/"frames.csv", frames)
    write_csv(args.out/"shots.csv", shots)
    print(f"{len(spec['matches'])} matches, {len(shots)} penalties, {len(frames)} frame records")


if __name__ == "__main__":
    main()
