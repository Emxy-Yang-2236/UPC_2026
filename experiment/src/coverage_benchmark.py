"""Z09: split calibration and a fresh, equal-budget 100 ms test."""
import argparse
import csv
import gzip
import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from time import perf_counter

import numpy as np

from additional_information import fixed_step_reference
from evaluate import truth_cell, wilson
from flight import cell_edges, cell_geometry
from predict import predict, prefix_masses, ranking, summarize
from reference import baselines, synthetic

ROOT = Path(__file__).resolve().parents[2]
LEVELS = (.50, .60, .70, .80, .85, .90, .95, .975, 1.)
METHODS = ('late', 'both', 'gravity')
PROFILES = ('rounded', 'tracking')
PROPOSALS = 8192
SAMPLE_SEEDS = {'cal': 79003, 'blind': 79009}
NOISE_SEEDS = {'cal': 79019, 'blind': 79031}
INFERENCE_SEEDS = {'cal': 79043, 'blind': 79063}
TRACKING_SIGMA, SHARED_SIGMA = .006, .008


def write_json(path, value):
    path.write_bytes((json.dumps(value, indent=2, allow_nan=False) + '\n').encode())


def prepare(split, cfg):
    exact, truth = synthetic(split, cfg, rounded=False, solver=fixed_step_reference)
    rng = np.random.default_rng(NOISE_SEEDS[split])
    q = cfg['observation']['quantum_m']
    inputs = []
    for row in exact:
        xyz = np.array(row['xyz'])
        offset = rng.normal(0., SHARED_SIGMA, (1, 3))
        noise = rng.normal(0., TRACKING_SIGMA, (2, 3))
        def round_cm(value):
            return (q * np.floor(value/q + .5)).round(8).tolist()
        inputs.append({'id': row['id'], 'rounded': round_cm(xyz),
                       'tracking': round_cm(xyz + offset + noise)})
    return inputs, truth


def forecast(inputs, cfg, split):
    configs = {profile: deepcopy(cfg) for profile in PROFILES}
    tracking = configs['tracking']
    tracking['observation']['tracking_noise'] = {'sigma_m': TRACKING_SIGMA,
                                                  'shared_bias_sigma_m': SHARED_SIGMA}
    tracking['sampling']['proposal_halfwidth_m'] = .026
    records = []
    for i, shot in enumerate(inputs):
        for profile, settings in configs.items():
            xyz = shot[profile]
            for method, mask in [('late', (1,)), ('both', (0, 1))]:
                visible = {j: xyz[j] for j in mask}
                start = perf_counter()
                info, tracks = predict(visible, settings, [INFERENCE_SEEDS[split], i])
                pred = summarize(info, tracks, settings)
                records.append({'id': shot['id'], 'profile': profile, 'method': method,
                                'point': pred['point'], 'hist': pred['hist'],
                                'p': pred['events'][0] if pred['events'] is not None else None,
                                'ess': pred['mixture_ess'], 'elapsed_s': perf_counter()-start})
            start = perf_counter()
            control = baselines(xyz, cfg)['gravity']
            records.append({'id': shot['id'], 'profile': profile, 'method': 'gravity',
                            'point': control['point'], 'p': float(control['event']=='in'),
                            'ess': None, 'elapsed_s': perf_counter()-start})
    return records


def cell_scores(row, centres, diagonal):
    """Nested sets use a rank-prefix score or distance to a ballistic point."""
    if row['method'] == 'gravity':
        if row['point'] is None:
            return np.ones(len(centres))
        # The monotone bounded transform leaves ordering and ties intact.
        distance = np.linalg.norm(centres - row['point'], axis=1)
        return distance / (diagonal + distance)
    hist = np.array(row['hist'])
    order = ranking(hist)
    score = np.ones(len(hist))
    occupied = hist[order] > 0
    score[order[occupied]] = np.minimum(prefix_masses(hist, order)[occupied], 1.)
    return score


def scoring_rows(predictions, truth, edges, centres, areas, cuts=None):
    lookup = {row['id']: row for row in truth}
    diagonal = float(np.hypot(np.ptp(edges[0]), np.ptp(edges[1])))
    rows = []
    for p in predictions:
        actual = lookup[p['id']]
        goal = actual['event'] == 'in'
        q = actual['yz']
        record = {k:p[k] for k in ('id','profile','method','p','ess','elapsed_s')}
        record.update(family=actual['family'], event=actual['event'],
                      edge_m=None, error_m=None, brier=None, score=None)
        if p['p'] is not None:
            record['brier'] = (p['p']-int(goal))**2
        if goal:
            record['edge_m'] = min(q[0]-edges[0][0], edges[0][-1]-q[0],
                                   q[1]-edges[1][0], edges[1][-1]-q[1])
            if p['point'] is not None:
                record['error_m'] = float(np.linalg.norm(np.array(p['point'])-q))
            scores = cell_scores(p, centres, diagonal)
            cid = truth_cell(q, edges)
            record['score'] = float(scores[cid])
            if cuts is not None:
                levels = cuts[(p['profile'],p['method'])]
                for level, threshold in zip(LEVELS, levels):
                    selected = scores <= threshold
                    record[f'hit_{level:g}'] = int(selected[cid])
                    record[f'area_{level:g}'] = float(areas[selected].sum())
        rows.append(record)
    return rows


def calibration(rows):
    cuts = {}
    for profile in PROFILES:
        for method in METHODS:
            values = sorted(r['score'] for r in rows if r['profile']==profile
                            and r['method']==method and r['score'] is not None)
            n = len(values)
            ranks = [math.ceil(level*(n+1)) for level in LEVELS]
            cuts[(profile,method)] = [values[k-1] if k<=n else 1. for k in ranks]
    return cuts


def summarize_group(rows):
    goals = [r for r in rows if r['event']=='in']
    errors = [r['error_m'] for r in goals if r['error_m'] is not None]
    brier = [r['brier'] for r in rows if r['brier'] is not None]
    times = [r['elapsed_s'] for r in rows]
    def mean(values):
        return float(np.mean(values)) if values else None
    curve = []
    for level in LEVELS:
        hits = sum(r[f'hit_{level:g}'] for r in goals)
        curve.append({'target':level,'hit':hits,'n':len(goals),
                      'area':mean([r[f'area_{level:g}'] for r in goals]),
                      'wilson95':wilson(hits,len(goals))})
    return {'shots':len(rows),'goals':len(goals),'point_n':len(errors),
            'mean_error_m':mean(errors),'median_error_m':float(np.median(errors)) if errors else None,
            'brier':mean(brier),'event_n':len(brier),'missing':len(rows)-len(brier),
            'low_ess':sum(r['ess'] is not None and r['ess']<25 for r in rows),
            'elapsed_p50_ms':1000*float(np.median(times)) if times else None,
            'elapsed_p95_ms':1000*float(np.quantile(times,.95)) if times else None,
            'curve':curve}


def paired(rows, baseline, metric):
    groups = [{r['id']:r.get(metric) for r in rows if r['method']==m and r.get(metric) is not None}
              for m in ('both',baseline)]
    first, second = groups
    delta = np.array([first[k]-second[k] for k in sorted(first.keys() & second.keys())])
    if not len(delta):
        return {'n':0}
    draw = np.random.default_rng(79079).choice(delta, (4000,len(delta))).mean(axis=1)
    return {'n':len(delta),'difference':float(delta.mean()),
            'interval95':np.quantile(draw,[.025,.975]).tolist()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    cfg = json.loads((ROOT/'design/settings.json').read_text())
    cfg['study'].update(cal=90,blind=120)
    cfg['study']['seeds'].update(SAMPLE_SEEDS)
    cfg['sampling'].update(n_single=PROPOSALS,n_both=PROPOSALS)
    write_json(args.out/'config.json',{'settings':cfg,'levels':LEVELS,'noise_seeds':NOISE_SEEDS,
               'inference_seeds':INFERENCE_SEEDS,'tracking_sigma_m':TRACKING_SIGMA,
               'shared_sigma_m':SHARED_SIGMA,'deadline_s':.10,'reference_step_s':.001,
               'source_sha256':{name:hashlib.sha256((ROOT/'experiment/src'/name).read_bytes()).hexdigest()
                                for name in ('coverage_benchmark.py','reference.py','predict.py',
                                             'flight.py','observation_layer.py','additional_information.py','evaluate.py')}})
    edges = cell_edges(cfg)
    centres, areas = cell_geometry(edges)
    cuts = None
    for split in ('cal','blind'):
        inputs, truth = prepare(split,cfg)
        write_json(args.out/f'{split}-inputs.json',inputs)
        write_json(args.out/f'{split}-truth.json',truth)
        records = forecast(inputs,cfg,split)
        compressed = gzip.compress(json.dumps(records,allow_nan=False).encode(),mtime=0)
        (args.out/f'{split}-predictions.json.gz').write_bytes(compressed)
        write_json(args.out/f'{split}-lock.json',{'sha256':hashlib.sha256(compressed).hexdigest()})
        rows = scoring_rows(records,truth,edges,centres,areas,cuts)
        if split=='cal':
            cuts = calibration(rows)
            write_json(args.out/'thresholds.json',{f'{p}/{m}':c for (p,m),c in cuts.items()})
        print(split,len(inputs),sum(r['event']=='in' for r in truth),flush=True)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (args.out/'scores.csv').open('w',encoding='utf-8',newline='') as target:
        writer = csv.DictWriter(target,fieldnames=fields,lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    results = {}
    for p in PROFILES:
        pool = [r for r in rows if r['profile']==p]
        results[p] = {'metrics':{m:summarize_group([r for r in pool if r['method']==m]) for m in METHODS},
                      'paired':{m:{key:paired(pool,m,key) for key in ('error_m','brier','hit_0.9','area_0.9')}
                                for m in ('late','gravity')},
                      'strata':{label:{m:summarize_group([r for r in pool if r['method']==m and criterion(r)])
                                      for m in METHODS} for label,criterion in
                                 [('no_spin',lambda r:r['family']=='no_spin'),
                                  ('stable_spin',lambda r:r['family']=='stable_spin'),
                                  ('wake',lambda r:r['family']=='wake'),
                                  ('near_edge',lambda r:r['edge_m'] is not None and r['edge_m']<.244),
                                  ('interior',lambda r:r['edge_m'] is not None and r['edge_m']>=.244)]}}
    write_json(args.out/'summary.json',results)


if __name__ == '__main__':
    main()
