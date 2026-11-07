"""Z05 official-case sensitivity. Refit to the same readings in each scenario."""
import argparse
from copy import deepcopy
import csv
import json
from pathlib import Path
import platform

import numpy as np

from official import run_official

ROOT = Path(__file__).resolve().parents[2]


def scenarios(base):
    yield 'reference', deepcopy(base)
    for name, section, key, value in [
        ('box_2p5mm', 'observation', 'quantum_m', .005),
        ('box_10mm', 'observation', 'quantum_m', .020),
        ('phase_minus1ms', 'official', 'times', [.049, .099]),
        ('phase_plus1ms', 'official', 'times', [.051, .101]),
        ('phase_minus5ms', 'official', 'times', [.045, .095]),
        ('phase_plus5ms', 'official', 'times', [.055, .105]),
        ('zero_wind', 'physics', 'wind_cap', 0.),
        ('half_spin_beta', 'physics', 'beta_cap', .4),
        ('half_spin_omega', 'physics', 'omega_cap', 32.5),
        ('mass_410g', 'physics', 'mass', .410),
        ('mass_450g', 'physics', 'mass', .450),
        ('spin_model_S', 'sampling', 'prior', [0., 1., 0.]),
        ('spin_model_E', 'sampling', 'prior', [0., 0., 1.]),
    ]:
        cfg = deepcopy(base)
        cfg[section][key] = value
        if key == 'quantum_m':
            cfg['sampling']['proposal_halfwidth_m'] = max(.007, value / 2 + .002)
        yield name, cfg
    cfg = deepcopy(base)
    cfg['observation']['tracking_noise'] = {'sigma_m': .006, 'shared_bias_sigma_m': .008}
    cfg['sampling']['proposal_halfwidth_m'] = .026
    yield 'tracking_noise', cfg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    base = json.loads((ROOT / 'design/settings.json').read_text())
    rows, details = [], {}
    for name, cfg in scenarios(base):
        result, _, tracks = run_official(cfg, {'both': {'level': .9}})
        # Unbinned mean of the gate points conditional on the in-goal event.
        points = np.concatenate([yz[e == 0] for e, yz, _, _ in tracks])
        masses = np.concatenate([p*m[e == 0] for p, (e, _, _, m) in zip(cfg['sampling']['prior'], tracks)])
        center = np.average(points, axis=0, weights=masses) if masses.sum() else None
        if not rows:
            baseline = center
        y, z = center.tolist() if center is not None else (None, None)
        mode_y, mode_z = result['point'] or (None, None)
        time = result['gate_time_q05_q50_q95_s'] or (None, None, None)
        row = {'scenario': name, 'mean_y_m': y, 'mean_z_m': z,
               'shift_from_reference_m': float(np.linalg.norm(center-baseline)) if center is not None else None,
               'mode_y_m': mode_y, 'mode_z_m': mode_z,
               'region90_m2': result['raw_area_m2'] if center is not None else None,
               'p_in': result['events'][0] if result['events'] is not None else None,
               'time_q05_s': time[0], 'time_median_s': time[1], 'time_q95_s': time[2],
               'mixture_ess': result['mixture_ess'], 'ess_pass': result['ess_pass']}
        rows.append(row)
        details[name] = {'config': cfg, 'grid_modes': result['grid_modes'],
                         'per_seed': [{'point': s['point'], 'ess': s['mixture_ess']} for s in result['replicates']],
                         'model_posterior': result['model_posterior'], 'gate_events': result['events']}
        print(name, row['shift_from_reference_m'], row['ess_pass'], flush=True)
    reference = json.loads((ROOT / 'experiment/runs/B03/official.json').read_text())
    assert np.allclose([rows[0]['mode_y_m'], rows[0]['mode_z_m']], reference['point'])
    assert abs(rows[0]['region90_m2'] - reference['raw_area_m2']) < 1e-10
    with (args.out / 'factors.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (args.out / 'scenarios.json').write_text(json.dumps({'python': platform.python_version(),
        'numpy': np.__version__, 'scenarios': details}, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
