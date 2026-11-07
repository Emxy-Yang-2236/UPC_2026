"""Importance-sampling predictor. This module never receives a reference outcome."""
import numpy as np
from flight import early, finish, draw_nuisance, gravity, cell_edges, cell_ids, cell_geometry
from observation_layer import rounded_probability

MASKS = {"origin": (), "first": (0,), "late": (1,), "both": (0,1)}


def posterior_tracks(observations, kind, cfg, n, cap, rng):
    sp, o, p = cfg["sampling"], cfg["official"], cfg["physics"]
    lo, hi = np.array(p["velocity_lo"]), np.array(p["velocity_hi"])
    pv = 1 / np.prod(hi-lo)
    epsilon = cfg["observation"]["quantum_m"]/2
    noise = cfg["observation"].get("tracking_noise")
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
            bias = 0.
            if noise is not None and noise["shared_bias_sigma_m"] > 0:
                bias = rng.normal(0., noise["shared_bias_sigma_m"], size=(count, 3))
            target = observations[latest] - bias
            center = np.broadcast_to((target-r0)/t - .5*t*gravity(cfg),(count,3)).copy()
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
            if noise is None:
                for frame, measurement in observations.items():
                    delta = frames[frame]-measurement
                    accepted &= np.all((delta>=-epsilon)&(delta<epsilon),axis=1)
                likelihood = accepted
            else:
                likelihood = accepted.astype(float)
                for frame, measurement in observations.items():
                    delta = frames[frame] + bias - measurement
                    likelihood *= np.prod(rounded_probability(delta, noise["sigma_m"], epsilon), axis=1)
            weights = np.divide(pv*likelihood,q,out=np.zeros(count),where=q>0)
            r, v = frames[-1], velocities[-1]
        keep = weights>0
        if np.any(keep):
            chunks.append(tuple(a[keep] for a in (weights,r,v,*nuisance)))
    if not chunks:
        return {"n":n,"hits":0,"evidence":0.,"second":0.,"ess":0.}, (np.empty(0,int),np.empty((0,2)),np.empty(0),np.empty(0))
    weights,r,v,*nuisance = (np.concatenate(a) for a in zip(*chunks))
    total, squares = weights.sum(), weights@weights
    normalized = weights / total
    info = {"n":n,"hits":len(weights),"evidence":float(total/n),
            "second":float(squares/n**2),"ess":float(1/(normalized@normalized))}
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


def phase_cases(visible, cfg):
    """Quadrature over a shared release offset, with a uniform bounded prior."""
    width = cfg["observation"].get("release_phase_halfwidth_s", 0.)
    if not np.isfinite(width) or width < 0.:
        raise ValueError("Release phase half-width must be finite and nonnegative")
    if not visible or width == 0.:
        return [(1., cfg)]
    times = np.asarray(cfg["official"]["times"], dtype=float)
    if times[0] <= width:
        raise ValueError("The phase prior must place all input frames after release")
    nodes, weights = np.polynomial.legendre.leggauss(cfg["observation"].get("phase_nodes", 3))
    return [(float(weight/2), dict(cfg, official=dict(cfg["official"], times=times+width*node)))
            for node, weight in zip(nodes, weights)]


def pool_phase_tracks(runs, probabilities):
    infos, tracks = zip(*runs)
    evidence = sum(p*i["evidence"] for p, i in zip(probabilities, infos))
    ess_inverse = sum((p*i["evidence"]/evidence)**2/i["ess"]
                      for p, i in zip(probabilities, infos) if evidence and i["ess"])
    summary = {"n": sum(i["n"] for i in infos), "hits": sum(i["hits"] for i in infos),
               "evidence": evidence, "second": sum(p*p*i["second"] for p, i in zip(probabilities, infos)),
               "ess": 1/ess_inverse if ess_inverse else 0.}
    events, points, arrival, _ = zip(*tracks)
    masses = np.concatenate([p*track[3] for p, track in zip(probabilities, tracks)])
    return summary, (np.concatenate(events), np.concatenate(points), np.concatenate(arrival), masses)


def predict(visible, cfg, seed, official=False):
    sp = cfg["sampling"]
    count = len(cfg["official"]["times"])
    visible = {index: np.asarray(point, dtype=float) for index, point in visible.items()}
    for index, point in visible.items():
        if not isinstance(index, (int, np.integer)) or not 0 <= index < count:
            raise ValueError("Observation index is outside the configured times")
        if point.shape != (3,) or not np.isfinite(point).all():
            raise ValueError("Each observation must contain three finite coordinates")
    n = sp["n_official"] if official else (sp["n_both"] if len(visible)>=2 else sp["n_single"])
    cap=sp["official_cap"] if official else sp["resample_cap"]
    cases = phase_cases(visible, cfg)
    probabilities = [p for p, _ in cases]
    size, extra = divmod(n, len(cases))
    if size < 1 or cap < len(cases):
        raise ValueError("Sampling and resampling budgets must cover all phase cases")
    cap_size, cap_extra = divmod(cap, len(cases))
    infos, tracks=[],[]
    for model, stream in zip(sp["models"],np.random.SeedSequence(seed).spawn(len(sp["models"]))):
        if len(cases) == 1:
            info, samples = posterior_tracks(visible, model, cases[0][1], n, cap, np.random.default_rng(stream))
        else:
            runs = [posterior_tracks(visible, model, case, size+(i<extra), cap_size+(i<cap_extra),
                                     np.random.default_rng(child))
                    for i, ((_, case), child) in enumerate(zip(cases, stream.spawn(len(cases))))]
            info, samples = pool_phase_tracks(runs, probabilities)
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


def prefix_masses(hist, order):
    """Mass accumulated just before each cell is added to the nested region."""
    return np.r_[0., np.cumsum(hist[order])[:-1]]


def region(hist, threshold=.9, calibrated=False):
    if calibrated and threshold>=1: return np.ones(len(hist),bool)
    if hist.sum()==0: return np.zeros(len(hist),bool)
    order=ranking(hist)
    prev=prefix_masses(hist,order)
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
    models=pri*evidence/z if z>0 else np.zeros(len(infos))
    ess_inverse = sum(p*p/i["ess"] for p, i in zip(models, infos) if i["ess"])
    ess = float(1/ess_inverse) if ess_inverse else 0.
    cells=pri @ grid_masses(tracks,edges)
    hist=cells/cells.sum() if cells.sum() else cells
    return {"events": (totals/z).tolist() if z else None,
            "hist":hist.tolist(),"point":centers[np.argmax(hist)].tolist() if hist.sum() else None,
            "mixture_ess":ess,"model_posterior":models.tolist(),"models":infos}
