"""Local timing and position sensitivity of the constant-acceleration control."""
import argparse
import itertools
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def fit_and_cross(readings, origin, h, gate):
    u1, u2 = (readings - origin) / h
    a = (u2 - 2*u1) / h
    v = u1 - h*a/2
    disc = v[0]**2 + 2*a[0]*(gate-origin[0])
    if disc <= 0 or v[0]+np.sqrt(disc) <= 0:
        raise ValueError('no transversal forward plane crossing')
    t = 2*(gate-origin[0])/(v[0]+np.sqrt(disc))
    p = origin + v*t + a*t*t/2
    return t, p[1:], v, a


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    o = json.loads((ROOT/'design/settings.json').read_text())['official']
    origin, readings = np.array(o['r0']), np.array(o['xyz'])
    h, gate = o['times'][0], o['gate']
    assert o['times'][1]==2*h
    t,q,v,a = fit_and_cross(readings,origin,h,gate)
    speed = v + t*a
    projection = np.column_stack((-speed[1:]/speed[0],np.eye(2)))
    s=t/h
    weights=np.array([s*(2-s),s*(s-1)/2])
    derivative_pos=np.concatenate([w*projection for w in weights],axis=1)
    derivative_phase=projection @ (weights @ (v + np.outer([h,2*h],a)))
    def shift(tau):
        times = np.array(o['times'])[:,None] + tau
        return origin+times*v+times**2*a/2
    step=1e-6
    plus=fit_and_cross(shift(step),origin,h,gate)[1]
    minus=fit_and_cross(shift(-step),origin,h,gate)[1]
    assert np.allclose((plus-minus)/(2*step),derivative_phase,atol=2e-5,rtol=0)
    corners=np.array(list(itertools.product((-1.,1.),repeat=6))).reshape(-1,2,3)
    grid=[]
    for tau in (0., .001, .003):
        for halfwidth in (0.,.0025,.005,.010):
            observed=[]
            missing=0
            shifts = halfwidth*corners if halfwidth else np.zeros((1,2,3))
            for phase in sorted({-tau,0.,tau}):
                for position_error in shifts:
                    try:
                        observed.append(fit_and_cross(shift(phase)+position_error,origin,h,gate)[1]-q)
                    except ValueError:
                        missing += 1
            linear=np.abs(derivative_pos).sum(axis=1)*halfwidth+np.abs(derivative_phase)*tau
            grid.append({'phase_bound_ms':tau*1000,'coordinate_bound_mm':halfwidth*1000,
                         'linear_axis_max_m':linear.tolist(),
                         'trials':len(observed)+missing,'no_crossing':missing,
                         'tested_axis_max_m':np.max(np.abs(observed),axis=0).tolist(),
                         'tested_max_distance_m':float(np.max(np.linalg.norm(observed,axis=1)))})
    result={'scope':'constant acceleration control; first forward plane root; local sensitivity',
            'time_s':t,'point_m':q.tolist(),'launch_m_s':v.tolist(),'acceleration_m_s2':a.tolist(),
            'weights':weights.tolist(),'position_jacobian':derivative_pos.tolist(),
            'phase_derivative_m_s':derivative_phase.tolist(),'scenarios':grid}
    args.out.write_bytes((json.dumps(result,indent=2,allow_nan=False)+'\n').encode())


if __name__ == '__main__':
    main()
