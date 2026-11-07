"""Conditional mechanism/refitting checks; ranges are exploratory, not measured."""
import json
import platform
from pathlib import Path
import numpy as np
from baseline_checks import OBS, R0, G, aerodynamic_fit

ROOT = Path(__file__).resolve().parent

def rhs(t, state, p, wind_y=0., alpha=0., tau=None):
    v = state[3:]
    u = v - np.array([0., wind_y, 0.])
    speed = np.linalg.norm(u)
    k = p[3] * (speed / 30.)**alpha
    beta = np.array([0., p[4], p[5]])
    if tau is not None:
        beta *= np.exp(-t/tau)
    return np.r_[v, [0., 0., -G]] + np.r_[np.zeros(3), -k*speed*u + np.cross(beta, u)]

def step(t, s, p, dt, cfg):
    a = rhs(t, s, p, **cfg)
    b = rhs(t+dt/2, s+dt*a/2, p, **cfg)
    c = rhs(t+dt/2, s+dt*b/2, p, **cfg)
    d = rhs(t+dt, s+dt*c, p, **cfg)
    return s+dt*(a+2*b+2*c+d)/6

def observations(p, cfg, dt=.001):
    s = np.r_[R0, p[:3]]
    out = []
    n = round(.05/dt)
    dt = .05/n
    for i in range(2*n):
        s = step(i*dt, s, p, dt, cfg)
        if (i+1) % n == 0:
            out.append(s[:3].copy())
    return np.array(out)

def fit(p, cfg):
    p = p.copy()
    for _ in range(16):
        r = (observations(p, cfg)-OBS).ravel()
        if np.max(np.abs(r)) < 1e-9:
            return p
        j = np.empty((6,6))
        for k in range(6):
            eps = 1e-5 if k<3 else 1e-6
            a,b = p.copy(),p.copy()
            a[k] += eps
            b[k] -= eps
            j[:,k] = ((observations(a,cfg)-observations(b,cfg))/(2*eps)).ravel()
        delta = np.linalg.solve(j,-r)
        for scale in [1.,.5,.25,.125,.0625,.03125]:
            candidate=p+scale*delta
            if candidate[3]>0 and np.linalg.norm(observations(candidate,cfg)-OBS)<np.linalg.norm(r):
                p=candidate
                break
        else:
            raise RuntimeError('No improving step')
    raise RuntimeError('Fit failed')

def goal(p,cfg,dt):
    s=np.r_[R0,p[:3]]
    for i in range(round(1/dt)):
        nxt=step(i*dt,s,p,dt,cfg)
        if nxt[0]>=11:
            f=(11-s[0])/(nxt[0]-s[0])
            cross=s+f*(nxt-s)
            return i*dt+f*dt,cross
        if nxt[2]<.11 and nxt[5]<0:
            raise RuntimeError('Ground before goal')
        s=nxt
    raise RuntimeError('No crossing')

def quadratic_goal(times):
    mat=np.column_stack([times,.5*times**2])
    v,a=np.linalg.solve(mat,OBS-R0)
    t=22/(v[0]+np.sqrt(v[0]**2+22*a[0]))
    return (R0+v*t+.5*a*t*t)[1:]

def main():
    p0,_=aerodynamic_fit()
    # Independent physical limits and uniform-clock invariance.
    p_free = np.r_[p0[:3], 0., 0., 0.]
    t_free, state_free = goal(p_free, {}, .00025)
    t_exact = 11/p_free[0]
    expected = R0+p_free[:3]*t_exact+np.array([0.,0.,-.5*G*t_exact*t_exact])
    free_error = float(np.linalg.norm(state_free[:3]-expected))
    assert free_error < 1e-6
    sample = np.r_[R0, p0[:3]]
    acceleration = rhs(0.,sample,p0)[3:]
    energy_residual = float(np.dot(sample[3:],acceleration)+G*sample[5]+p0[3]*np.linalg.norm(sample[3:])**3)
    assert abs(energy_residual) < 1e-10
    cases=[('baseline',{}),('crosswind_minus_2',{'wind_y':-2.}),('crosswind_plus_2',{'wind_y':2.}),('coefficient_power_minus_1',{'alpha':-1.}),('coefficient_power_plus_1',{'alpha':1.}),('effective_lift_decay_40s',{'tau':40.}),('effective_lift_decay_1s',{'tau':1.}),('effective_lift_decay_02s',{'tau':.2})]
    results=[]
    for name,cfg in cases:
        p=fit(p0,cfg)
        t,s=goal(p,cfg,.0005)
        tf,sf=goal(p,cfg,.00025)
        residual=float(np.max(np.abs(observations(p,cfg,.0005)-OBS)))
        difference=float(np.linalg.norm(s[1:3]-sf[1:3]))
        assert residual<1e-7 and difference<1e-5
        results.append({'name':name,'config':cfg,'parameters_v0xyz_kappaRef_betaYZ':p.tolist(),'goal_yz_m':sf[1:3].tolist(),'goal_time_s':tf,'refined_observation_residual_m':residual,'step_difference_m':difference,'goal_velocity_m_s':sf[3:].tolist()})
    baseline=np.array(results[0]['goal_yz_m'])
    for r in results:
        r['shift_from_refitted_baseline_m']=float(np.linalg.norm(np.array(r['goal_yz_m'])-baseline))
    times=np.array([.05,.10])
    j=np.empty((2,2))
    for k in range(2):
        a,b=times.copy(),times.copy()
        a[k]+=1e-6
        b[k]-=1e-6
        j[:,k]=(quadratic_goal(a)-quadratic_goal(b))/2e-6
    sigma=.001
    clock_invariance = float(np.linalg.norm(quadratic_goal(times*1.01)-quadratic_goal(times)))
    assert clock_invariance < 1e-10
    timing={'interpretation':'Quadratic model only. Fixed exact positions, independent 1 ms timestamp uncertainty, exact kick time. Local linear propagation, not total prediction error.','goal_jacobian_m_per_s':j.tolist(),'linear_std_yz_m':(sigma*np.sqrt(np.sum(j*j,axis=1))).tolist(),'common_frame_offset_sensitivity_yz_m_per_s':np.sum(j,axis=1).tolist()}
    result={'status':'conditional toy-model mechanism checks, not new empirical measurements or a posterior probability calculation','environment':{'python':platform.python_version(),'numpy':np.__version__},'ranges':'wind +/-2 m/s, coefficient power +/-1, effective beta e-fold times 40, 1 and .2 s are chosen scenarios, not calibrated football ranges; strong beta decay is not measured spin decay','fixed_assumptions':'beta_x=0 in every scenario; six refitted parameters, exact two observed positions; constant wind; no bounce','physical_checks':{'zero_force_limit_endpoint_error_m':free_error,'no_wind_energy_identity_residual':energy_residual,'quadratic_common_clock_scale_1_01_endpoint_difference_m':clock_invariance},'scenarios':results,'timing':timing}
    (ROOT/'extension_check_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
