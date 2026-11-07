"""Z07 developmental replay of the three native, release-unverified field inputs."""
import argparse
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from empirical_penalties import acceleration_certificate, prepare, read_table
from observation_layer import flags
from predict import predict, summarize

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    base = json.loads((ROOT / 'design/settings.json').read_text())
    source = ROOT / 'experiment/data/raw/idsse-penalties/frames.csv'
    shots = prepare(read_table(source))
    rows = []
    seeds = (77603, 77617)
    for i, shot in enumerate(shots):
        assert shot['status'] == 'ready'
        anchor, *xyz = shot['xyz_m']
        for mode in ('launch_hard', 'airborne_hard', 'airborne_soft'):
            cfg = deepcopy(base)
            cfg['official'].update(r0=anchor, times=shot['times_s'][1:])
            if mode != 'launch_hard':
                cfg['physics']['velocity_lo'][2] = -11.
            if mode == 'airborne_soft':
                cfg['observation']['tracking_noise'] = {'sigma_m': .006, 'shared_bias_sigma_m': .008}
                cfg['sampling']['proposal_halfwidth_m'] = .026
            certificate = acceleration_certificate(shot, cfg)
            for seed in seeds:
                visible = {j: np.asarray(value) for j, value in enumerate(xyz)}
                info, tracks = predict(visible, cfg, [seed, i])
                estimate = summarize(info, tracks, cfg)
                rows.append({'match_id': shot['match_id'], 'event_id': shot['event_id'], 'mode': mode, 'seed': seed,
                             'ess': estimate['mixture_ess'], 'has_event_distribution': estimate['events'] is not None,
                             'has_in_goal_point': estimate['point'] is not None,
                             'hard_box_incompatible': bool(certificate['incompatible_both']), **flags(shot)})
    with (args.out / 'field-diagnostics.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (args.out / 'config.json').write_text(json.dumps({'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'settings': base, 'seeds': seeds, 'airborne_min_vz_m_s': -11.,
        'soft_sigma_m': .006, 'soft_shared_bias_sigma_m': .008, 'soft_proposal_halfwidth_m': .026,
        'interpretation': 'same exact anchor and native timings; conditional development diagnostics only; all lack release verification'},
        indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
