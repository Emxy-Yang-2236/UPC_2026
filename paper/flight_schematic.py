"""Draw the recorded penalty geometry and a separate example of Magnus lift."""
from itertools import combinations, product
from math import cos, radians, sin

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Polygon


INK = "#193640"
TEAL = "#076e79"
RUST = "#a64b26"
SLATE = "#516674"
GUIDE = "#91aaa9"
SPIN = "#71548e"

def camera(azimuth, elevation):
    """Orthonormal screen-right and screen-up directions for an oblique view."""
    azimuth, elevation = map(radians, (azimuth, elevation))
    return np.array([[cos(azimuth), -sin(azimuth), 0.0],
                     [sin(azimuth)*sin(elevation), cos(azimuth)*sin(elevation), cos(elevation)]])


VIEW = camera(37, 20)


def project(xyz):
    return np.asarray(xyz, dtype=float) @ VIEW.T


def line(ax, xyz, **style):
    ax.plot(*project(xyz).T, solid_capstyle="round", **style)


def surface(ax, xyz, **style):
    ax.add_patch(Polygon(project(xyz), closed=True, **style))


def draw_field(ax, official, points, future):
    gate, half, height = (official[key] for key in ("gate", "half_width", "height"))
    field_edge = half + .32
    x_left, x_right = -.58, gate + .75
    # A shallow turf base makes the three directions visible without a box around the plot.
    surface(ax, [(x_left, -field_edge, -.10), (x_right, -field_edge, -.10),
                 (x_right, -field_edge, 0), (x_left, -field_edge, 0)],
            fc="#c0cfca", ec="none")
    surface(ax, [(x_left, field_edge, -.10), (x_left, -field_edge, -.10),
                 (x_left, -field_edge, 0), (x_left, field_edge, 0)],
            fc="#aebfb9", ec="none")
    band_edges = np.linspace(x_left, x_right, 7)
    for i, (a, b) in enumerate(zip(band_edges[:-1], band_edges[1:])):
        surface(ax, [(a, -field_edge, 0), (b, -field_edge, 0),
                     (b, field_edge, 0), (a, field_edge, 0)],
                fc=("#e6f0e9", "#edf4ee")[i % 2], ec="none")
    line(ax, [(x_left, -field_edge, 0), (x_right, -field_edge, 0),
              (x_right, field_edge, 0), (x_left, field_edge, 0),
              (x_left, -field_edge, 0)], color="#a8beb2", lw=.55)
    # The upright face alone defines the crossing; the light mesh is a drawing aid behind it.
    back = gate + .55
    net = "#b0c2c2"
    for y in np.linspace(-half, half, 14):
        line(ax, [(gate, y, height), (back, y, height - .18), (back, y, 0)],
             color=net, lw=.38)
    for z in np.linspace(0, height - .18, 6):
        line(ax, [(back, -half, z), (back, half, z)], color=net, lw=.38)
    for y in (-half, half):
        line(ax, [(gate, y, height), (back, y, height - .18), (back, y, 0),
                  (gate, y, 0)], color="#8aaba8", lw=.70)
    surface(ax, [(gate,-half,0), (gate,half,0), (gate,half,height), (gate,-half,height)],
            fc="#c4dedb", alpha=.36, ec="none")
    frame = [(gate, -half, 0), (gate, -half, height),
             (gate, half, height), (gate, half, 0)]
    line(ax, frame, color=INK, lw=2.1)
    line(ax, frame, color="#edf5f4", lw=.70)
    line(ax, [(gate,-half,0), (gate,half,0)], color=INK, lw=.9)

    for point in points[1:]:
        line(ax, [point, (*point[:2], 0)], color=GUIDE, lw=.65, ls=(0, (2, 2)))
    ground_path = np.vstack([points, future])
    ground_path[:, 2] = .006
    line(ax, ground_path, color="#9fb2ac", lw=.65, ls=(0, (1, 2)))
    line(ax, points, color="white", lw=3.4)
    line(ax, points, color=TEAL, lw=1.9)
    continuation = np.vstack([points[-1], future])
    line(ax, continuation, color="white", lw=3.1)
    line(ax, continuation, color=RUST, lw=1.8, ls=(0, (3, 2)))
    for point, marker in zip(points, ("s", "o", "o")):
        ax.plot(*project(point), marker=marker, ms=5, mfc=TEAL, mec="white", mew=.8)
    _, target_y, target_z = future[-1]
    line(ax, [(gate,target_y,0), (gate,target_y,target_z), (gate,0,target_z)],
         color="#997864", lw=.7, ls=(0, (2, 2)))
    target = project(future[-1])
    ax.plot(*target, marker="D", ms=5.8, mfc=RUST, mec="white", mew=.9)
    ax.annotate("$Q_A$", target, xytext=(-23, 9), textcoords="offset points",
                ha="right", color="black", fontsize=9,
                arrowprops=dict(arrowstyle="-", color=RUST, lw=.6, shrinkB=3.5))

    for point, label, offset in zip(points, ("0 ms", "50 ms", "100 ms"),
                                     ((-3, -11), (-12, 17), (-2, 21))):
        ax.annotate(label, project(point), xytext=offset, textcoords="offset points",
                    ha="right" if offset[0] < 0 else "left",
                    va="top" if offset[1] < 0 else "bottom", color="black", fontsize=7.8,
                    arrowprops=dict(arrowstyle="-", color=SLATE, lw=.57, shrinkB=3.4))

    # Dimension parallel to x. Both endpoints use the same lateral position.
    xa = points[-1, 0]
    dim_y = -field_edge - .76
    a, b = project([(xa, dim_y, 0), (gate, dim_y, 0)])
    for x in (xa, gate):
        line(ax, [(x,dim_y-.16,0), (x,-field_edge+.04,0)], color=SLATE, lw=.6)
    ax.annotate("", b, a, arrowprops=dict(arrowstyle="<->", color=SLATE, lw=.7,
                                           shrinkA=0, shrinkB=0, mutation_scale=7))
    text_angle = np.degrees(np.arctan2(*(b-a)[::-1]))
    ax.annotate(f"{gate-xa:.2f} m downfield", (a+b)/2,
                xytext=(0,-6.5), textcoords="offset points", rotation=text_angle,
                ha="center", va="top", fontsize=7.7, color="black")

    mid_bar = project((gate, 0, height))
    ax.annotate(f"Goal plane  $x={gate:g}$ m", mid_bar, xytext=(1, 16),
                textcoords="offset points", ha="center", va="bottom", fontsize=8,
                color="black", fontweight="bold",
                arrowprops=dict(arrowstyle="-", color=SLATE, lw=.6, shrinkB=3))
    # A ground-aligned reference triad uses the same projection as the pitch.
    origin = np.array([-1.2, 2.8, .24])
    for name, vector, shift in (("$x$", (1.12,0,0), (2,-1)),
                                ("$y$", (0,1.12,0), (-4,0)),
                                ("$z$", (0,0,.96), (0,2))):
        start, end = project([origin, origin+vector])
        ax.annotate("", end, start, arrowprops=dict(arrowstyle="-|>", color=SLATE,
                    lw=.75, shrinkA=0, shrinkB=0, mutation_scale=6))
        ax.annotate(name, end, xytext=shift, textcoords="offset points", fontsize=7.3,
                    ha="center", va="center", color="black")
    ax.set(xlim=(-4, 12.65), ylim=(-2.20, 6.0), aspect="equal")
    ax.axis("off")


def draw_ball(ax, radius):
    """Project the pentagons and hexagons of a truncated icosahedron onto a sphere."""
    phi = (1 + np.sqrt(5)) / 2
    vertices = np.array([np.roll((0.0, a, b * phi), shift)
                         for a, b in product((-1, 1), repeat=2) for shift in range(3)])
    edges = np.isclose(np.linalg.norm(vertices[:, None] - vertices, axis=2), 2)
    faces = []
    for i, vertex in enumerate(vertices):
        neighbours = vertices[edges[i]]
        normal = vertex / np.linalg.norm(vertex)
        radial = neighbours - (neighbours @ normal)[:, None] * normal
        first = radial[0] / np.linalg.norm(radial[0])
        order = np.argsort(np.arctan2(radial @ np.cross(normal, first), radial @ first))
        faces.append(((2 * vertex + neighbours[order]) / 3, True))
    for a, b, c in combinations(range(len(vertices)), 3):
        if edges[a,b] and edges[b,c] and edges[c,a]:
            ring = [(a,b), (b,a), (b,c), (c,b), (c,a), (a,c)]
            faces.append((np.array([(2 * vertices[i] + vertices[j]) / 3 for i,j in ring]), False))

    # Align a pentagonal panel slightly above and left of the visible centre.
    away = np.array([.21, -.69, .693])
    away /= np.linalg.norm(away)
    right = np.cross((0, 0, 1), away)
    right /= np.linalg.norm(right)
    camera = np.stack([right, np.cross(away, right), away], axis=1)
    disk = Circle((0, 0), radius, facecolor="#f2f6f4", edgecolor="none", zorder=5)
    ax.add_patch(disk)
    light = np.array([-.40, .55, .73])
    for vertices_3d, is_pentagon in sorted(faces, key=lambda f: (f[0].mean(axis=0) @ away)):
        # Subdividing the shared edges makes the panels wrap around the silhouette.
        corners = vertices_3d @ camera
        ring = np.concatenate([a + (b-a)*np.arange(8)[:, None]/8
                               for a,b in zip(corners, np.roll(corners, -1, axis=0))])
        ring /= np.linalg.norm(ring, axis=1)[:, None]
        normal = ring.mean(axis=0)
        normal /= np.linalg.norm(normal)
        intensity = max(0., float(normal @ light))
        color = (np.array([.085,.18,.20]) + .12*intensity if is_pentagon
                 else np.array([.77,.82,.81]) + .17*intensity)
        ax.add_patch(Polygon(ring[:, :2]*radius, closed=True, facecolor=color,
                             edgecolor="#7f9795", lw=.29, clip_path=disk, zorder=6))
    ax.add_patch(Circle((0,0), radius, fc="none", ec=INK, lw=.7, zorder=7))


def unit(vector):
    return vector / np.linalg.norm(vector)


def draw_forces(ax):
    # Frozen "empirical" release from numerical_checks in experiment/src/reference.py.
    velocity = np.array([30., 7., 7.])
    wind = np.array([1., -1., 0.])
    omega = np.array([20., -35., 12.])
    air = velocity - wind
    magnus = np.cross(omega, air)
    view = camera(-70, 35)
    facing = np.cross(*view)
    spin_axis = unit(omega)
    # With this basis, d(rim)/d(theta) = spin_axis x rim. The second
    # basis vector points towards the reader, so 0 < theta < pi is visible.
    side = unit(np.cross(facing, spin_axis))
    front = np.cross(spin_axis, side)
    theta = np.linspace(0, 2*np.pi, 161)
    radius = 17.
    ring_radius = 1.23 * radius
    rim = ring_radius * ((np.outer(np.cos(theta), side) + np.outer(np.sin(theta), front)) @ view.T)
    middle = len(theta) // 2
    ax.plot(*rim[middle:].T, color=SPIN, lw=.9, ls=(0, (2.0, 2.2)), zorder=2)

    end_spin = 48 * unit(view @ omega)
    ax.plot(*np.stack([-.60*end_spin, (0, 0)]).T, color=SPIN, lw=.8,
            ls=(0, (2, 2)), zorder=2)
    vectors = [
        (r'Spin axis $\omega$', end_spin, SPIN, '-', (-2, -4), 'center', 'top'),
        ('Magnus lift\n' + r'$\parallel\,\omega\times\mathbf{u}$',
         47*unit(view @ magnus), TEAL, '-', (5, 0), 'left', 'center'),
        ('Drag', -50*unit(view @ air), RUST, '-', (-2, 2), 'center', 'bottom'),
        ('Relative velocity\n' + r'$\mathbf{u}=\mathbf{v}-\mathbf{w}$',
         52*unit(view @ air), SLATE, (0, (3, 2)), (-1, -3), 'center', 'top'),
        (r'Weight $m\mathbf{g}$', 41*unit(view @ np.array([0, 0, -1])),
         INK, '-', (-3, -2), 'center', 'top'),
    ]
    for label, tip, color, style, offset, align, valign in vectors:
        ax.annotate('', tip, (0, 0), zorder=3,
                    arrowprops=dict(arrowstyle='-|>', color=color, linestyle=style,
                                    lw=1.45, mutation_scale=8.5, shrinkA=0, shrinkB=0))
        ax.annotate(label, tip, xytext=offset, textcoords='offset points',
                    ha=align, va=valign, fontsize=7.75, color='black', linespacing=1.10)
    draw_ball(ax, radius)
    for color, width in [('white', 3.15), (SPIN, 1.65)]:
        ax.plot(*rim[:middle + 1].T, lw=width, color=color, solid_capstyle='round', zorder=8)
    arrow_angle = radians(120)
    tip = ring_radius * ((cos(arrow_angle)*side + sin(arrow_angle)*front) @ view.T)
    tangent = unit((-sin(arrow_angle)*side + cos(arrow_angle)*front) @ view.T)
    normal = np.array([-tangent[1], tangent[0]])
    base = tip - 5.8*tangent
    ax.add_patch(Polygon([tip, base + 2.8*normal, base - 2.8*normal],
                         facecolor=SPIN, edgecolor=SPIN, linewidth=.4, zorder=9))
    ax.set(xlim=(-78, 80), ylim=(-55, 55), aspect='equal')
    ax.axis('off')
    return {
        'model': 'E', 'source_case': 'empirical in experiment/src/reference.py::numerical_checks',
        'interpretation': 'Illustrative release, independent of the model-S witness in panel A.',
        'velocity_m_s': velocity.tolist(), 'wind_m_s': wind.tolist(),
        'air_relative_velocity_m_s': air.tolist(), 'spin_rad_s': omega.tolist(),
        'magnus_direction_unit': unit(magnus).tolist(), 'drag_direction_unit': (-unit(air)).tolist(),
        'weight_direction_unit': [0, 0, -1], 'rotation_sense': 'right-handed about omega',
        'view_azimuth_elevation_deg': [-70, 35], 'arrow_lengths': 'schematic',
        'parallel_spin_limit': 'omega parallel to u gives zero Magnus lift in model E',
    }


def flight_figure(official, pair):
    points = np.array([official["r0"], *official["xyz"]])
    shot = pair["shots"][0]
    future = np.array([*shot["third_frame_xyz_m"], [official["gate"], *shot["goal_yz_m"]]])
    fig = plt.figure(figsize=(6.60, 3.05), facecolor="white")
    fig.text(.013,.93,"A   Flight to the goal plane", fontsize=9.7, color="black", weight="bold")
    fig.text(.660,.93,"B   Spin and lift in model E", fontsize=9.7, color="black", weight="bold")
    field = fig.add_axes([.002,.251,.704,.626])
    forces = fig.add_axes([.650,.330,.343,.525])
    fig.add_artist(Line2D([.645,.645],[.25,.90],color="#dbe4e1", lw=.7))
    draw_field(field, official, points, future)
    release_forces = draw_forces(forces)
    # A second orientation isolates the spin component unobservable through lift.
    aligned = fig.add_axes([.660,.225,.324,.091])
    aligned.set(xlim=(0, 150), ylim=(0, 19))
    aligned.axis("off")
    for y, symbol, color, style in [(13.5, r"$\omega$", SPIN, "-"),
                                    (4.2, r"$\mathbf{u}$", SLATE, (0, (3, 2)))]:
        aligned.text(0, y, symbol, ha="left", va="center", fontsize=7.7, color="black")
        aligned.annotate("", (33, y), (10, y), arrowprops=dict(arrowstyle="-|>",
                         lw=1.25, color=color, linestyle=style, shrinkA=0, shrinkB=0, mutation_scale=7))
    aligned.text(43, 13.5, "Parallel spin", va="center", fontsize=7.4, weight="bold", color="black")
    aligned.text(43, 4.2, "No Magnus lift", va="center", fontsize=7.4, color="black")
    # Three brief coordinate records preserve the precision of the supplied inputs.
    fig.add_artist(Line2D([.014,.986],[.206,.206],color="#c7d6d2",lw=.7))
    times = [0, *np.rint(np.asarray(official["times"])*1000).astype(int)]
    for x, t, xyz in zip((.014,.247,.47), times, points):
        heading = "Release" if t == 0 else f"{t} ms"
        fig.text(x,.132,heading,fontsize=7.7,color="black",weight="bold")
        fig.text(x,.053,"(" + ", ".join(f"{c:.2f}" for c in xyz) + ") m",
                 fontsize=7.65,color="black")
    fig.text(.660,.132,"Goal opening",fontsize=7.7,color="black",weight="bold")
    fig.text(.660,.053,f"{2*official['half_width']:.2f} m wide × {official['height']:.2f} m high",
             fontsize=7.65,color="black")
    plotted = {
        "observations_xyz_m": points.tolist(), "time_ms": [int(t) for t in times],
        "gate_x_m": official["gate"], "half_width_m": official["half_width"],
        "height_m": official["height"], "remaining_x_m": official["gate"]-points[-1,0],
        "witness": "A, the first archived zero-wind S-model flight",
        "continuation_times_s": [r["t_s"] for r in pair["third_frames"]] + [shot["arrival_s"]],
        "continuation_xyz_m": future.tolist(), "path_display": "straight joins of archived samples",
        "panel_a_view_azimuth_elevation_deg": [37,20],
        "panel_b_release": release_forces,
    }
    return fig, plotted
