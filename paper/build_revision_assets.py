"""Build the geometry, witness and benchmark assets for the revised paper."""
import csv
import json
import sys

import numpy as np
from build_assets import ROOT, FIGURES, TABLES, write_table
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, str(ROOT/'experiment/src'))
from flight import advance

TEAL, OCHRE, GRAY = '#14687b', '#9b531f', '#58637a'


def save(fig,name):
    fig.savefig(FIGURES/name,metadata={'CreationDate':None,'ModDate':None})
    plt.close(fig)


def draw_geometry(cfg):
    o=cfg['official']
    r=np.array([o['r0'],*o['xyz']])
    fig,(ax,face)=plt.subplots(1,2,figsize=(6.55,2.35),layout='constrained',
                               gridspec_kw={'width_ratios':[1.6,1]})
    ax.axvline(o['gate'],c=GRAY,lw=2)
    ax.axvspan(r[-1,0],o['gate'],color='#e9f2f5')
    ax.plot(r[:,0],r[:,1],'-o',c=TEAL)
    for (x,y,_), label, dy in zip(r, ('Release','50 ms','100 ms'),(-18,10,-20)):
        ax.annotate(label,(x,y),xytext=(2,dy),textcoords='offset points',fontsize=8)
    ax.text(7.0,1.6,'Unobserved flight',ha='center',color=TEAL)
    ax.set(xlim=(-.45,11.65),ylim=(-.9,2.25),xlabel='Downfield, $x$ (m)',ylabel='Lateral, $y$ (m)',
           title='(a) Observations in plan view')
    face.add_patch(Rectangle((-o['half_width'],0),2*o['half_width'],o['height'],
                             fill=False,lw=1.6,ec=GRAY))
    with (ROOT/'report/evidence/grid.csv').open(encoding='utf-8',newline='') as source:
        cells=list(csv.DictReader(source))
    dy=2*o['half_width']/cfg['study']['grid'][0]
    dz=o['height']/cfg['study']['grid'][1]
    for c in cells:
        if c['in_raw_90']=='1':
            face.add_patch(Rectangle((float(c['y_m'])-dy/2,float(c['z_m'])-dz/2),
                                     dy,dz,color=TEAL,alpha=.20))
    peak=max(cells,key=lambda c:float(c['probability']))
    face.scatter(float(peak['y_m']),float(peak['z_m']),c=TEAL,marker='x')
    face.set(xlim=(-4.0,4.0),ylim=(-.22,2.80),aspect='equal',xlabel='$y$ (m)',ylabel='$z$ (m)',
             title='(b) Prediction at $x=11$ m')
    save(fig,'problem-geometry.pdf')


def draw_witness(cfg, pair):
    fig,(a,b)=plt.subplots(1,2,figsize=(6.55,2.45),layout='constrained',
                            gridspec_kw={'width_ratios':[1.3,1]})
    observed=np.array([pair['start_m'],*pair['readings_m']])
    for k,(shot,color) in enumerate(zip(pair['shots'],(TEAL,OCHRE)),1):
        pos=np.array([pair['start_m']],float)
        vel=np.array([shot['velocity0_m_s']])
        nuisance=(np.zeros((1,3)),np.array([shot['kappa_per_m']]),np.array([shot['beta_per_s']]))
        times=np.linspace(0,shot['arrival_s'],401)
        path=[pos[0].copy()]
        for h in np.diff(times):
            dr,vel=advance(vel,nuisance,'S',h,cfg)
            pos=pos+dr
            path.append(pos[0].copy())
        path=np.array(path)
        assert np.max(np.abs(path[-1]-np.r_[11.,shot['goal_yz_m']]))<2e-7
        a.plot(path[:,0],path[:,2],color=color,lw=1.7,label=f'Witness {k}')
        b.scatter(*shot['goal_yz_m'],color=color,s=34,label=f'Witness {k}')
    a.scatter(observed[:,0],observed[:,2],facecolor='white',edgecolor='black',s=26,zorder=3,
              label='Common readings')
    a.axvline(11,c=GRAY,ls=':',lw=1)
    a.set(xlabel='$x$ (m)',ylabel='$z$ (m)',title='(a) Flight and shared inputs',xlim=(-.25,11.4))
    a.legend(loc='lower right',fontsize=7)
    yz=np.array([shot['goal_yz_m'] for shot in pair['shots']])
    b.plot(yz[:,0],yz[:,1],c=GRAY,ls=':')
    b.annotate('8.76 cm',xy=yz.mean(axis=0),xytext=(-47,-4),textcoords='offset points',fontsize=8)
    b.set(xlabel='$y$ (m)',ylabel='$z$ (m)',title='(b) Distinct goal-plane points',
          xlim=(2.50,2.69),ylim=(1.88,2.05),aspect='equal')
    save(fig,'witness-path.pdf')


def coverage_assets(result):
    names={'late':'100 ms only','both':'50 + 100 ms','gravity':'Gravity + radius'}
    targets={.8,.9,.95,1.}
    headline, scores, strata, cuts = [], [], [], []
    fig,axes=plt.subplots(1,2,figsize=(6.55,2.65),layout='constrained',sharey=True)
    for profile,ax in zip(('rounded','tracking'),axes):
        values=result[profile]
        for method,color,marker in zip(names,(GRAY,TEAL,OCHRE),('s','o','^')):
            m=values['metrics'][method]
            curve=m['curve']
            ax.plot([r['area'] for r in curve],[r['hit']/r['n'] for r in curve],
                    color=color,marker=marker,ms=3,lw=1.1,label=names[method])
            q=next(r for r in curve if r['target']==.9)
            ax.scatter(q['area'],q['hit']/q['n'],marker=marker,s=47,fc='white',ec=color,zorder=4)
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
        ax.set(xscale='log',xlim=(.05,22),ylim=(.44,1.027),xlabel='Mean region area (m$^2$)',
               title='(a) Centimetre rounding' if profile=='rounded' else '(b) Tracking noise')
        ax.axhline(.9,color='#999999',ls=':',lw=.8)
        ax.grid(alpha=.22)
    axes[0].set_ylabel('Test coverage among direct entries')
    axes[1].legend(loc='lower right',fontsize=7,frameon=False)
    save(fig,'coverage-frontier.pdf')
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
    FIGURES.mkdir(exist_ok=True)
    TABLES.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':9,'pdf.fonttype':42})
    cfg=json.loads((ROOT/'design/settings.json').read_text())
    draw_geometry(cfg)
    draw_witness(cfg,json.loads((ROOT/'experiment/runs/B01/pair.json').read_text()))
    coverage_assets(json.loads((ROOT/'report/evidence/z09-summary.json').read_text()))
    sensitivity_table(json.loads((ROOT/'report/evidence/plane-sensitivity.json').read_text()))


if __name__=='__main__':
    main()
