"""Reconstruct the supplement's headline comparisons from its exported tables."""
import csv
import json
from math import isclose
from pathlib import Path
from statistics import mean

EVIDENCE = Path(__file__).resolve().parent / 'evidence'


def read_csv(name):
    with (EVIDENCE / name).open(encoding='utf-8', newline='') as source:
        return list(csv.DictReader(source))


def main():
    factors = {row['scenario']: row for row in read_csv('z05-factors.csv')}
    assert isclose(float(factors['reference']['region90_m2']), .357216, abs_tol=1e-10)
    assert factors['phase_minus5ms']['p_in'] == factors['phase_plus5ms']['p_in'] == ''
    rows = read_csv('z06-scores.csv')
    expected = json.loads((EVIDENCE / 'z06-summary.json').read_text(encoding='utf-8'))
    for method, metric in expected['metrics'].items():
        scores = [row for row in rows if row['method'] == method]
        assert len(scores) == metric['attempts']
        assert len({r['id'] for r in scores}) == metric['unique_shots']
        assert sum(r['missing_event'] == 'True' for r in scores) == metric['missing_event']
        for name in ('raw_hit', 'cal_hit'):
            hits = [int(r[name]) for r in scores if r[name] != '']
            assert (sum(hits), len(hits)) == (metric[name]['hit'], metric[name]['n'])
        for name in ('point_error_m', 'raw_area_m2', 'cal_area_m2', 'brier', 'time_to_goal_s'):
            values = [float(r[name]) for r in scores if r[name] != '']
            assert len(values) == metric[name]['n']
            if values:
                assert isclose(mean(values), metric[name]['mean'], abs_tol=1e-12)
    two = expected['metrics']['two_100ms']['time_to_goal_s']['mean']
    three = expected['metrics']['three_150ms']['time_to_goal_s']['mean']
    assert isclose(two-three, .05, abs_tol=1e-12)
    field = read_csv('z07-field-diagnostics.csv')
    assert len(field) == 18
    assert all(row['release_time_independently_verified'] == 'False' for row in field)
    for mode, events in [('launch_hard', 0), ('airborne_hard', 2), ('airborne_soft', 2)]:
        assert sum(r['mode'] == mode and r['has_event_distribution'] == 'True' for r in field) == events
    print(json.dumps({'status': 'pass', 'factor_scenarios': len(factors), 'score_rows': len(rows),
                      'field_diagnostic_rows': len(field), 'waiting_cost_s': two-three}))


if __name__ == '__main__':
    main()
