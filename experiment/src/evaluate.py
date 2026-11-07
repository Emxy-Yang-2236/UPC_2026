"""Calibration and paired scoring after predictions have been locked."""
import math
import numpy as np
from flight import cell_edges, cell_ids, cell_geometry
from predict import MASKS, ranking, region


def truth_cell(q,edges):
    return int(cell_ids(np.asarray(q)[None,:],edges)[0])


def calibration(predictions,truth,cfg):
    edges=cell_edges(cfg)
    lookup={row["id"]:row for row in predictions}
    result={}
    for mask in MASKS:
        scores=[]
        for row in truth:
            if row["event"]!="in": continue
            hist=np.array(lookup[row["id"]][mask]["hist"])
            cid=truth_cell(row["yz"],edges)
            if hist[cid]<=0: scores.append(1.); continue
            order=ranking(hist)
            index=int(np.flatnonzero(order==cid)[0])
            scores.append(float(hist[order[:index]].sum()))
        k=math.ceil(cfg["study"]["coverage"]*(len(scores)+1))
        result[mask]={"n":len(scores),"rank":k,"level":float(sorted(scores)[k-1]) if k<=len(scores) else 1.}
    return result


def wilson(hit,n):
    if not n: return None
    z=1.95996398454
    p=hit/n
    center=(p+z*z/(2*n))/(1+z*z/n)
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return [max(0,center-half),min(1,center+half)]


def evaluate(predictions,truth,cal,cfg):
    edges=cell_edges(cfg)
    _,areas=cell_geometry(edges)
    ref={r["id"]:r for r in truth}
    details=[]
    for pred in predictions:
        actual=ref[pred["id"]]
        inside=actual["event"]=="in"
        for mask in MASKS:
            est=pred[mask]; hist=np.array(est["hist"])
            if est["events"] is not None and not np.isclose(sum(est["events"]),1): raise RuntimeError("event mass")
            if hist.sum()>0 and not np.isclose(hist.sum(),1): raise RuntimeError("goal mass")
            nominal=region(hist,cfg["study"]["coverage"])
            calibrated=region(hist,cal[mask]["level"],True)
            cid=truth_cell(actual["yz"],edges) if inside else None
            err=float(np.linalg.norm(np.asarray(est["point"])-actual["yz"])) if inside and est["point"] is not None else None
            event_pred=est["events"][0] if est["events"] is not None else None
            details.append({"id":pred["id"],"family":actual["family"],"truth_event":actual["event"],"mask":mask,
                "ess":est["mixture_ess"],"low_ess":int(est["mixture_ess"]<cfg["study"]["min_ess"]),
                "missing":int(est["events"] is None),"point_error_m":err,
                "brier":(event_pred-int(inside))**2 if event_pred is not None else None,
                "raw_hit":int(nominal[cid]) if inside else None,"cal_hit":int(calibrated[cid]) if inside else None,
                "raw_area_m2":float(areas[nominal].sum()) if inside else None,
                "cal_area_m2":float(areas[calibrated].sum()) if inside else None})
    def values(rows,key):
        return [r[key] for r in rows if r[key] is not None]
    def stat(numbers,method):
        return float(method(numbers)) if len(numbers) else None
    summary={}
    for family in ["all","no_spin","stable_spin","wake"]:
        bymask={}
        for mask in MASKS:
            rows=[r for r in details if r["mask"]==mask and (family=="all" or r["family"]==family)]
            points=values(rows,"point_error_m"); brier=values(rows,"brier")
            item={"shots":len(rows),"in_goal":sum(r["truth_event"]=="in" for r in rows),"point_n":len(points),
                  "mean_point_m":stat(points,np.mean),"median_point_m":stat(points,np.median),"brier_n":len(brier),
                  "brier":stat(brier,np.mean),"brier_upper_if_missing":float((sum(brier)+len(rows)-len(brier))/len(rows)) if rows else None,
                  "low_ess":sum(r["low_ess"] for r in rows),"failed":sum(r["missing"] for r in rows)}
            for name in ("raw","cal"):
                hits=values(rows,name+"_hit")
                item[name]={"hit":sum(hits),"n":len(hits),"wilson95":wilson(sum(hits),len(hits)),
                            "mean_area_m2":stat(values(rows,name+"_area_m2"),np.mean)}
            bymask[mask]=item
        summary[family]=bymask
    paired={}
    rng=np.random.default_rng(cfg["study"]["bootstrap_seed"])
    for metric in ("point_error_m","brier","raw_hit","cal_hit","raw_area_m2","cal_area_m2"):
        vals={}
        for mask in ("late","both"):
            vals[mask]={r["id"]:r[metric] for r in details if r["mask"]==mask and r[metric] is not None}
        ids=sorted(vals["late"].keys() & vals["both"].keys())
        delta=np.array([vals["both"][i]-vals["late"][i] for i in ids])
        if len(delta):
            boot=rng.choice(delta,size=(cfg["study"]["bootstrap_n"],len(delta))).mean(axis=1)
            paired[metric]={"n":len(delta),"mean_both_minus_late":float(delta.mean()),"interval95":np.quantile(boot,[.025,.975]).tolist()}
        else: paired[metric]={"n":0}
    controls={}
    for model in ("gravity","constant_a"):
        errors=[]; brier=[]
        for row in predictions:
            tr=ref[row["id"]]; ctrl=row["controls"][model]
            brier.append((int(ctrl["event"]=="in")-int(tr["event"]=="in"))**2)
            if tr["event"]=="in" and ctrl["point"] is not None:
                errors.append(np.linalg.norm(np.array(ctrl["point"])-tr["yz"]))
        controls[model]={"point_n":len(errors),"median_point_m":stat(errors,np.median),
                         "mean_point_m":stat(errors,np.mean),"event_brier":stat(brier,np.mean)}
    return {"groups":summary,"both_minus_late":paired,"kinematic_controls":controls},details
