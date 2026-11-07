"""Z06 fresh synthetic comparison of a third frame and observation likelihoods."""
import argparse
from copy import deepcopy
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
from types import SimpleNamespace

import numpy as np

from evaluate import truth_cell
from flight import cell_edges, cell_geometry
from observation_layer import rounded_probability
from predict import predict, prefix_masses, ranking, region, summarize
from reference import baselines, synthetic

ROOT = Path(__file__).resolve().parents[2]
MASKS = {'two_100ms': (0, 1), 'late_pair_150ms': (1, 2), 'three_150ms': (0, 1, 2),
         'noisy_hard': (0, 1), 'noisy_independent': (0, 1), 'noisy_shared': (0, 1)}
SEEDS = (77501, 77507)
SIGMA = .006
SHARED = .008


def fixed_step_reference(v0, acceleration, cfg, dt=.001):
    """Integrate the existing truth force law on a fine mesh with event interpolation."""
    o, p, s = cfg['official'], cfg['physics'], cfg['solver']
    state = np.r_[o['r0'], v0].astype(float)
    times, states = [0.], [state]
    event, point, arrival = 3, None, None

    def rhs(t, x):
        return np.r_[x[3:], acceleration(t, x[3:])]

    while times[-1] < s['horizon'] - 1e-12:
        t = times[-1]
        h = min(dt, s['horizon']-t)
        a = rhs(t, state)
        b = rhs(t+h/2, state+h*a/2)
        c = rhs(t+h/2, state+h*b/2)
        d = rhs(t+h, state+h*c)
        step = h*(a+2*b+2*c+d)/6
        candidate = state+step
        gate = ((o['gate']-state[0])/step[0]
                if state[0] < o['gate'] <= candidate[0] else math.inf)
        floor = ((p['radius']-state[2])/step[2]
                 if state[2] >= p['radius'] >= candidate[2] and step[2] < 0 else math.inf)
        fraction = min(gate, floor)
        if math.isfinite(fraction):
            state = state+fraction*step
            arrival = t+fraction*h
            times.append(arrival)
            states.append(state)
            if floor <= gate:
                event = 2
            else:
                point = state[1:3].tolist()
                event = int(not (abs(point[0]) < o['half_width'] and 0 < point[1] < o['height']))
            break
        state = candidate
        times.append(t+h)
        states.append(state)

    def interpolate(target_times):
        return np.array([np.interp(target_times, times, column) for column in np.asarray(states).T])

    return SimpleNamespace(t=times, sol=interpolate), event, point, arrival


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def inputs_for(split, cfg):
    noise_rng = np.random.default_rng({'cal': 77431, 'blind': 77443}[split])
    exact, references = synthetic(split, cfg, rounded=False, solver=fixed_step_reference)
    quantum = cfg['observation']['quantum_m']

    def quantize(x):
        return (np.floor(x/quantum+.5)*quantum).round(8).tolist()

    inputs = []
    for row in exact:
        positions = np.asarray(row['xyz'])
        noisy = positions + noise_rng.normal(0., SHARED, size=(1, 3)) + noise_rng.normal(0., SIGMA, size=positions.shape)
        inputs.append({'id': row['id'], 'xyz': quantize(positions), 'noisy_xyz': quantize(noisy)})
    return inputs, references


def forecasts(inputs, cfg, seed):
    modes = {name: deepcopy(cfg) for name in MASKS}
    for name, sigma, bias_sigma in [('noisy_independent', math.hypot(SIGMA, SHARED), 0.),
                                  ('noisy_shared', SIGMA, SHARED)]:
        modes[name]['observation']['tracking_noise'] = {'sigma_m': sigma, 'shared_bias_sigma_m': bias_sigma}
        modes[name]['sampling']['proposal_halfwidth_m'] = .026
    gravity_cfg = deepcopy(cfg)
    gravity_cfg['official']['times'] = cfg['official']['times'][:2]
    rows = []
    for index, shot in enumerate(inputs):
        for name, frames in MASKS.items():
            xyz = shot['noisy_xyz'] if name.startswith('noisy') else shot['xyz']
            visible = {i: np.asarray(xyz[i]) for i in frames}
            info, tracks = predict(visible, modes[name], [seed, index])
            estimate = summarize(info, tracks, modes[name])
            rows.append(dict(id=shot['id'], seed=seed, method=name, **estimate))
        gravity = baselines(shot['noisy_xyz'][:2], gravity_cfg)['gravity']
        rows.append(dict(id=shot['id'], seed=seed, method='noisy_gravity', **gravity))
    return rows


def calibrate(predictions, truth, edges):
    levels = {}
    for seed in SEEDS:
        for name in MASKS:
            scores = []
            for row in predictions:
                if row['seed'] != seed or row['method'] != name or truth[row['id']]['event'] != 'in':
                    continue
                hist = np.asarray(row['hist'])
                cell = truth_cell(truth[row['id']]['yz'], edges)
                order = ranking(hist)
                location = int(np.flatnonzero(order == cell)[0])
                scores.append(float(prefix_masses(hist, order)[location]) if hist[cell] > 0 else 1.)
            rank = math.ceil(.9 * (len(scores) + 1))
            levels[(seed, name)] = {'level': sorted(scores)[rank-1] if rank <= len(scores) else 1.,
                                    'calibration_in_goal': len(scores), 'rank': rank}
    return levels


def score(predictions, truth, edges, levels):
    _, areas = cell_geometry(edges)
    rows = []
    for row in predictions:
        ref = truth[row['id']]
        inside = ref['event'] == 'in'
        probability = None
        if row['method'] == 'noisy_gravity':
            probability = float(row['event'] == 'in')
        elif row['events'] is not None:
            probability = row['events'][0]
        point_error = (float(np.linalg.norm(np.asarray(row['point']) - ref['yz']))
                       if inside and row['point'] is not None else None)
        raw_hit = raw_area = adjusted_hit = adjusted_area = None
        if inside and row['method'] in MASKS:
            hist = np.asarray(row['hist'])
            cell = truth_cell(ref['yz'], edges)
            raw = region(hist, .9)
            adjusted = region(hist, levels[(row['seed'], row['method'])]['level'], True)
            raw_hit, adjusted_hit = int(raw[cell]), int(adjusted[cell])
            raw_area, adjusted_area = float(areas[raw].sum()), float(areas[adjusted].sum())
        deadline = .15 if row['method'].endswith('150ms') else .10
        rows.append({'id': row['id'], 'seed': row['seed'], 'method': row['method'], 'family': ref['family'],
                     'event': ref['event'], 'deadline_s': deadline,
                     'time_to_goal_s': ref['T'] - deadline if inside else None,
                     'missing_event': probability is None, 'low_ess': row.get('mixture_ess', 25) < 25,
                     'point_error_m': point_error, 'brier': (probability-inside)**2 if probability is not None else None,
                     'raw_hit': raw_hit, 'cal_hit': adjusted_hit, 'raw_area_m2': raw_area, 'cal_area_m2': adjusted_area})
    return rows


def summarize_scores(rows):
    def values(group, key):
        return [r[key] for r in group if r[key] is not None]

    results = {}
    for name in (*MASKS, 'noisy_gravity'):
        group = [r for r in rows if r['method'] == name]
        result = {'attempts': len(group), 'unique_shots': len({r['id'] for r in group}),
                  'in_goal_shots': len({r['id'] for r in group if r['event'] == 'in'}),
                  'missing_event': sum(r['missing_event'] for r in group), 'low_ess': sum(r['low_ess'] for r in group)}
        for key in ('point_error_m', 'brier', 'raw_area_m2', 'cal_area_m2', 'time_to_goal_s'):
            v = values(group, key)
            result[key] = {'n': len(v), 'mean': float(np.mean(v)) if v else None}
        for key in ('raw_hit', 'cal_hit'):
            v = values(group, key)
            result[key] = {'n': len(v), 'hit': sum(v)}
        results[name] = result
    return results


def paired(rows, comparison, baseline):
    points = {(r['id'], r['seed'], r['method']): r['point_error_m'] for r in rows}
    shot_differences = []
    for shot in sorted({r['id'] for r in rows}):
        pairs = [(points[(shot, seed, comparison)], points[(shot, seed, baseline)]) for seed in SEEDS]
        if all(a is not None and b is not None for a, b in pairs):
            shot_differences.append(float(np.mean([a-b for a, b in pairs])))
    if not shot_differences:
        return {'complete_shots': 0}
    rng = np.random.default_rng(77579)
    means = rng.choice(shot_differences, (2000, len(shot_differences))).mean(axis=1)
    return {'complete_shots': len(shot_differences), 'mean_difference_m': float(np.mean(shot_differences)),
            'shot_bootstrap95_m': np.quantile(means, [.025, .975]).tolist()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cfg = json.loads((ROOT / 'design/settings.json').read_text())
    cfg['official']['times'] = [.05, .10, .15]
    cfg['study']['seeds'].update(cal=77401, blind=77407)
    cfg['sampling'].update(n_single=8192, n_both=8192)
    dump(args.out / 'config.json', {'settings': cfg, 'masks': MASKS, 'predict_seeds': SEEDS,
         'noise_tracking_sigma_m': SIGMA, 'noise_shared_sigma_m': SHARED, 'noise_seeds': [77431, 77443],
         'python': platform.python_version(), 'numpy': np.__version__, 'reference_step_s': .001})
    assert float(rounded_probability(0., .006, .005)) > float(rounded_probability(.02, .006, .005)) > 0.
    # Verify the local reference integrator against frozen DOP853 outcomes.
    historical = json.loads((ROOT / 'design/settings.json').read_text())
    _, checks = synthetic('blind', historical, solver=fixed_step_reference)
    frozen = json.loads((ROOT / 'experiment/runs/B03/blind_reference.json').read_text())
    assert all(a['id'] == b['id'] and a['event'] == b['event'] for a, b in zip(checks, frozen))
    max_point = max(float(np.linalg.norm(np.asarray(a['yz'])-b['yz'])) for a, b in zip(checks, frozen) if a['yz'] is not None)
    max_time = max(abs(a['T']-b['T']) for a, b in zip(checks, frozen) if a['T'] is not None)
    assert max_point < .0001 and max_time < .0001
    dump(args.out / 'reference-check.json', {'checked_shots': len(checks), 'all_event_types_match': True,
         'max_goal_difference_m': max_point, 'max_event_time_difference_s': max_time})
    edges = cell_edges(cfg)
    for split in ('cal', 'blind'):
        inputs, truth = inputs_for(split, cfg)
        dump(args.out / f'{split}-inputs.json', inputs)
        dump(args.out / f'{split}-truth.json', truth)
        locked = []
        for seed in SEEDS:
            locked.extend(forecasts(inputs, cfg, seed))
            print(split, seed, len(locked), flush=True)
        pred_path = args.out / f'{split}-predictions.json.gz'
        pred_path.write_bytes(gzip.compress(json.dumps(locked, allow_nan=False).encode(), mtime=0))
        dump(args.out / f'{split}-lock.json', {'sha256': hashlib.sha256(pred_path.read_bytes()).hexdigest()})
        truth = {row['id']: row for row in truth}
        if split == 'cal':
            levels = calibrate(locked, truth, edges)
            dump(args.out / 'calibration.json', [{'seed': seed, 'method': name, **record}
                 for (seed, name), record in levels.items()])
        else:
            rows = score(locked, truth, edges, levels)
    with (args.out / 'scores.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    comparisons = [('three_150ms', 'two_100ms'), ('late_pair_150ms', 'two_100ms'),
                   ('three_150ms', 'late_pair_150ms'), ('noisy_shared', 'noisy_hard'),
                   ('noisy_shared', 'noisy_independent'), ('noisy_shared', 'noisy_gravity')]
    dump(args.out / 'summary.json', {'metrics': summarize_scores(rows),
        'paired_point_error': {f'{a}_minus_{b}': paired(rows, a, b) for a, b in comparisons}})


if __name__ == '__main__':
    main()
