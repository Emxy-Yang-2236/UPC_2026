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


def main():
    TABLES.mkdir(exist_ok=True)
    coverage_assets(json.loads((ROOT/'report/evidence/z09-summary.json').read_text()))
    sensitivity_table(json.loads((ROOT/'report/evidence/plane-sensitivity.json').read_text()))


if __name__=='__main__':
    main()
