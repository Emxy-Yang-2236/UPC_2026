"""D04 diagnostics and B04 equal-proposal-budget retrospective comparison."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from observation_layer import observe,flags
from empirical_penalties import prepare,read_table,acceleration_certificate
from predict import predict,summarize,region
from flight import cell_edges,cell_geometry,cell_ids

ROOT=Path(__file__).resolve().parents[2]

def write(path,data):
    path.write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')

def main():
    out=ROOT/'experiment/runs/Z04'
    out.mkdir(exist_ok=False)
    cfg=json.loads((ROOT/'design/settings.json').read_text())
    shots=prepare(read_table(ROOT/'experiment/data/raw/idsse-penalties/frames.csv'))
    diagnostics=[dict(match_id=s['match_id'],**flags(s),original_hard_box=acceleration_certificate(s,cfg)) for s in shots]
    write(out/'input-diagnostics.json',diagnostics)
    # Exact timing, quantization and stale-frame checks, independent of forecasting.
    line=lambda t:np.column_stack([30*t,2*t,1+t])
    obs=observe(line,[.05,.1],np.random.default_rng(1),phase_s=.01,quantum_m=.01)
    assert np.allclose(obs['xyz_m'],line(np.array([.06,.11])))
    repeated=observe(line,[.05,.1],np.random.default_rng(1),repeat_probability=1.)
    assert repeated['repeated'][1] and np.array_equal(repeated['xyz_m'][0],repeated['xyz_m'][1])
    many=observe(lambda t:np.zeros((len(t),3)),np.arange(30000.),np.random.default_rng(3),sigma_m=[.1]*3,correlation=.7,quantum_m=.000001)
    corr=float(np.corrcoef(many['xyz_m'][:-1,0],many['xyz_m'][1:,0])[0,1])
    assert abs(corr-.7)<.025
    write(out/'observation-checks.json',{'shared_phase':True,'single_rounding':True,'stale_frame':True,'synthetic_lag1_correlation':corr,'field_calibrated':False})
    seeds=[74011,74017,74021]
    cfg['sampling']['n_single']=cfg['sampling']['n_both']=2048
    inputs_path=ROOT/'experiment/runs/B03/blind_inputs.json'
    inputs=json.loads(inputs_path.read_text())
    write(out/'config.json',{'settings':cfg,'seeds':seeds,'input_sha256':hashlib.sha256(inputs_path.read_bytes()).hexdigest(),'status':'retrospective on existing B03 set, not fresh holdout'})
    predictions=[]
    for seed in seeds:
        for i,shot in enumerate(inputs):
            for mask,indices in [('late',[1]),('both',[0,1])]:
                info,tracks=predict({j:np.array(shot['xyz'][j]) for j in indices},cfg,[seed,i])
                predictions.append(dict(id=shot['id'],seed=seed,mask=mask,**summarize(info,tracks,cfg)))
        print('completed seed',seed,flush=True)
    (out/'predictions.json.gz').write_bytes(gzip.compress(json.dumps(predictions,allow_nan=False).encode(),mtime=0))
    # Read outcomes only after forecasts are saved.
    truth={x['id']:x for x in json.loads((ROOT/'experiment/runs/B03/blind_reference.json').read_text())}
    edges=cell_edges(cfg)
    _,areas=cell_geometry(edges)
    rows=[]
    for est in predictions:
        ref=truth[est['id']]; hist=np.array(est['hist']); selected=region(hist,.9)
        inside=ref['event']=='in'
        cid=int(cell_ids(np.array(ref['yz'])[None,:],edges)[0]) if inside else None
        rows.append({'id':est['id'],'seed':est['seed'],'mask':est['mask'],'missing':est['events'] is None,'low_ess':est['mixture_ess']<25,'ess':est['mixture_ess'],'point_error_m':float(np.linalg.norm(np.array(est['point'])-ref['yz'])) if inside and est['point'] is not None else None,'inside':inside,'hit':bool(selected[cid]) if inside else None,'area_m2':float(areas[selected].sum()),'brier':float((est['events'][0]-int(inside))**2) if est['events'] else None})
    with (out/'scores.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    result={}
    for mask in ['late','both']:
        a=[r for r in rows if r['mask']==mask]; inside=[r for r in a if r['inside']]
        errors=[r['point_error_m'] for r in a if r['point_error_m'] is not None]
        result[mask]={'predictions':len(a),'unique_shots':48,'seeds':3,'missing':sum(r['missing'] for r in a),'low_ess':sum(r['low_ess'] for r in a),'point_error_n':len(errors),'mean_point_error_m':float(np.mean(errors)),'nominal90_hits':sum(r['hit'] for r in inside),'nominal90_denominator':len(inside),'mean_area_on_in_goal_m2':float(np.mean([r['area_m2'] for r in inside]))}
    differences=[]
    for shot in inputs:
        values=[]
        for seed in seeds:
            pair={r['mask']:r for r in rows if r['id']==shot['id'] and r['seed']==seed}
            if all(pair[m]['point_error_m'] is not None for m in ['late','both']):
                values.append(pair['both']['point_error_m']-pair['late']['point_error_m'])
        if len(values)==len(seeds): differences.append(float(np.mean(values)))
    rng=np.random.default_rng(74039)
    boot=rng.choice(differences,(2000,len(differences))).mean(axis=1)
    result['paired']={'complete_shots':len(differences),'mean_both_minus_late_m':float(np.mean(differences)),'shot_bootstrap95_m':np.quantile(boot,[.025,.975]).tolist(),'unit':'shot after averaging three seeds; no seed pseudoreplication'}
    result['limitations']=['existing synthetic set reused','2048 proposals per model per mask','nominal regions only; no new calibration','observation layer not integrated into posterior; field calibration unavailable']
    write(out/'summary.json',result)
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
