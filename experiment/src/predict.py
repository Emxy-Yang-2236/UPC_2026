"""Importance-sampling predictor. This module never receives a reference outcome."""
import numpy as np
from flight import early, finish, draw_nuisance, gravity, cell_edges, cell_ids, cell_geometry

MASKS = {"origin": (), "first": (0,), "late": (1,), "both": (0,1)}


def posterior_tracks(observations, kind, cfg, n, cap, rng):
    sp, o, p = cfg["sampling"], cfg["official"], cfg["physics"]
    lo, hi = np.array(p["velocity_lo"]), np.array(p["velocity_hi"])
    pv = 1 / np.prod(hi-lo)
    epsilon = cfg["observation"]["quantum_m"]/2
    latest = max(observations) if observations else None
    times = o["times"]
    r0 = np.array(o["r0"])
    chunks = []
    for offset in range(0,n,sp["batch"]):
        count = min(n-offset,sp["batch"])
        nuisance = draw_nuisance(rng,count,kind,cfg)
        v_prior = rng.uniform(lo,hi,(count,3))
        if latest is None:
            weights = np.ones(count)
            r = np.broadcast_to(r0, v_prior.shape)
            v = v_prior
            t = 0.
        else:
            t = times[latest]
            target = observations[latest]
            center = np.tile((target-r0)/t - .5*t*gravity(cfg),(count,1))
            for _ in range(sp["inverse_steps"]):
                frames, _, _ = early(center,nuisance,kind,cfg,latest)
                center += (target-frames[-1])/t
            width = sp["proposal_halfwidth_m"]/t
            local = center + rng.uniform(-width,width,(count,3))
            frac = sp["prior_proposal"]
            v0 = np.where((rng.random(count)<frac)[:,None],v_prior,local)
            in_prior = np.all((lo<=v0)&(v0<=hi),axis=1)
            in_local = np.all(np.abs(v0-center)<=width,axis=1)
            q = frac*pv*in_prior + (1-frac)/(2*width)**3*in_local
            frames, velocities, alive = early(v0,nuisance,kind,cfg,latest)
            accepted = in_prior & alive[-1]
            for frame, measurement in observations.items():
                delta = frames[frame]-measurement
                accepted &= np.all((delta>=-epsilon)&(delta<epsilon),axis=1)
            weights = np.divide(pv*accepted,q,out=np.zeros(count),where=q>0)
            r, v = frames[-1], velocities[-1]
        keep = weights>0
        if np.any(keep):
            chunks.append(tuple(a[keep] for a in (weights,r,v,*nuisance)))
    if not chunks:
        return {"n":n,"hits":0,"evidence":0.,"second":0.,"ess":0.}, (np.empty(0,int),np.empty((0,2)),np.empty(0),np.empty(0))
    weights,r,v,*nuisance = (np.concatenate(a) for a in zip(*chunks))
    total, squares = weights.sum(), weights@weights
    info = {"n":n,"hits":len(weights),"evidence":float(total/n),
            "second":float(squares/n**2),"ess":float(total**2/squares)}
    if len(weights)>cap:
        cdf=np.cumsum(weights/total)
        cdf[-1]=1.
        select=np.searchsorted(cdf,(np.arange(cap)+rng.random())/cap,side="right")
        r,v,nuisance=r[select],v[select],tuple(a[select] for a in nuisance)
        masses = np.full(cap,total/(n*cap))
    else:
        masses = weights/n
    event,yz,arrival=finish(r,v,nuisance,kind,cfg,t)
    return info,(event,yz,arrival,masses)


def predict(visible, cfg, seed, official=False):
    sp = cfg["sampling"]
    n = sp["n_official"] if official else (sp["n_both"] if len(visible)==2 else sp["n_single"])
    cap=sp["official_cap"] if official else sp["resample_cap"]
    infos, tracks=[],[]
    for model, stream in zip(sp["models"],np.random.SeedSequence(seed).spawn(3)):
        info,samples=posterior_tracks(visible,model,cfg,n,cap,np.random.default_rng(stream))
        infos.append(info)
        tracks.append(samples)
    return infos,tracks


def grid_masses(tracks,edges):
    count=(len(edges[0])-1)*(len(edges[1])-1)
    rows=[]
    for event,yz,_,masses in tracks:
        inside=event==0
        rows.append(np.bincount(cell_ids(yz[inside],edges),weights=masses[inside],minlength=count))
    return np.array(rows)


def ranking(hist):
    return np.argsort(-hist,kind="stable")


def region(hist, threshold=.9, calibrated=False):
    if calibrated and threshold>=1: return np.ones(len(hist),bool)
    if hist.sum()==0: return np.zeros(len(hist),bool)
    order=ranking(hist)
    prev=np.r_[0., np.cumsum(hist[order])[:-1]]
    selected=np.zeros(len(hist),bool)
    selected[order]=(prev<=threshold if calibrated else prev<threshold)
    return selected


def summarize(infos,tracks,cfg):
    pri=np.array(cfg["sampling"]["prior"])
    edges=cell_edges(cfg)
    centers,_=cell_geometry(edges)
    totals=pri @ np.array([np.bincount(e,weights=m,minlength=4) for e,_,_,m in tracks])
    z=totals.sum()
    evidence=np.array([a["evidence"] for a in infos])
    second=sum(p**2*i["second"] for p,i in zip(pri,infos))
    ess=float(z**2/second) if second else 0.
    models=pri*evidence/z if z>0 else np.zeros(3)
    cells=pri @ grid_masses(tracks,edges)
    hist=cells/cells.sum() if cells.sum() else cells
    return {"events": (totals/z).tolist() if z else None,
            "hist":hist.tolist(),"point":centers[np.argmax(hist)].tolist() if hist.sum() else None,
            "mixture_ess":ess,"model_posterior":models.tolist(),"models":infos}
