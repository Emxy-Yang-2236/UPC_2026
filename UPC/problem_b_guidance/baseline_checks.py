"""Reproducible checks for the Problem B report-planning guide.

Only NumPy is required. Noise levels and aerodynamic simplifications below
are illustrative assumptions, not measurements of the supplied kick.
"""
from pathlib import Path
import json
import numpy as np

ROOT = Path(__file__).resolve().parent
G = 9.81
H = 0.05
R0 = np.array([0., 0., .11])
OBS = np.array([[1.50, .45, .44], [2.96, .86, .74]])
TIMES = np.array([H, 2 * H])
SEED = 20261107


def ballistic_fit(obs):
    corrected = obs - R0
    corrected = corrected.copy()
    corrected[..., 2] += .5 * G * TIMES**2
    return np.sum(corrected * TIMES[:, None], axis=-2) / np.sum(TIMES**2)


def ballistic_endpoint(v):
    t = 11. / v[..., 0]
    q = np.stack([v[..., 1] * t, R0[2] + v[..., 2] * t - .5 * G * t**2], axis=-1)
    return t, q


def quadratic_fit(obs):
    v0 = (4 * obs[..., 0, :] - obs[..., 1, :] - 3 * R0) / (2 * H)
    a = (obs[..., 1, :] - 2 * obs[..., 0, :] + R0) / H**2
    return v0, a


def quadratic_endpoint(v, a):
    disc = v[..., 0]**2 + 22 * a[..., 0]
    # Stable first positive crossing formula; other roots/events must be checked.
    t = np.where(disc >= 0, 22 / (v[..., 0] + np.sqrt(np.maximum(disc, 0))), np.nan)
    forward = (v[..., 0] + a[..., 0] * t) > 0
    t = np.where(forward & (t > .1), t, np.nan)
    q = R0[1:] + v[..., 1:] * t[..., None] + .5 * a[..., 1:] * t[..., None]**2
    return t, q


def numerical_jacobian(fn, values, eps=1e-6):
    flat = values.flatten()
    jac = np.empty((2, len(flat)))
    for j in range(len(flat)):
        plus, minus = flat.copy(), flat.copy()
        plus[j] += eps
        minus[j] -= eps
        jac[:, j] = (fn(plus.reshape(values.shape)) - fn(minus.reshape(values.shape))) / (2 * eps)
    return jac


def rhs(state, p):
    v = state[3:]
    beta = np.array([0., p[4], p[5]])
    acceleration = np.array([0., 0., -G]) - p[3] * np.linalg.norm(v) * v + np.cross(beta, v)
    return np.r_[v, acceleration]


def rk4(state, p, dt):
    k1 = rhs(state, p)
    k2 = rhs(state + dt * k1 / 2, p)
    k3 = rhs(state + dt * k2 / 2, p)
    k4 = rhs(state + dt * k3, p)
    return state + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6


def aerodynamic_observations(p, dt=.001):
    state = np.r_[R0, p[:3]]
    result = []
    for end in TIMES:
        n = round(H / dt)
        for _ in range(n):
            state = rk4(state, p, H / n)
        result.append(state[:3].copy())
    return np.array(result)


def aerodynamic_fit():
    # Six parameters and six observed coordinates: exact fit has no residual df.
    # beta_x = 0, zero wind and constant k/beta are explicit assumptions.
    p = np.array([30.4, 9.4, 6.9, .02, -.06, -.36])
    trace = []
    for _ in range(15):
        residual = (aerodynamic_observations(p) - OBS).ravel()
        trace.append(float(np.linalg.norm(residual)))
        if trace[-1] < 1e-11:
            break
        jac = np.empty((6, 6))
        for j in range(6):
            eps = 1e-5 if j < 3 else 1e-6
            plus, minus = p.copy(), p.copy()
            plus[j] += eps
            minus[j] -= eps
            jac[:, j] = ((aerodynamic_observations(plus) - aerodynamic_observations(minus)) / (2 * eps)).ravel()
        delta = np.linalg.solve(jac, -residual)
        scale = 1.
        for _ in range(15):
            candidate = p + scale * delta
            if candidate[3] > 0 and np.linalg.norm(aerodynamic_observations(candidate) - OBS) < trace[-1]:
                p = candidate
                break
            scale /= 2
        else:
            raise RuntimeError('Newton line search failed')
    if np.max(np.abs(aerodynamic_observations(p) - OBS)) > 1e-8:
        raise RuntimeError('Aerodynamic fitting residual too large')
    return p, trace


def aerodynamic_goal(p, dt):
    state = np.r_[R0, p[:3]]
    t = 0.
    for _ in range(round(2 / dt)):
        nxt = rk4(state, p, dt)
        if nxt[0] >= 11:
            fraction = (11 - state[0]) / (nxt[0] - state[0])
            crossing = state + fraction * (nxt - state)
            return t + fraction * dt, crossing
        if nxt[2] < R0[2] and nxt[5] < 0:
            raise RuntimeError('Ground contact before goal plane')
        state, t = nxt, t + dt
    raise RuntimeError('No goal-plane crossing')


def main():
    v1 = ballistic_fit(OBS)
    t1, q1 = ballistic_endpoint(v1)
    v2, a2 = quadratic_fit(OBS)
    t2, q2 = quadratic_endpoint(v2, a2)
    predictions = R0 + TIMES[:, None] * v1
    predictions[:, 2] -= .5 * G * TIMES**2
    result = {
        'assumptions': {'r0_exact': True, 'times_exact': True, 'noise': 'independent Gaussian per observed coordinate, only where stated', 'seed': SEED},
        'ballistic': {'v0_m_s': v1.tolist(), 't_goal_s': float(t1), 'goal_yz_m': q1.tolist(), 'residual_observed_minus_predicted_m': (OBS - predictions).tolist(), 'sse_m2': float(np.sum((OBS - predictions)**2))},
        'quadratic': {'v0_m_s': v2.tolist(), 'a_m_s2': a2.tolist(), 't_goal_s': float(t2), 'goal_yz_m': q2.tolist()},
    }
    rng = np.random.default_rng(SEED)
    uncertainty = []
    for label, fit, endpoint in [('ballistic', lambda o: (ballistic_fit(o),), ballistic_endpoint), ('quadratic', quadratic_fit, quadratic_endpoint)]:
        fn = lambda o: endpoint(*fit(o))[1]
        jac = numerical_jacobian(fn, OBS)
        for sigma in [.002, .005, .01, .02]:
            cov = sigma**2 * jac @ jac.T
            simulated_obs = OBS + rng.normal(0, sigma, (20000, 2, 3))
            ts, qs = endpoint(*fit(simulated_obs))
            valid = np.isfinite(ts) & np.all(np.isfinite(qs), axis=-1)
            # These samples propagate an assumed input distribution around the
            # supplied values; they are not a coverage validation experiment.
            uncertainty.append({'model': label, 'assumed_sigma_m': sigma, 'N': 20000, 'no_forward_crossing_fraction': float(1 - np.mean(valid)), 'linear_std_yz_m': np.sqrt(np.diag(cov)).tolist(), 'linear_correlation': float(cov[0, 1] / np.sqrt(cov[0, 0] * cov[1, 1])), 'mc_std_yz_m_conditional_on_crossing': np.std(qs[valid], axis=0, ddof=1).tolist(), 'mc_marginal_2_5_97_5_percentiles_conditional_on_crossing': np.quantile(qs[valid], [.025, .975], axis=0).tolist(), 'plane_crossing_outside_point_goal_fraction_among_crossings': float(np.mean((np.abs(qs[valid, 0]) >= 3.66) | (qs[valid, 1] <= 0) | (qs[valid, 1] >= 2.44)))})
    result['conditional_uncertainty_examples'] = uncertainty
    mid_v = (OBS[1] - R0) / (2 * H)
    non_gravity_a = a2 - np.array([0, 0, -G])
    k_local = -np.dot(non_gravity_a, mid_v) / np.linalg.norm(mid_v)**3
    beta_local = np.cross(mid_v, non_gravity_a) / np.dot(mid_v, mid_v)
    result['local_aerodynamic_initial_guess'] = {'v_mid_m_s': mid_v.tolist(), 'k_per_m': float(k_local), 'beta_minimum_norm_per_s': beta_local.tolist(), 'Cd_if_mass_0_43kg_radius_0_11m_density_1_2kg_m3': float(2 * .43 * k_local / (1.2 * np.pi * .11**2))}
    p, trace = aerodynamic_fit()
    convergence = []
    for dt in [.001, .0005, .00025]:
        t, state = aerodynamic_goal(p, dt)
        convergence.append({'dt_s': dt, 't_goal_s': float(t), 'goal_yz_m': state[1:3].tolist()})
    energy_0 = .5 * np.dot(p[:3], p[:3]) + G * R0[2]
    state = np.r_[R0, p[:3]]
    max_energy_increment = -float('inf')
    for _ in range(1600):
        nxt = rk4(state, p, .00025)
        e0 = .5 * np.dot(state[3:], state[3:]) + G * state[2]
        e1 = .5 * np.dot(nxt[3:], nxt[3:]) + G * nxt[2]
        max_energy_increment = max(max_energy_increment, e1 - e0)
        state = nxt
    result['aerodynamic_illustrative_restricted_fit'] = {'status': 'computed illustrative conditional model; not validated against an independent trajectory', 'assumptions': ['constant k and beta', 'zero wind', 'beta_x=0', 'six free parameters for six measured coordinates'], 'parameter_order': ['v0_x_m_s', 'v0_y_m_s', 'v0_z_m_s', 'k_per_m', 'beta_y_per_s', 'beta_z_per_s'], 'parameters': p.tolist(), 'residual_l2_trace_m': trace, 'convergence': convergence, 'maximum_energy_increment_per_step_m2_s2': float(max_energy_increment)}
    # Independent analytic limits and key baseline values.
    assert np.allclose(v2, [30.4, 9.4, 6.9])
    assert np.allclose(a2, [-16., -16., -12.])
    assert np.allclose(q1, [3.2169811321, 1.9570064289], atol=1e-9)
    assert np.allclose(q2, [2.4948244142, 1.9203670565], atol=1e-9)
    assert max_energy_increment < 1e-8
    ballistic_p = np.r_[v1, 0., 0., 0.]
    _, state_limit = aerodynamic_goal(ballistic_p, .00025)
    assert np.linalg.norm(state_limit[1:3] - q1) < 1e-6
    assert np.linalg.norm(np.array(convergence[-1]['goal_yz_m']) - np.array(convergence[-2]['goal_yz_m'])) < 1e-5
    (ROOT / 'baseline_results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ['ballistic', 'quadratic', 'aerodynamic_illustrative_restricted_fit']}, ensure_ascii=False, indent=2))
    print('Conditional noise examples, assumed sigma=0.01 m:')
    for row in uncertainty:
        if row['assumed_sigma_m'] == .01:
            print(json.dumps(row, ensure_ascii=False))


if __name__ == '__main__':
    main()
