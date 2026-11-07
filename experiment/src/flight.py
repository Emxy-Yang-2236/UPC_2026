"""B-1.0 vectorized double-precision flight and event solver (SI)."""
import numpy as np

EVENTS = ("in", "out", "ground", "timeout")


def length(a):
    return np.sqrt(np.einsum("ij,ij->i", a, a))


def gravity(cfg):
    return np.array([0., 0., -cfg["physics"]["g"]])


def draw_nuisance(rng, n, kind, cfg):
    p = cfg["physics"]
    az = rng.uniform(0, 2*np.pi, n)
    speed = p["wind_cap"] * np.sqrt(rng.random(n))
    wind = np.column_stack((speed*np.cos(az), speed*np.sin(az), np.zeros(n)))
    if kind == "E":
        drag = rng.uniform(*p["drag_offset"], n)
        cap = p["omega_cap"]
    else:
        drag = rng.uniform(*p["kappa"], n)
        cap = p["beta_cap"] if kind == "S" else 0.
    spin = rng.uniform(-cap, cap, (n, 3))
    return wind, drag, spin


def advance(v, nuisance, kind, h, cfg):
    wind, drag, spin = nuisance
    p = cfg["physics"]
    g = gravity(cfg)
    K = p["air_density"] * np.pi*p["radius"]**2 / (2*p["mass"])

    def acceleration(vel):
        u = vel - wind
        speed = length(u)
        if kind == "E":
            cross = np.cross(spin, u)
            norm = length(cross)
            cd = 0.155 + 0.346/(1 + np.exp((np.clip(speed, 9.3, 29.9)-12.19)/1.309)) + drag
            speed2 = np.maximum(speed**2, 1e-24)
            lift = K*.38*np.tanh(5*p["radius"]*norm/speed2)*speed2/np.maximum(norm, 1e-20)
            return g - (K*cd*speed)[:, None]*u + lift[:, None]*cross
        a = g - (drag*speed)[:, None]*u
        if kind == "S":
            a += np.cross(spin, u)
        return a

    k1 = acceleration(v)
    v2 = v + .5*h*k1
    k2 = acceleration(v2)
    v3 = v + .5*h*k2
    k3 = acceleration(v3)
    v4 = v + h*k3
    k4 = acceleration(v4)
    return h/6*(v + 2*v2 + 2*v3 + v4), v + h/6*(k1 + 2*k2 + 2*k3 + k4)


def early(v, nuisance, kind, cfg, last=1):
    r = np.broadcast_to(cfg["official"]["r0"], v.shape).copy().astype(float)
    frames, velocities, valid = [], [], []
    alive = np.ones(len(v), bool)
    prev = 0.
    for t in cfg["official"]["times"][:last+1]:
        n_steps = round((t-prev)/cfg["solver"]["early_dt"])
        h = (t-prev)/n_steps
        for _ in range(n_steps):
            dr, v = advance(v, nuisance, kind, h, cfg)
            r = r + dr
            alive &= (r[:, 2] > cfg["physics"]["radius"]) & (r[:, 0] < cfg["official"]["gate"])
        frames.append(r)
        velocities.append(v)
        valid.append(alive.copy())
        prev = t
    return frames, velocities, valid


def finish(r, v, nuisance, kind, cfg, t=0.):
    """Localize both possible events in a step; a launch at z=R is airborne."""
    o, s = cfg["official"], cfg["solver"]
    n = len(r)
    event = np.full(n, 3, dtype=int)
    coords = np.full((n, 2), np.nan)
    arrival = np.full(n, np.nan)
    indices = np.arange(n)
    max_dt = s["late_dt"]
    while len(indices) and t < s["horizon"]-1e-12:
        h = min(max_dt, s["horizon"]-t)
        dr, new_v = advance(v, nuisance, kind, h, cfg)
        new_r = r + dr
        fg = np.full(len(v), np.inf)
        ft = np.full(len(v), np.inf)
        gate = (r[:,0] < o["gate"]) & (new_r[:,0] >= o["gate"])
        floor = (r[:,2] >= cfg["physics"]["radius"]) & (new_r[:,2] <= cfg["physics"]["radius"]) & (dr[:,2]<0)
        fg[gate] = (o["gate"]-r[gate,0])/dr[gate,0]
        ft[floor] = (cfg["physics"]["radius"]-r[floor,2])/dr[floor,2]
        end = gate | floor
        if np.any(end):
            is_gate = fg[end] < ft[end]
            fraction = np.minimum(fg[end], ft[end])
            yz = r[end,1:] + fraction[:,None]*dr[end,1:]
            inside = (np.abs(yz[:,0]) < o["half_width"]) & (yz[:,1] > 0) & (yz[:,1] < o["height"])
            rows = indices[end]
            event[rows] = np.where(is_gate, np.where(inside, 0, 1), 2)
            arrival[rows] = t + h*fraction
            coords[rows[is_gate]] = yz[is_gate]
            keep = ~end
            indices = indices[keep]
            nuisance = tuple(a[keep] for a in nuisance)
            r, v = new_r[keep], new_v[keep]
        else:
            r, v = new_r, new_v
        t += h
    return event, coords, arrival


def cell_edges(cfg, size=None, shift=False):
    ny, nz = size or cfg["study"]["grid"]
    w, z = cfg["official"]["half_width"], cfg["official"]["height"]
    def axis(lo, hi, n):
        x = np.linspace(lo, hi, n+1)
        return np.r_[lo, (x[1:]+x[:-1])/2, hi] if shift else x
    return axis(-w,w,ny), axis(0,z,nz)


def cell_ids(yz, edges):
    ey, ez = edges
    return (np.searchsorted(ey, yz[:,0], side="right")-1)*(len(ez)-1) + np.searchsorted(ez, yz[:,1], side="right")-1


def cell_geometry(edges):
    y,z = edges
    yc,zc = np.meshgrid((y[1:]+y[:-1])/2, (z[1:]+z[:-1])/2, indexing="ij")
    return np.column_stack((yc.ravel(),zc.ravel())), np.outer(np.diff(y),np.diff(z)).ravel()
