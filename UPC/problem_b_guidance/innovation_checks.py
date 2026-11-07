"""Checks supporting proposed innovations; all physical examples are conditional.

Uses the earlier effective constant-beta force law, not a measured spin law.
The beta_x family is a feasibility witness, not a global maximum search.
"""
import json
from pathlib import Path
import numpy as np
from baseline_checks import R0, OBS, G, aerodynamic_fit

ROOT = Path(__file__).resolve().parent


def rhs(s, p, bx):
    v = s[3:]
    return np.r_[v, np.array([0., 0., -G]) - p[3] * np.linalg.norm(v) * v + np.cross([bx, p[4], p[5]], v)]


def rk4(s, p, bx, dt):
    k1 = rhs(s, p, bx)
    k2 = rhs(s + dt*k1/2, p, bx)
    k3 = rhs(s + dt*k2/2, p, bx)
    k4 = rhs(s + dt*k3, p, bx)
    return s + dt*(k1+2*k2+2*k3+k4)/6


def at_times(p, bx, dt=.001):
    s = np.r_[R0, p[:3]]
    positions = []
    for _ in range(4):
        n = round(.05/dt)
        for _ in range(n):
            s = rk4(s,p,bx,.05/n)
        positions.append(s[:3].copy())
    return np.array(positions)


def fit_for_bx(bx, initial):
    p=initial.copy()
    for _ in range(12):
        residual=(at_times(p,bx)[:2]-OBS).ravel()
        if np.linalg.norm(residual)<1e-10:
            return p
        j=np.empty((6,6))
        for k in range(6):
            eps=1e-5 if k<3 else 1e-6
            plus,minus=p.copy(),p.copy()
            plus[k]+=eps
            minus[k]-=eps
            j[:,k]=((at_times(plus,bx)[:2]-at_times(minus,bx)[:2])/(2*eps)).ravel()
        step=np.linalg.solve(j,-residual)
        for factor in [1.,.5,.25,.125,.0625]:
            candidate=p+factor*step
            if candidate[3]>0 and np.linalg.norm(at_times(candidate,bx)[:2]-OBS)<np.linalg.norm(residual):
                p=candidate
                break
        else:
            raise RuntimeError('No improving Newton step')
    raise RuntimeError('No convergence')


def crossing(p,bx,dt):
    s=np.r_[R0,p[:3]]
    for i in range(round(2/dt)):
        nxt=rk4(s,p,bx,dt)
        if nxt[0]>=11:
            u=(11-s[0])/(nxt[0]-s[0])
            return i*dt+u*dt,(s+u*(nxt-s))[1:3]
        if nxt[2]<R0[2] and nxt[5]<0:
            raise RuntimeError('Ground before crossing')
        s=nxt
    raise RuntimeError('No crossing')


def main():
    x1,y1=OBS[0,:2]
    x2,y2=OBS[1,:2]
    e_min=(y1*x2-y2*x1)/(y1+x2+y2+x1)
    p0,_=aerodynamic_fit()
    family=[]
    for bx in [-.5,-.25,0.,.25,.5]:
        p=fit_for_bx(bx,p0)
        t,q=crossing(p,bx,.0005)
        tf,qf=crossing(p,bx,.00025)
        residual=np.max(np.abs(at_times(p,bx)[:2]-OBS))
        assert residual<1e-8
        assert np.linalg.norm(q-qf)<1e-5
        family.append({'beta_x_per_s':bx,'parameters_v0xyz_kappa_beta_yz':p.tolist(),'beta_norm_per_s':float(np.linalg.norm([bx,p[4],p[5]])),'maximum_observation_residual_m':float(residual),'goal_time_s':float(tf),'goal_yz_m':qf.tolist(),'positions_at_005_010_015_020_s':at_times(p,bx,.0005).tolist()})
    pair=max(((i,j) for i in range(len(family)) for j in range(i+1,len(family))),key=lambda ij:np.linalg.norm(np.array(family[ij[0]]['goal_yz_m'])-np.array(family[ij[1]]['goal_yz_m'])))
    d=np.linalg.norm(np.array(family[pair[0]]['goal_yz_m'])-np.array(family[pair[1]]['goal_yz_m']))
    result={'horizontal_diagnostic':{'exact_initial_horizontal_origin':True,'error_bound_applies_to_each_x_and_y_at_two_observations':True,'determinant_m2':float(x1*y2-y1*x2),'minimum_per_coordinate_bound_m':float(e_min),'at_5mm_slope_intervals':[[float((y1-.005)/(x1+.005)),float((y1+.005)/(x1-.005))],[float((y2-.005)/(x2+.005)),float((y2+.005)/(x2-.005))]]},'twin_family':family,'largest_separation_among_five_searched_models':{'family_indices':list(pair),'separation_m':float(d),'conditional_minimax_point_error_lower_bound_m':float(d/2)},'interpretation':'Witnesses under constant effective-beta model, zero wind, exact early positions, kappa>0; not measured spin and not globally optimal twins.'}
    # Purely illustrative short-time force scale, not a measured force.
    result['force_scale_example']={'mass_kg':.43,'density_kg_m3':1.2,'radius_m':.11,'speed_m_s':30.,'side_force_coefficient':.1,'remaining_time_s':.3,'constant_acceleration_shift_m':float(.5*(.5*1.2*np.pi*.11**2*30**2*.1/.43)*.3**2),'meaning':'Constant speed and side acceleration magnitude example; not an uncertainty standard deviation.'}
    (ROOT/'innovation_check_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
