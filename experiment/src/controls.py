"""Structural controls before unblinding, independent of the synthetic test set."""
import copy
import numpy as np
from flight import finish,cell_edges,cell_geometry
from predict import summarize,predict,region

def check(cfg):
    o=cfg["official"]
    # All these cases cross the goal or the ground in the same first time step.
    expected=[1,0,2,0]
    r=np.array([[10.99,3.66,1.0],[10.99,3.65999,1.0],[10.95,0,.111],[10.99,0,.12]])
    v=np.array([[10.,0,0.],[10.,0,0.],[10.,0,-1.],[10.,0,-1.]])
    eta=(np.zeros_like(v),np.zeros(len(v)),np.zeros_like(v))
    ev,_,_=finish(r,v,eta,"D",cfg)
    hits={}
    hits["open_boundary_and_event_order"]=ev.tolist()==expected
    empty_info={"n":10,"hits":0,"evidence":0.,"second":0.,"ess":0.}
    blank=(np.array([],dtype=int),np.empty((0,2)),np.empty(0),np.empty(0))
    no=summarize([empty_info]*3,[blank]*3,cfg)
    hits["empty_evidence"]=no["events"] is None and no["point"] is None
    center=np.array([[0.05,.95]])
    infos=[dict(empty_info,evidence=e,second=e*e) for e in [.25,.5,0]]
    tracks=[(np.array([0]),center,np.array([.4]),np.array([.25])),
            (np.array([1]),np.array([[4.,1.]]),np.array([.4]),np.array([.5])),blank]
    mix=summarize(infos,tracks,cfg)
    hits["evidence_denominator"]=bool(np.allclose(mix["events"],[.2,.8,0,0]))
    edges=cell_edges(cfg,shift=True); _,areas=cell_geometry(edges)
    hits["shifted_grid_area"]=bool(np.isclose(areas.sum(),2*o["half_width"]*o["height"]))
    hits["empty_calibrated_full_goal"]=bool(region(np.zeros(300),1,True).all())
    # Holding the late frame fixed while changing only the hidden early frame.
    tiny=copy.deepcopy(cfg);tiny["sampling"]["n_single"]=48
    a=np.array(o["xyz"]);b=a.copy();b[0]+=123
    late_a=summarize(*predict({1:a[1]},tiny,123),tiny)
    late_b=summarize(*predict({1:b[1]},tiny,123),tiny)
    hits["hidden_frame_invariance"]=late_a==late_b
    return hits
