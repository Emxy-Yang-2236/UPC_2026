"""Z08 model-based capture design for independent field validation."""
import argparse
from copy import deepcopy
import csv
from dataclasses import asdict, dataclass, replace
import gzip
import hashlib
import json
from pathlib import Path
import platform

import numpy as np

from additional_information import fixed_step_reference
from flight import cell_edges, cell_geometry, cell_ids
from observation_layer import observe
from predict import predict, region, summarize
from reference import synthetic

ROOT = Path(__file__).resolve().parents[2]
DEADLINES = np.array([.05, .10])
MAX_AGE = .010
SEEDS = (78101, 78121)


@dataclass(frozen=True)
class Camera:
    name: str
    fps: int
    latency_s: float = .002
    drop_probability: float = 0.
    release_error_s: float = .001
    tracking_sigma_m: float = .003
    shared_sigma_m: float = .003
    infer_release_offset: bool = True


def profiles():
    reference = Camera('240hz', 240)
    phase3 = replace(reference, name='phase3ms', release_error_s=.003)
    return [Camera('ideal', 0, 0., 0., 0., 0., 0.),
            replace(reference, name='25hz', fps=25), replace(reference, name='60hz', fps=60),
            replace(reference, name='120hz', fps=120), reference,
            replace(reference, name='latency6ms', latency_s=.006),
            replace(reference, name='drop5pct', drop_probability=.05),
            replace(phase3, name='phase3ms_fixed', infer_release_offset=False), phase3,
            replace(reference, name='phase5ms', release_error_s=.005),
            replace(reference, name='tracking6mm', tracking_sigma_m=.006),
            replace(reference, name='tracking12mm', tracking_sigma_m=.012),
            replace(reference, name='shared8mm', shared_sigma_m=.008)]


def causal_frames(exposures, received, keep, earliest_release):
    """Use the newest distinct native frames available by each deadline."""
    indices = []
    for deadline in DEADLINES:
        available = np.flatnonzero(keep & (received <= deadline + 1e-12)
                                   & (exposures > earliest_release)
                                   & (exposures >= deadline-MAX_AGE-1e-12))
        if not len(available):
            return [], f'missing_or_stale_at_{round(deadline*1000)}ms'
        index = int(available[-1])
        if indices and index <= indices[-1]:
            return [], 'same_frame_twice'
        indices.append(index)
    return indices, 'ready'


def input_for(shot, times, camera, index):
    clock, losses, tracking = [np.random.default_rng(s) for s in np.random.SeedSequence([78019, index]).spawn(3)]
    phase = (2*clock.random()-1)*camera.release_error_s
    if camera.fps:
        frame_phase = clock.random()
        exposures = (np.arange(int(camera.fps*DEADLINES[-1])+2)+frame_phase)/camera.fps
        received = exposures + camera.latency_s
        keep = losses.random(len(exposures)) >= camera.drop_probability
    else:
        exposures = DEADLINES.copy()
        received = exposures.copy()
        keep = np.ones(len(exposures), dtype=bool)
    indices, status = causal_frames(exposures, received, keep, camera.release_error_s)
    row = {'id': shot['id'], 'profile': camera.name, 'status': status}
    if not indices:
        return row

    native = exposures[indices]
    points = np.asarray(shot['xyz'])

    def trajectory(t):
        if t[0] <= 0 or t[-1] > times[-1]:
            raise ValueError('Requested frame is outside the synthetic trajectory')
        return np.column_stack([np.interp(t, times, values) for values in points.T])

    measurement = observe(trajectory, native, tracking, phase_s=phase,
                          bias_m=tracking.normal(0., camera.shared_sigma_m, 3),
                          sigma_m=[camera.tracking_sigma_m]*3)
    row.update(times_s=native.tolist(), received_s=received[indices].tolist(),
               max_age_s=float(max(DEADLINES-native)), xyz_m=measurement['xyz_m'].tolist())
    return row


def forecast(row, camera, cfg, seed, index, areas):
    local = dict(cfg, official=dict(cfg['official'], times=row['times_s']))
    observation = dict(cfg['observation'])
    sampling = dict(cfg['sampling'])
    if camera.tracking_sigma_m:
        observation['tracking_noise'] = {'sigma_m': camera.tracking_sigma_m,
                                         'shared_bias_sigma_m': camera.shared_sigma_m}
        sampling['proposal_halfwidth_m'] = max(.007, .005 + 3*camera.tracking_sigma_m)
    if camera.infer_release_offset:
        observation['release_phase_halfwidth_s'] = camera.release_error_s
        observation['phase_nodes'] = 5 if camera.release_error_s <= .003 else 7
    local.update(observation=observation, sampling=sampling)
    infos, tracks = predict(dict(enumerate(row['xyz_m'])), local, [seed, index])
    result = summarize(infos, tracks, local)
    selected = region(np.asarray(result['hist']), .9)
    return {'point': result['point'], 'ess': result['mixture_ess'],
            'event_available': result['events'] is not None, 'p_in': result['events'][0] if result['events'] else None,
            'area_m2': float(areas[selected].sum()) if selected.any() else None,
            'cells': np.flatnonzero(selected).tolist()}


def score(rows, truth, edges):
    output = []
    for row in rows:
        shot = truth[row['id']]
        goal = shot['event'] == 'in'
        target = cell_ids(np.asarray([shot['yz']]), edges)[0] if goal else None
        point = row.get('point')
        output.append({'profile': row['profile'], 'id': row['id'], 'seed': row['seed'], 'truth_event': shot['event'],
                       'input_status': row['input_status'], 'max_age_ms': row['max_age_ms'],
                       'event_available': row.get('event_available', False), 'ess': row.get('ess', 0.),
                       'point_error_m': float(np.linalg.norm(np.array(point)-shot['yz'])) if goal and point is not None else None,
                       'nominal90_hit': int(target in row.get('cells', [])) if goal else None,
                       'area_m2': row.get('area_m2') if goal else None})
    return output


def summarize_scores(rows):
    ready = [r for r in rows if r['input_status'] == 'ready']
    attempts = len(rows)
    ages = [r['max_age_ms'] for r in ready]
    errors = [r['point_error_m'] for r in rows if r['point_error_m'] is not None]
    hits = [r['nominal90_hit'] for r in rows if r['nominal90_hit'] is not None]
    areas = [r['area_m2'] for r in rows if r['area_m2'] is not None]
    unique = len({r['id'] for r in rows})
    unique_ready = len({r['id'] for r in ready})
    return {'input_ready': unique_ready, 'shots': unique, 'attempts': attempts,
            'max_input_age_ms': max(ages) if ages else None, 'p95_input_age_ms': float(np.quantile(ages, .95)) if ages else None,
            'event_estimates': sum(r['event_available'] for r in rows),
            'ess25_estimates': sum(r['event_available'] and r['ess'] >= 25 for r in rows),
            'goal_point_n': len(errors), 'point_error_mean_m': float(np.mean(errors)) if errors else None,
            'nominal90_hits': sum(hits), 'nominal90_goal_n': len(hits),
            'mean_region_area_m2': float(np.mean(areas)) if areas else None}


def csv_table(path, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def dump(path, data):
    if path.suffix == '.gz':
        payload = json.dumps(data, allow_nan=False, separators=(',', ':')).encode('utf-8')
        path.write_bytes(gzip.compress(payload, mtime=0))
    else:
        path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cfg = json.loads((ROOT / 'design/settings.json').read_text())
    cfg['sampling']['n_both'] = 8192
    truth_cfg = deepcopy(cfg)
    truth_cfg['study']['seeds']['blind'] = 78007
    times = np.arange(106)*.001
    truth_cfg['official']['times'] = times.tolist()
    shots, truth = synthetic('blind', truth_cfg, rounded=False, solver=fixed_step_reference)
    cameras = profiles()
    dump(args.out / 'config.json', {'settings': cfg, 'profiles': [asdict(c) for c in cameras], 'seeds': SEEDS,
         'truth_seed': 78007, 'camera_seed': 78019, 'max_age_s': MAX_AGE, 'deadlines_s': DEADLINES.tolist(),
         'python': platform.python_version(), 'numpy': np.__version__, 'reference_step_s': .001})
    dump(args.out / 'reference.json', truth)
    edges = cell_edges(cfg)
    _, areas = cell_geometry(edges)
    inputs, predictions = [], []
    for camera in cameras:
        for index, shot in enumerate(shots):
            row = input_for(shot, times, camera, index)
            inputs.append(row)
            for seed in SEEDS:
                estimate = forecast(row, camera, cfg, seed, index, areas) if row['status'] == 'ready' else {}
                predictions.append({'profile': camera.name, 'id': row['id'], 'seed': seed,
                                    'input_status': row['status'], 'max_age_ms': row.get('max_age_s', 0)*1000 if estimate else None,
                                    **estimate})
        print(camera.name, sum(r['status'] == 'ready' for r in inputs if r['profile'] == camera.name), flush=True)
    dump(args.out / 'inputs.json.gz', inputs)
    pred = args.out / 'predictions.json.gz'
    dump(pred, predictions)
    dump(args.out / 'lock.json', {'prediction_sha256': hashlib.sha256(pred.read_bytes()).hexdigest()})
    scores = score(predictions, {shot['id']: shot for shot in truth}, edges)
    csv_table(args.out / 'scores.csv', scores)
    summary = [dict(profile=camera.name, **summarize_scores([r for r in scores if r['profile'] == camera.name]))
               for camera in cameras]
    csv_table(args.out / 'feedback.csv', summary)


if __name__ == '__main__':
    main()
