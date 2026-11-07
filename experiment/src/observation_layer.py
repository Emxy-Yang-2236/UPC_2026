"""Development observation process; parameters require independent calibration."""
import numpy as np


def observe(trajectory, times, rng, *, phase_s=0., bias_m=(0.,0.,0.),
            sigma_m=(0.,0.,0.), correlation=0., quantum_m=.01,
            repeat_probability=0.):
    """One phase and bias per shot; stationary AR(1) tracking error then rounding.

    trajectory(t) must handle the chosen launch or in-flight anchor explicitly.
    A repeated frame is a stale observation, not a second physical position.
    """
    times=np.asarray(times,float)
    sigma=np.asarray(sigma_m,float)
    if quantum_m<=0 or np.any(sigma<0) or not -1<correlation<1 or not 0<=repeat_probability<=1:
        raise ValueError('Invalid observation parameters')
    if times.ndim!=1 or len(times)==0 or np.any(np.diff(times)<=0):
        raise ValueError('Times must increase')
    truth=np.asarray(trajectory(times+phase_s),float)
    if truth.shape!=(len(times),3) or not np.all(np.isfinite(truth)):
        raise ValueError('Expected finite 3D trajectory')
    error=np.empty_like(truth)
    error[0]=rng.normal(size=3)*sigma
    for i in range(1,len(times)):
        error[i]=correlation*error[i-1]+np.sqrt(1-correlation**2)*rng.normal(size=3)*sigma
    recorded=quantum_m*np.floor((truth+np.asarray(bias_m)+error)/quantum_m+.5)
    repeated=np.zeros(len(times),bool)
    for i in range(1,len(times)):
        if rng.random()<repeat_probability:
            recorded[i]=recorded[i-1]
            repeated[i]=True
    return {'xyz_m':recorded,'true_times_s':times+phase_s,'repeated':repeated}


def flags(shot):
    xyz=np.asarray(shot['xyz_m'])
    return {'repeated_adjacent_position':bool(np.any(np.all(np.diff(xyz,axis=0)==0,axis=1))),
            'anchor_away_from_penalty_mark':bool(np.linalg.norm(xyz[0,:2])>.10),
            'release_time_independently_verified':False}
