"""Official application, prior envelope and grid/Monte Carlo sensitivity."""
import numpy as np
from flight import cell_edges,cell_ids,cell_geometry
from predict import grid_masses,region,summarize,predict


def prior_envelope(mass,area,centers,limits):
    intercept=(.2*mass[0]+.8*mass[1])/area
    slope=.8*(mass[2]-mass[1])/area
    peak=max(np.max(np.abs(intercept)),np.max(np.abs(slope)),1e-250)
    intercept=intercept/peak; slope=slope/peak
    result=[]
    for i in range(len(area)):
        if np.all(mass[:,i]==0): continue
        b=intercept[i]-intercept; a=slope[i]-slope
        if np.any((a==0)&(b<0)): continue
        lo,hi=limits
        if np.any(a>0): lo=max(lo,float(np.max(-b[a>0]/a[a>0])))
        if np.any(a<0): hi=min(hi,float(np.min(-b[a<0]/a[a<0])))
        if hi-lo>1e-12:
            mid=(lo+hi)/2
            if int(np.argmax(intercept+slope*mid))==i:
                result.append({"cell":i,"point":centers[i].tolist(),"pi_from":lo,"pi_to":hi})
    return sorted(result,key=lambda row:row["pi_from"])


def run_official(cfg,cal):
    sp=cfg["sampling"]; base=cell_edges(cfg); centers,areas=cell_geometry(base)
    visible={i:np.array(row) for i,row in enumerate(cfg["official"]["xyz"])}
    runs=[predict(visible,cfg,seed,True) for seed in sp["official_seeds"]]
    results=[summarize(info,tr,cfg) for info,tr in runs]
    alltracks=[]; infos=[]
    for k in range(3):
        a,b=[r[0][k] for r in runs]
        evidence=(a["evidence"]+b["evidence"])/2
        second=(a["second"]+b["second"])/4
        infos.append({"n":a["n"]+b["n"],"hits":a["hits"]+b["hits"],"evidence":evidence,
                      "second":second,"ess":evidence**2/second if second else 0.})
        chunks=[r[1][k] for r in runs]
        e,yz,t,wt=[np.concatenate(a) for a in zip(*chunks)]
        alltracks.append((e,yz,t,wt/2))
    pooled=summarize(infos,alltracks,cfg)
    hist=np.array(pooled["hist"]); raw=region(hist,cfg["study"]["coverage"])
    adjusted=region(hist,cal["both"]["level"],True)
    modes={}; env=prior_envelope(grid_masses(alltracks,base),areas,centers,sp["spin_fraction_range"])
    for label,edges in [("base",base),("fine",cell_edges(cfg,[60,20])),("shift",cell_edges(cfg,shift=True))]:
        c,ar=cell_geometry(edges)
        mass=np.array(sp["prior"])@grid_masses(alltracks,edges)
        modes[label]=c[np.argmax(mass/ar)].tolist() if mass.sum()>0 else None
    quant=None
    weights=np.concatenate([sp["prior"][i]*m[e==0] for i,(e,_,t,m) in enumerate(alltracks)])
    time=np.concatenate([t[e==0] for e,_,t,_ in alltracks])
    if len(time):
        order=np.argsort(time); cw=np.cumsum(weights[order]); cw/=cw[-1]
        quant=time[order][np.searchsorted(cw,[.05,.5,.95])].tolist()
    points=[r["point"] for r in results]+list(modes.values())+[r["point"] for r in env]
    ess_ok=(pooled["mixture_ess"]>=cfg["study"]["official_min_ess"] and all(
        m["ess"]>=cfg["study"]["min_ess"] or post<.1 for m,post in zip(infos,pooled["model_posterior"])))
    stable=ess_ok and bool(env) and all(point is not None for point in points) and len(set(cell_ids(np.array(points),base)))==1
    output={"events":pooled["events"],"point":pooled["point"],"model_posterior":pooled["model_posterior"],
            "models":infos,"mixture_ess":pooled["mixture_ess"],"ess_pass":bool(ess_ok),
            "raw_cells":np.flatnonzero(raw).tolist(),"raw_area_m2":float(areas[raw].sum()),
            "raw_mass":float(hist[raw].sum()),"cal_area_m2":float(areas[adjusted].sum()),
            "cal_cells":np.flatnonzero(adjusted).tolist(),"gate_time_q05_q50_q95_s":quant,
            "prior_envelope":env,"grid_modes":modes,"stable_single_hotspot":bool(stable),
            "replicates":[{k:v for k,v in row.items() if k!="hist"} for row in results]}
    return output,hist,alltracks
