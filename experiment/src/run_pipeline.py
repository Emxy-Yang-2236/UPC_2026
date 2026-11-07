"""Run the frozen B study from any working directory, using a fresh output ID."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

for name in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","VECLIB_MAXIMUM_THREADS","MKL_NUM_THREADS"):
    os.environ[name]="1"

import numpy as np
import scipy
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from controls import check as structural_checks
from evaluate import calibration,evaluate
from flight import cell_edges,cell_geometry
from official import run_official
from predict import MASKS,predict,summarize
from reference import baselines,numerical_checks,synthetic

ROOT=Path(__file__).resolve().parents[2]


def write_json(path,data):
    content=(json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(",",":"))+"\n").encode()
    if path.suffix==".gz": content=gzip.compress(content,mtime=0)
    with path.open("xb") as f: f.write(content)


def read_json(path):
    data=path.read_bytes()
    if path.suffix==".gz": data=gzip.decompress(data)
    return json.loads(data)


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(path,rows):
    with path.open("x",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,list(rows[0]),lineterminator="\n")
        writer.writeheader();writer.writerows(rows)


def shot_forecast(job):
    # This interface accepts an ID, rounded readings and numerical settings only.
    shot,seed,index,cfg=job
    xyz=np.array(shot["xyz"])
    out={"id":shot["id"],"controls":baselines(xyz,cfg)}
    for m,(mask,indices) in enumerate(MASKS.items()):
        if not indices: continue
        visible={j:xyz[j].copy() for j in indices}
        info,tracks=predict(visible,cfg,[seed,701,index,m])
        out[mask]=summarize(info,tracks,cfg)
    return out


def official_figure(path,cfg,output,hist):
    edges=cell_edges(cfg)
    fig,ax=plt.subplots(figsize=(8.4,3.65),layout="constrained")
    image=ax.pcolormesh(*edges,hist.reshape(cfg["study"]["grid"]).T,cmap="Blues",shading="flat")
    fig.colorbar(image,ax=ax,label="Probability per cell, conditional on entry")
    centers,_=cell_geometry(edges)
    from matplotlib.patches import Rectangle
    for i in output["raw_cells"]:
        y,z=centers[i];dy=edges[0][1]-edges[0][0];dz=edges[1][1]-edges[1][0]
        ax.add_patch(Rectangle((y-dy/2,z-dz/2),dy,dz,fill=False,edgecolor="#12615d",linewidth=1))
    if output["point"]: ax.scatter(*output["point"],marker="x",c="#a82226",s=75,label="Nominal mode")
    pair=ROOT/"experiment/runs/B01/pair.json"
    if pair.exists():
        pts=[s["goal_yz_m"] for s in read_json(pair)["shots"]]
        ax.scatter(*np.array(pts).T,edgecolor="black",facecolor="none",s=42,label="Admissible pair")
    ax.set(xlim=(edges[0][0],edges[0][-1]),ylim=(0,edges[1][-1]),xlabel="Lateral coordinate y (m)",
           ylabel="Height z (m)",title="Official two-frame example")
    ax.set_aspect("equal");ax.legend(loc="upper left",fontsize=8)
    fig.savefig(path,dpi=160);plt.close(fig)


def run(path,cfg,workers):
    settings=ROOT/"design/settings.json"
    sources=sorted((ROOT/"experiment/src").glob("*.py"))
    manifest={"status":"running","started_utc":datetime.now(timezone.utc).isoformat(),
              "design_commit":"4ad681dc280c5abfd8b78f01348e1b1620ba00b3",
              "source_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
              "settings_sha256":checksum(settings),"source_sha256":{p.name:checksum(p) for p in sources},
              "python":platform.python_version(),"numpy":np.__version__,"scipy":scipy.__version__,
              "matplotlib":matplotlib.__version__,"machine":platform.machine(),"workers":workers,
              "backend":"CPU float64; one BLAS thread per shot worker",
              "seeds":cfg["study"]["seeds"],"official_seeds":cfg["sampling"]["official_seeds"]}
    write_json(path/"start.json",manifest)
    checks=numerical_checks(cfg)
    write_json(path/"solver_checks.json",checks)
    if not all(r["pass"] for r in checks): raise ValueError("Solver threshold failed; see solver_checks.json")
    controls=structural_checks(cfg)
    write_json(path/"structural_checks.json",controls)
    if not all(controls.values()): raise ValueError("Structural control failed")
    prior=summarize(*predict({},cfg,[71001,211]),cfg)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for split in ("dev","cal","blind"):
            inputs,truth=synthetic(split,cfg)
            write_json(path/(split+"_inputs.json"),inputs)
            write_json(path/(split+"_reference.json"),truth)
            del truth
            premade=read_json(path/(split+"_inputs.json"))
            seed=cfg["study"]["seeds"][split]
            predictions=list(pool.map(shot_forecast,((r,seed,i,cfg) for i,r in enumerate(premade))))
            for row in predictions: row["origin"]=prior
            pred_file=path/(split+"_predictions.json.gz")
            write_json(pred_file,predictions)
            # Hash and seal all forecasts before the scoring stage obtains the reference file.
            write_json(path/(split+"_lock.json"),{"inputs":checksum(path/(split+"_inputs.json")),
                       "prediction_sha256":checksum(pred_file),"source_sha256":manifest["source_sha256"]})
            if split=="dev":
                for row in predictions:
                    for mask in MASKS:
                        events=row[mask]["events"]
                        if events is not None: assert abs(sum(events)-1)<1e-9
                print("V2 development forecasts locked",len(predictions),flush=True)
            elif split=="cal":
                cal=calibration(read_json(pred_file),read_json(path/(split+"_reference.json")),cfg)
                write_json(path/"calibration.json",cal)
                print("V3 calibration locked",cal["both"],flush=True)
            else:
                summary,details=evaluate(read_json(pred_file),read_json(path/(split+"_reference.json")),cal,cfg)
                write_json(path/"blind_summary.json",summary)
                table(path/"blind_scores.csv",details)
                print("V4 blind scores saved",len(predictions),flush=True)
    output,hist,tracks=run_official(cfg,cal)
    output["controls"]=baselines(cfg["official"]["xyz"],cfg)
    write_json(path/"official.json",output)
    centers,_=cell_geometry(cell_edges(cfg))
    table(path/"official_grid.csv",[{"cell":i,"y_m":float(c[0]),"z_m":float(c[1]),"probability":float(h),
          "in_raw_90":int(i in output["raw_cells"]),"in_calibrated":int(i in output["cal_cells"])}
         for i,(c,h) in enumerate(zip(centers,hist))])
    arrays={}
    for model,(e,yz,t,m) in zip(cfg["sampling"]["models"],tracks):
        arrays.update({model+"_event":e,model+"_yz":yz,model+"_time":t,model+"_evidence_mass":m})
    np.savez_compressed(path/"official_tracks.npz",**arrays)
    official_figure(path/"official.png",cfg,output,hist)
    write_json(path/"complete.json",{"status":"completed","end_utc":datetime.now(timezone.utc).isoformat(),
        "sha256":{p.name:checksum(p) for p in sorted(path.iterdir()) if p.is_file()}})
    print("V5 official replicates saved",output["point"],flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--workers",type=int,default=3)
    args=parser.parse_args()
    if args.workers<1: parser.error("--workers must be positive")
    args.out.mkdir(exist_ok=False,parents=True)
    try:
        run(args.out,read_json(ROOT/"design/settings.json"),args.workers)
    except BaseException as error:
        write_json(args.out/"failure.json",{"type":type(error).__name__,"message":str(error)})
        raise


if __name__=="__main__":
    main()
