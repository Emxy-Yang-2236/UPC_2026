"""Plot the frozen blind comparison from its actual score table."""
import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from evaluate import wilson
from predict import MASKS


def draw(source,path):
    with source.open(newline="") as f:
        rows=list(csv.DictReader(f))
    masks=list(MASKS)
    labels=["Origin","+ first","+ late","+ both"]
    x=np.arange(len(masks))
    bymask=[[r for r in rows if r["mask"]==m and r["truth_event"]=="in"] for m in masks]
    fig,axes=plt.subplots(1,3,figsize=(10.9,3.35),layout="constrained")
    c1,c2="#174775","#b45527"
    axes[0].plot(x,[np.mean([float(r["point_error_m"]) for r in b if r["point_error_m"]]) for b in bymask],
                 "o-",color=c1,label="Mean")
    axes[0].plot(x,[np.median([float(r["point_error_m"]) for r in b if r["point_error_m"]]) for b in bymask],
                 "s--",color=c2,label="Median")
    axes[0].set(ylabel="Point error (m)",yscale="log",title="Gate location")
    axes[1].axhline(.9,color=".45",ls=":",lw=1)
    for label,key,color,dx in [("Nominal","raw",c1,-.08),("Calibrated","cal",c2,.08)]:
        n=[len(b) for b in bymask]
        counts=[sum(int(r[key+"_hit"]) for r in b) for b in bymask]
        probs=np.array(counts)/n
        lower,upper=np.array([wilson(h,den) for h,den in zip(counts,n)]).T
        axes[1].errorbar(x+dx,probs,yerr=np.maximum(0,np.vstack([probs-lower,upper-probs])),
                         fmt="o",color=color,capsize=2.5,label=label)
        areas=[np.mean([float(r[key+"_area_m2"]) for r in b]) for b in bymask]
        axes[2].plot(x,areas,"o-" if key=="raw" else "s--",color=color,label=label)
    axes[1].set(ylabel="Fraction covered",ylim=(0.42,1.04),title="Region coverage")
    axes[2].set(ylabel="Mean area (m²)",yscale="log",title="Region size")
    for ax in axes:
        ax.set_xticks(x,labels,rotation=20)
        ax.spines[["right","top"]].set_visible(False)
        ax.legend(frameon=False,fontsize=8)
    fig.savefig(path,dpi=160)
    plt.close(fig)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("scores",type=Path);p.add_argument("output",type=Path)
    args=p.parse_args()
    if args.output.exists(): p.error("Use a new output path.")
    draw(args.scores,args.output)
