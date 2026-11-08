"""Generate Z09 coverage and plane-event tables from frozen results."""
import json

from build_assets import ROOT, TABLES, write_table


def coverage_assets(result):
    names={'late':'100 ms only','both':'50 + 100 ms','gravity':'Gravity + radius'}
    targets={.8,.9,.95,1.}
    headline, scores, strata, cuts = [], [], [], []
    for profile in ('rounded','tracking'):
        values=result[profile]
        for method in names:
            m=values['metrics'][method]
            curve=m['curve']
            q=next(r for r in curve if r['target']==.9)
            headline.append([profile,names[method],f"{q['hit']}/{q['n']}",f"{q['area']:.3f}",
                             f"{m['mean_error_m']:.3f}",f"{m['brier']:.3f}"])
            scores.append([profile,names[method],f"{m['point_n']}/{m['goals']}",
                           f"{m['event_n']}/{m['shots']}",str(m['low_ess']),
                           f"{m['elapsed_p50_ms']:.1f}",f"{m['elapsed_p95_ms']:.1f}"])
            for row in curve:
                if row['target'] in targets:
                    cuts.append([profile,names[method],f"{100*row['target']:.0f}",
                                 f"{row['hit']}/{row['n']}",f"{row['area']:.3f}"])
        for key,group in values['strata'].items():
            row=[profile,key.replace('_',' '),str(group['both']['goals'])]
            for m in names:
                x=group[m]
                stat=next(r for r in x['curve'] if r['target']==.9)
                row += [f"{stat['hit']}/{stat['n']}"]
            strata.append(row)
    for name,rows in [('coverage-main.tex',headline),('coverage-runtime.tex',scores),
                      ('coverage-strata.tex',strata),('coverage-targets.tex',cuts)]:
        write_table(name,rows)


def sensitivity_table(result):
    rows=[]
    for r in result['scenarios']:
        rows.append([f"{r['phase_bound_ms']:g}",f"{r['coordinate_bound_mm']:g}",
                     f"{r['linear_axis_max_m'][0]:.3f}",f"{r['linear_axis_max_m'][1]:.3f}",
                     f"{r['tested_max_distance_m']:.3f}",f"{r['no_crossing']}/{r['trials']}"])
    write_table('plane-sensitivity.tex',rows)


def spin_tables(evidence):
    exchange = json.loads((evidence / 'z10-cross-calibration.json').read_text())
    lookup = {(r['test'], r['calibration'], r['method']): r for r in exchange}
    rows = []
    for test in ('Z09', 'Z10'):
        for calibration in ('Z09', 'Z10'):
            aero, gravity = (lookup[test, calibration, m] for m in ('aero', 'gravity'))
            rows.append([test, calibration, *[f"{r['hits']}/{r['goals']}" for r in (aero, gravity)],
                         *[f"{r['mean_area_m2']:.3f}" for r in (aero, gravity)]])
    write_table('threshold-exchange.tex', rows)

    summary = json.loads((evidence / 'z10-summary.json').read_text())
    lookup = {(r['profile'], r['family']): r for r in summary['groups']
              if r['method'] == 'nominal' and r['calibration'] == 'pooled'}
    rows = []
    for profile, label in [('rounded', 'Rounding'), ('tracking', 'Tracking + rounding')]:
        groups = [lookup[profile, f] for f in ('all', 'stable_spin', 'wake')]
        all_kicks = groups[0]
        rows.append([label, *[f"{r['hits']}/{r['goals']}" for r in groups],
                     f"{all_kicks['mean_area_m2']:.3f}", f"{all_kicks['mean_point_error_m']:.3f}"])
    write_table('spin-profiles.tex', rows)


def control_tables(evidence):
    data = json.loads((evidence / 'revision-controls.json').read_text())
    rows = []
    for r in data['prescribed_scenarios']:
        rows.append(['Tracking + rounding' if r['tracking'] else 'Rounding',
                     r'Uniform $\pm1$ ms' if r['phase_halfwidth_ms'] else 'Exact',
                     str(r['region_cells']), f"{r['area_m2']:.3f}", f"{100*r['p_direct']:.1f}",
                     f"{r['median_and_central90_ms'][1]:.1f}"])
    write_table('joint-observation.tex', rows)
    rows = []
    for key, r in data['retrospective'].items():
        study, profile = key.split('/')
        metrics = r['mean_point_error_aero_centroid_gravity_m'] + r['brier_aero_binary_soft']
        rows.append([study, 'Rounding' if profile == 'rounded' else 'Tracking',
                     *[f"{value:.3f}" for value in metrics]])
    write_table('decision-controls.tex', rows)


def calibration_robustness_table(evidence):
    result = json.loads((evidence / 'z11-summary.json').read_text())
    rows = []
    for key, label in (('nominal','Nominal'), ('S_half','S only'), ('E_half','E only'),
                       ('both_half','S and E')):
        r = result['stable_spin_prior'][key]
        rows.append([label, f"{r['mean_error_m']:.3f}", f"{r['mean_true_rank']:.2f}",
                     f"{r['fixed_nominal_hits']}/{r['goals']}"])
    write_table('separate-lift-priors.tex', rows)


def main():
    TABLES.mkdir(exist_ok=True)
    evidence = ROOT / 'report/evidence'
    coverage_assets(json.loads((evidence / 'z09-summary.json').read_text()))
    sensitivity_table(json.loads((evidence / 'plane-sensitivity.json').read_text()))
    spin_tables(evidence)
    control_tables(evidence)
    calibration_robustness_table(evidence)


if __name__=='__main__':
    main()
