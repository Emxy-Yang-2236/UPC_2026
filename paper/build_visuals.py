"""Rebuild paper graphics and their exact plotted-data ledger from frozen evidence."""
import csv
import hashlib
import json
import sys
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Rectangle
from matplotlib.ticker import MaxNLocator, PercentFormatter

from flight_schematic import flight_figure

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiment/src"))
PAPER = ROOT / "paper"
FIGURES = PAPER / "figures"
EVIDENCE = "report/evidence/"
INK = "#193640"
TEAL = "#076e79"
OCHRE = "#9b501e"
SLATE = "#5a647b"
FAINT = "#e0e8ea"
PALE = "#f0f6f6"
WIDTH = 6.60
METHODS = {
    "both": ("Two-frame aero", TEAL, "o"),
    "late": ("Late-frame aero", SLATE, "s"),
    "gravity": ("Two-frame gravity", OCHRE, "^"),
}
PROFILES = {"rounded": "Centimetre rounding", "tracking": "Tracking error + rounding"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "mathtext.fontset": "dejavusans",
    "pdf.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": .7, "axes.edgecolor": SLATE, "axes.labelcolor": INK,
    "axes.titlecolor": INK, "text.color": INK, "axes.titlesize": 10,
    "xtick.color": INK, "ytick.color": INK, "xtick.labelsize": 8,
    "ytick.labelsize": 8, "legend.fontsize": 8, "legend.frameon": False,
})


class Visuals:
    def __init__(self):
        self.sources = {}
        self.figures = {}

    def read(self, path):
        content = (ROOT / path).read_bytes()
        self.sources[path] = hashlib.sha256(content).hexdigest()
        return content

    def json(self, path):
        return json.loads(self.read(path))

    def rows(self, path):
        return list(csv.DictReader(self.read(path).decode("utf-8").splitlines()))

    def save(self, fig, name, sources, plotted):
        path = FIGURES / (name + ".pdf")
        fig.savefig(path, metadata={"CreationDate": None, "ModDate": None})
        plt.close(fig)
        self.figures[path.name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "sources": sources, "plotted": plotted,
        }


def panel(ax, title):
    ax.set_title(title, loc="left", fontweight="bold", pad=8)


def grid(ax, axis="y"):
    ax.set_axisbelow(True)
    ax.grid(axis=axis, color=FAINT, linewidth=.65)


def draw_geometry(v, settings):
    source = "experiment/runs/B01/pair.json"
    force_case = "experiment/src/reference.py"
    v.read(force_case)
    fig, plotted = flight_figure(settings["official"], v.json(source))
    v.save(fig, "problem-geometry", ["design/settings.json", source, force_case], plotted)


def draw_pipeline(v, settings):
    source = "design/settings.json"
    code = "experiment/src/coverage_benchmark.py"
    estimator = "experiment/src/predict.py"
    v.read(code)
    v.read(estimator)
    fig, ax = plt.subplots(figsize=(WIDTH, 2.52))
    fig.subplots_adjust(left=.01, right=.99, bottom=.035, top=.97)
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    titles = [
        ("Visible inputs", "Launch anchor\nTime-stamped positions"),
        ("Observation model", "Coordinate likelihood\nProposal correction"),
        ("Flight propagation", "Weighted D, S, E paths\nPlane and ground events"),
        ("Two outputs", "First-event probabilities\nConditional goal map"),
    ]
    study = [
        ("Calibration only", "Rank the true cell\nFit the cutoff"),
        ("Test inputs only", "Predict and lock\nApply fitted cutoff"),
        ("Held-out scoring", "Unmask reference\nScore hit, area, error"),
    ]

    def boxes(items, y, width, gap, color):
        for i, (title, body) in enumerate(items):
            x = i * (width + gap) + .005
            ax.add_patch(FancyBboxPatch((x, y), width, .29, boxstyle="round,pad=.005",
                                       fc=PALE if color == TEAL else "#f9f2eb", ec=color, lw=.85))
            ax.text(x + width / 2, y + .218, title, ha="center", color=color, fontweight="bold")
            ax.text(x + width / 2, y + .126, body, ha="center", va="top", fontsize=8.2,
                    linespacing=1.35)
            if i:
                ax.annotate("", (x - .006, y + .145), (x - gap + .006, y + .145),
                            arrowprops={"arrowstyle": "->", "color": color, "lw": .9})

    ax.text(.005, .98, "A   Forecasting one kick", va="top", fontweight="bold")
    ax.text(.005, .49, "B   Calibrating and evaluating regions", va="top", fontweight="bold")
    boxes(titles, .59, .222, .034, TEAL)
    boxes(study, .09, .295, .052, OCHRE)
    v.save(fig, "prediction-workflow", [source, estimator, code], {
        "forecast_steps": titles, "evaluation_steps": study,
        "goal_grid": settings["study"]["grid"],
    })


def draw_goal(v, official, grid_rows):
    ys = np.array(sorted({float(r["y_m"]) for r in grid_rows}))
    zs = np.array(sorted({float(r["z_m"]) for r in grid_rows}))
    edges = [np.r_[a - (a[1] - a[0]) / 2, a[-1] + (a[1] - a[0]) / 2] for a in (ys, zs)]
    ye, ze = edges
    probability = np.zeros((len(zs), len(ys)))
    selected = []
    for r in grid_rows:
        j = int(np.searchsorted(ys, float(r["y_m"])))
        i = int(np.searchsorted(zs, float(r["z_m"])))
        probability[i, j] = 100 * float(r["probability"])
        if r["in_raw_90"] == "1":
            selected.append((i, j))
    cells = np.array(selected)
    assert np.isclose(probability.sum(), 100)
    assert np.isclose(probability[tuple(cells.T)].sum() / 100, official["raw_mass"])
    assert np.isclose(len(cells) * np.diff(ye[:2])[0] * np.diff(ze[:2])[0], official["raw_area_m2"])
    fig = plt.figure(figsize=(WIDTH, 3.42), layout="constrained")
    spec = fig.add_gridspec(2, 2, width_ratios=[1.1, 1], height_ratios=[1.9, 1])
    overview = fig.add_subplot(spec[0, 0])
    detail = fig.add_subplot(spec[:, 1])
    time = fig.add_subplot(spec[1, 0])
    norm = matplotlib.colors.Normalize(vmin=0, vmax=np.ceil(probability.max()))
    for ax in (overview, detail):
        mesh = ax.pcolormesh(ye, ze, probability, shading="flat", cmap="Blues", norm=norm)
        ax.set(xlabel="$Y$ (m)", ylabel="$Z$ (m)", aspect="equal")
        ax.spines[["top", "right"]].set_visible(True)
        for i, j in selected:
            ax.add_patch(Rectangle((ye[j], ze[i]), ye[j + 1] - ye[j], ze[i + 1] - ze[i],
                                   fc="none", ec=TEAL, lw=1.15))
    overview.set(xticks=[ye[0], 0, ye[-1]], yticks=[0, ze[-1]])
    overview.axvline(0, c=FAINT, ls="--", lw=.9)
    left, right = ye[max(0, cells[:, 1].min() - 1)], ye[min(len(ys), cells[:, 1].max() + 2)]
    bottom, top = ze[max(0, cells[:, 0].min() - 1)], ze[min(len(zs), cells[:, 0].max() + 2)]
    overview.add_patch(Rectangle((left, bottom), right - left, top - bottom,
                                 fc="none", ec=OCHRE, lw=1.3, ls="--", clip_on=False))
    detail.set(xlim=(left, right), ylim=(bottom, top))
    detail.xaxis.set_major_locator(MaxNLocator(4))
    detail.yaxis.set_major_locator(MaxNLocator(4))
    p_y, p_z = official["point"]
    for i, j in selected:
        p = probability[i, j]
        is_mode = np.allclose((ys[j], zs[i]), (p_y, p_z))
        detail.text(ys[j], zs[i] + (.059 if is_mode else 0), f"{p:.1f}",
                    ha="center", va="center", fontweight="bold",
                    color="white" if norm(p) > .56 else INK)
    detail.plot(p_y, p_z, marker="D", ms=3.5, mfc="#ffd18a", mec=INK, mew=.6)
    fig.colorbar(mesh, ax=detail, shrink=.72, pad=.025, label="Conditional mass per cell (%)")
    q05, q50, q95 = np.array(official["gate_time_q05_q50_q95_s"]) * 1000
    time.hlines(0, q05, q95, color=TEAL, lw=2)
    time.scatter([q05, q95], [0, 0], marker="|", color=TEAL, s=63)
    time.scatter(q50, 0, marker="o", color=TEAL, s=33)
    time.text(q50, .23, f"{q50:.1f} ms median", ha="center", fontsize=8)
    time.set(xlim=(389, 411), ylim=(-.15, .47), yticks=[], xlabel="Time after release (ms)")
    time.spines["left"].set_visible(False)
    panel(overview, "A   Goal opening")
    panel(detail, "B   Enlarged prediction")
    panel(time, "C   Crossing time")
    v.save(fig, "goal-forecast", [EVIDENCE + "grid.csv", EVIDENCE + "measurements.json"], {
        "grid_y_m": ys.tolist(), "grid_z_m": zs.tolist(), "probability_pct": probability.tolist(),
        "raw90_indices_z_y": selected, "modal_cell_yz_m": official["point"],
        "time_quantiles_ms": [q05, q50, q95],
    })


def draw_witness(v, settings, pair, rounded, grid_rows):
    from flight import advance

    pair_source = "experiment/runs/B01/pair.json"
    rounded_source = EVIDENCE + "review-rounded-pair.json"
    inference_source = EVIDENCE + "review-inference.json"
    solver_source = "experiment/src/flight.py"
    candidates = v.json(inference_source)["rounded_pair_candidates"]
    v.read(solver_source)
    official = settings["official"]
    display = np.array(official["xyz"])
    readings = np.array(official["times"])
    fig, (flight, offsets, goal) = plt.subplots(
        1, 3, figsize=(WIDTH, 2.90), layout="constrained",
        gridspec_kw={"width_ratios": [1.05, 1.15, 1]})
    positions = []
    paths = []
    colors = (TEAL, OCHRE)
    marks = ("o", "s")
    for color, marker, draw, checked in zip(colors, marks, candidates, rounded["verified_flights"]):
        assert draw["pooled_model_index"] == checked["pooled_model_index"]
        time = np.unique(np.r_[np.linspace(0, checked["arrival_s"], 401), readings])
        pos = np.array([official["r0"]], dtype=float)
        vel = np.array([draw["v0_m_s"]])
        nuisance = (np.array([draw["wind_m_s"]]), np.array([draw["kappa_m_inv"]]),
                    np.array([draw["beta_s_inv"]]))
        path = [pos[0].copy()]
        for step in np.diff(time):
            dr, vel = advance(vel, nuisance, "S", step, settings)
            pos += dr
            path.append(pos[0].copy())
        path = np.array(path)
        early = path[np.searchsorted(time, readings)]
        crossing = np.r_[official["gate"], checked["goal_yz_m"]]
        assert np.max(np.abs(early - checked["early_m"])) < 1e-7
        assert np.max(np.abs(path[-1] - crossing)) < 1e-7
        delta = 1000 * (early - display)
        assert np.max(np.abs(delta)) < 5
        flight.plot(path[:, 0], path[:, 2], c=color, lw=1.35)
        flight.scatter(early[:, 0], early[:, 2], marker=marker, c=color, s=14)
        offsets.scatter(np.arange(6) + (-.10 if marker == "o" else .10), delta.ravel(),
                        marker=marker, c=color, s=18, zorder=4)
        goal.scatter(*crossing[1:], marker=marker, c=color, s=24, zorder=4)
        paths.append({"t_s": time.tolist(), "xyz_m": path.tolist(), "display_offset_mm": delta.tolist()})
        positions.append(crossing[1:].tolist())

    flight.axvline(official["gate"], c=SLATE, lw=.8, ls=":")
    flight.set(xlabel="$x$ (m)", ylabel="$z$ (m)", xticks=[0, 3, 7, 11], ylim=(0, 2.52))
    panel(flight, "A   Flight profile")
    grid(flight)
    offsets.axhspan(-5, 5, color=PALE)
    offsets.axhline(0, c=SLATE, lw=.6)
    offsets.axvline(2.5, c=SLATE, lw=.65, ls=":")
    offsets.set(xticks=range(6), xticklabels=list("xyzxyz"), xlim=(-.48, 5.48),
                ylim=(-6, 6.6), yticks=[-5, 0, 5], ylabel="Offset (mm)", xlabel="50 ms             100 ms")
    panel(offsets, "B   Rounding bins")
    grid(offsets)

    yz = np.array([shot["goal_yz_m"] for shot in pair["shots"]])
    separation = np.linalg.norm(yz[0] - yz[1])
    rounded_yz = np.array(positions)
    rounded_gap = np.linalg.norm(rounded_yz[0] - rounded_yz[1])
    assert np.isclose(separation, pair["goal_separation_m"])
    assert np.isclose(rounded_gap, rounded["verified_separation_m"])
    selected = [[float(row["y_m"]), float(row["z_m"])] for row in grid_rows if row["in_raw_90"] == "1"]
    dy = 2 * official["half_width"] / settings["study"]["grid"][0]
    dz = official["height"] / settings["study"]["grid"][1]
    for y, z in selected:
        goal.add_patch(Rectangle((y - dy/2, z - dz/2), dy, dz, fc=PALE, ec="#bfced0", lw=.55))
    goal.plot(*rounded_yz.T, color=SLATE, lw=.8, ls="--")
    goal.plot(*yz.T, color=SLATE, marker=".", lw=1.35, ms=4)
    goal.text(2.69, 2.28, f"{rounded_gap*100:.1f} cm", ha="center", fontsize=8)
    goal.set(xlabel="$Y$ (m)", ylabel="$Z$ (m)", aspect="equal",
             xlim=(2.13, 3.02), ylim=(1.53, 2.43), xticks=[2.2, 2.6, 3.0], yticks=[1.6, 1.9, 2.2])
    panel(goal, "C   Goal plane")
    grid(goal, "both")
    fig.legend(handles=[Line2D([], [], color=c, marker=m, label=f"Rounded flight {i}")
                        for i, (c, m) in enumerate(zip(colors, marks), 1)] +
                       [Line2D([], [], color=SLATE, marker=".", label="Exact-centre pair"),
                        Rectangle((0, 0), 1, 1, fc=PALE, ec="#bfced0", label="Six-cell posterior region")],
               loc="outside lower center", ncol=4, columnspacing=1.0)
    v.save(fig, "witness-path", [pair_source, rounded_source, inference_source, EVIDENCE + "grid.csv",
                                "design/settings.json", solver_source], {
        "rounded_flights": paths, "rounded_goal_yz_m": positions, "rounded_separation_m": float(rounded_gap),
        "raw90_cell_centres_yz_m": selected, "goal_yz_m": yz.tolist(),
        "goal_separation_cm": 100 * separation, "display_bin_half_width_mm": 5,
    })


def draw_factors(v, rows):
    labels = {
        "reference": "Nominal", "box_2p5mm": "Coordinate bound 2.5 mm",
        "box_10mm": "Coordinate bound 10 mm", "phase_minus1ms": "Time labels −1 ms",
        "phase_plus1ms": "Time labels +1 ms", "phase_minus5ms": "Time labels −5 ms",
        "phase_plus5ms": "Time labels +5 ms", "zero_wind": "No wind",
        "half_spin_beta": "Half S lift-axis range", "half_spin_omega": "Half E spin range",
        "mass_410g": "Ball mass 410 g (E)", "mass_450g": "Ball mass 450 g (E)",
        "spin_model_S": "S alone", "spin_model_E": "E alone", "tracking_noise": "Tracking error + rounding",
    }
    assert set(labels) == {r["scenario"] for r in rows}
    order = ["reference", "box_2p5mm", "box_10mm", "phase_minus1ms", "phase_plus1ms",
             "phase_minus5ms", "phase_plus5ms", "tracking_noise", "zero_wind", "half_spin_beta",
             "half_spin_omega", "spin_model_S", "spin_model_E", "mass_410g", "mass_450g"]
    by_scenario = {r["scenario"]: r for r in rows}
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 4.50), sharey=True, layout="constrained")
    nominal_area = float(by_scenario["reference"]["region90_m2"])
    axes[1].axvline(nominal_area, color=SLATE, ls="--", lw=1)
    plotted = []
    for i, key in enumerate(order):
        row = by_scenario[key]
        good = row["ess_pass"] == "True"
        shift = 100 * float(row["shift_from_reference_m"]) if row["shift_from_reference_m"] else None
        area = float(row["region90_m2"]) if row["region90_m2"] else None
        plotted.append({"scenario": key, "shift_cm": shift, "area_m2": area, "ess": float(row["mixture_ess"])})
        for ax, x in zip(axes, (shift, area)):
            if x is None:
                ax.text(.045, i, "No weighted fit", transform=ax.get_yaxis_transform(),
                        color=OCHRE, va="center", fontsize=8)
            else:
                color = TEAL if good else OCHRE
                ax.hlines(i, 0, x, color=FAINT, lw=1.1)
                ax.scatter(x, i, s=26, marker="o" if good else "^",
                           facecolor=color if good else "white", edgecolor=color, zorder=3,
                           clip_on=False)
    axes[0].set(yticks=np.arange(len(order)), yticklabels=[labels[key] for key in order],
                ylim=(len(order) - .25, -.75), xlim=(0, 27), xlabel="Conditional mean shift (cm)")
    axes[1].set(xlim=(0, 1.17), xlabel="90% region area (m²)")
    for ax, title in zip(axes, ("A   Forecast displacement", "B   Size of the region")):
        panel(ax, title)
        grid(ax, "x")
        ax.axhspan(.5, 7.5, color="#e8f2f5", zorder=-1)
        ax.axhspan(7.5, len(order)-.5, color="#f8f0e5", zorder=-1)
        ax.axhline(7.5, color=SLATE, linewidth=.6)
        ax.tick_params(axis="y", length=0)
    fig.legend(handles=[Rectangle((0, 0), 1, 1, color="#e8f2f5", label="Measurement assumptions"),
                        Rectangle((0, 0), 1, 1, color="#f8f0e5", label="Force assumptions")],
               loc="outside lower center", ncol=2)
    v.save(fig, "sensitivity", [EVIDENCE + "z05-factors.csv"], plotted)


def coverage_data(v, summary):
    """Join scores by kick, retain true entries for position and verify area/coverage."""
    source = EVIDENCE + "z09-replay.zip"
    with ZipFile(BytesIO(v.read(source))) as z:
        assert json.loads(z.read("summary.json")) == summary
        rows = list(csv.DictReader(z.read("scores.csv").decode("utf-8").splitlines()))
    groups = defaultdict(dict)
    events = {}
    for row in rows:
        profile, method, shot = (row[k] for k in ("profile", "method", "id"))
        assert shot not in groups[profile, method]
        assert events.setdefault(shot, row["event"]) == row["event"]
        groups[profile, method][shot] = row
    goal_ids = sorted(shot for shot, event in events.items() if event == "in")
    assert len(events) == 120 and len(goal_ids) == 71 and len(rows) == 720
    for profile in PROFILES:
        for method in METHODS:
            group = groups[profile, method]
            assert group.keys() == events.keys()
            for r in summary[profile]["metrics"][method]["curve"]:
                target = f"{r['target']:g}"
                assert sum(int(group[s][f"hit_{target}"]) for s in goal_ids) == r["hit"]
                assert np.isclose(np.mean([float(group[s][f"area_{target}"]) for s in goal_ids]), r["area"])
    return groups, goal_ids


def draw_coverage(v, summary):
    fig, axes = plt.subplots(2, 2, figsize=(WIDTH, 4.95), layout="constrained",
                             gridspec_kw={"height_ratios": [1.25, 1]})
    matched_targets = [{"both": .95, "late": .95, "gravity": .9}, {"both": .95, "gravity": .8}]
    plotted = {}
    for j, (profile, title) in enumerate(PROFILES.items()):
        curves = {method: summary[profile]["metrics"][method]["curve"] for method in METHODS}
        top, bottom = axes[:, j]
        matches = {}
        for i, (method, (name, color, marker)) in enumerate(METHODS.items()):
            curve = curves[method]
            # The smallest test area is positive; the displayed axis is logarithmic.
            top.plot([r["area"] for r in curve], [r["hit"] for r in curve],
                     color=color, marker=marker, lw=1.05, ms=3.5)
            p90 = next(r for r in curve if r["target"] == .9)
            top.scatter(p90["area"], p90["hit"], marker=marker, s=43, fc="white", ec=color, zorder=4)
            if method in matched_targets[j]:
                match = next(r for r in curve if r["target"] == matched_targets[j][method])
                matches[method] = match
                bottom.barh(i, match["area"], color=color, height=.50)
                bottom.text(match["area"] + .07, i, f"{match['area']:.3f}", va="center", fontsize=8)
            else:
                bottom.text(.08, i, "No matching point", va="center", fontsize=8, color=SLATE)
        hits = {r["hit"] for r in matches.values()}
        assert len(hits) == 1 and {r["n"] for r in matches.values()} == {71}
        count = hits.pop()
        assert all(row["hit"] != count for method in METHODS if method not in matches
                   for row in curves[method])
        top.axhline(count, c=SLATE, lw=.65, ls=":")
        top.set(xscale="log", xlim=(.05, 24), ylim=(32, 73), yticks=[35, 45, 55, 65, 71],
                xlabel="Mean region area (m²)")
        bottom.set(xlim=(0, 4.1), ylim=(2.6, -.6), yticks=range(len(METHODS)),
                   yticklabels=[m[0] for m in METHODS.values()] if j == 0 else [],
                   xlabel="Mean region area (m²)")
        bottom.tick_params(axis="y", length=0)
        panel(top, f"{'AB'[j]}   {title}")
        panel(bottom, f"{'CD'[j]}   Same test coverage · {count}/71")
        grid(top)
        grid(bottom, "x")
        plotted[profile] = {"curves": curves, "matched": matches}
    axes[0, 0].set_ylabel("Held-out hits (of 71)")
    axes[0, 1].tick_params(labelleft=False)
    handles = [Line2D([], [], label=name, color=c, marker=m, lw=1, ms=4)
               for name, c, m in METHODS.values()]
    handles.append(Line2D([], [], label="90% calibration target", color=INK, marker="o",
                          mfc="white", linestyle="none", ms=5))
    fig.legend(handles=handles, loc="outside upper center", ncol=4, columnspacing=1.25)
    v.save(fig, "coverage-frontier", [EVIDENCE + "z09-summary.json", EVIDENCE + "z09-replay.zip"], plotted)


def draw_paired(v, groups, goal_ids, summary):
    fig, (counts, interval) = plt.subplots(1, 2, figsize=(WIDTH, 2.87), sharey=True, layout="constrained",
                                          gridspec_kw={"width_ratios": [1, 1.12]})
    labels = []
    plotted = []
    for i, (profile, method) in enumerate((p, m) for p in PROFILES for m in ("late", "gravity")):
        errors = [
            100 * (float(groups[profile, "both"][s]["error_m"]) -
                   float(groups[profile, method][s]["error_m"]))
            for s in goal_ids
        ]
        row = summary[profile]["paired"][method]["error_m"]
        mean = row["difference"] * 100
        lo, hi = np.array(row["interval95"]) * 100
        assert row["n"] == len(errors) and np.isclose(np.mean(errors), mean)
        win = sum(e < -1e-9 for e in errors)
        loss = sum(e > 1e-9 for e in errors)
        tie = len(errors) - win - loss
        for width, left, color in [(win, 0, TEAL), (tie, win, FAINT), (loss, win + tie, OCHRE)]:
            counts.barh(i, width, left=left, height=.52, color=color)
            if width:
                counts.text(left + width / 2, i, str(width), ha="center", va="center",
                            color=INK if color == FAINT else "white", fontsize=7.5)
        interval.errorbar(mean, i, xerr=[[mean - lo], [hi - mean]], marker="o", ms=4.7,
                          color=METHODS[method][1], capsize=3, lw=1.35)
        labels.append(f"{'Rounded' if profile == 'rounded' else 'Tracking'} vs. {method}")
        plotted.append({"profile": profile, "reference": method, "win_tie_loss": [win, tie, loss],
                        "difference_cm_by_id": dict(zip(goal_ids, errors)), "mean_cm": mean,
                        "bootstrap95_cm": [lo, hi]})
    counts.set(yticks=np.arange(4), yticklabels=labels, ylim=(3.6, -.6), xlim=(0, 71),
               xticks=[0, 25, 50, 71], xlabel="Number of test kicks")
    interval.set(xlim=(-9, 12), xticks=[-8, -4, 0, 4, 8, 12],
                 xlabel="Two-frame error minus reference (cm)")
    interval.axvline(0, color=SLATE, ls="--", lw=1)
    for ax in (counts, interval):
        ax.tick_params(axis="y", length=0)
        ax.axhline(1.5, color=FAINT, lw=.8)
        grid(ax, "x")
    panel(counts, "A   Per-kick outcome")
    panel(interval, "B   Paired mean and 95% interval")
    fig.legend(handles=[
        Rectangle((0, 0), 1, 1, color=TEAL, label="Two-frame lower error"),
        Rectangle((0, 0), 1, 1, color=FAINT, label="Tie"),
        Rectangle((0, 0), 1, 1, color=OCHRE, label="Two-frame higher error"),
    ], loc="outside upper center", ncol=3)
    v.save(fig, "paired-error", [EVIDENCE + "z09-replay.zip", EVIDENCE + "z09-summary.json"], plotted)


def draw_waiting(v, z06):
    names = {"two_100ms": "50 / 100 ms", "late_pair_150ms": "100 / 150 ms",
             "three_150ms": "50 / 100 / 150 ms"}
    colors = [TEAL, OCHRE, SLATE]
    marks = ["o", "s", "^"]
    fig, (time, area) = plt.subplots(1, 2, figsize=(WIDTH, 2.80), layout="constrained")
    plotted = {}
    for (key, label), color, mark in zip(names.items(), colors, marks):
        m = z06[key]
        r = {"remaining_ms": 1000 * m["time_to_goal_s"]["mean"],
             "error_cm": 100 * m["point_error_m"]["mean"], "point_n": m["point_error_m"]["n"],
             "area_m2": m["raw_area_m2"]["mean"], "hit": m["raw_hit"]["hit"],
             "n": m["raw_hit"]["n"]}
        plotted[key] = r
        time.scatter(r["remaining_ms"], r["error_cm"], label=label, color=color, marker=mark, s=43)
        area.scatter(r["area_m2"], r["hit"], color=color, marker=mark, s=43)
        time.annotate(f'{r["point_n"]}/72 points', (r["remaining_ms"], r["error_cm"]),
                      xytext=(8, 7 if key != "late_pair_150ms" else -12),
                      textcoords="offset points", fontsize=8, color=color)
        area.annotate(f'{r["hit"]}/72', (r["area_m2"], r["hit"]),
                      xytext=(7, 5), textcoords="offset points", fontsize=8, color=color)
    time.set(xlim=(262, 355), ylim=(10, 21.5), xlabel="Mean remaining flight (ms)",
             ylabel="Mean point error (cm)")
    area.set(xlim=(.045, .45), ylim=(48, 67), yticks=[50, 55, 60, 65], xlabel="Mean raw region area (m²)",
             ylabel="Hits (of 72 attempts)")
    panel(time, "A   Time and accuracy")
    panel(area, "B   Area and coverage")
    for ax in (time, area):
        grid(ax)
    fig.legend(*time.get_legend_handles_labels(), loc="outside upper center", ncol=3)
    v.save(fig, "waiting-tradeoff", [EVIDENCE + "z06-summary.json"], plotted)


def draw_event(v, result):
    fig, (shifts, misses) = plt.subplots(1, 2, figsize=(WIDTH, 2.88), layout="constrained")
    plotted = {}
    for phase, color, marker in [(0, TEAL, "o"), (1, SLATE, "s"), (3, OCHRE, "^")]:
        rows = sorted((r for r in result["scenarios"] if r["phase_bound_ms"] == phase),
                      key=lambda r: r["coordinate_bound_mm"])
        x = [r["coordinate_bound_mm"] for r in rows]
        shifts.plot(x, [r["tested_max_distance_m"] for r in rows], color=color,
                    marker=marker, ms=4.5, label=f"±{phase} ms" if phase else "0 ms")
        misses.plot(x, [r["no_crossing"] / r["trials"] for r in rows], color=color,
                    marker=marker, ms=4.5)
        plotted[str(phase)] = rows
    coords = sorted({r["coordinate_bound_mm"] for rows in plotted.values() for r in rows})
    for ax in (shifts, misses):
        ax.set(xticks=coords, xlabel="Per-axis coordinate bound (mm)")
        grid(ax)
    shifts.set_ylabel("Largest sampled shift (m)")
    misses.set_ylabel("Trials with no forward root")
    misses.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    misses.set_ylim(bottom=-.025)
    panel(shifts, "A   Shift when a root exists")
    panel(misses, "B   Loss of the forward root")
    fig.legend(*shifts.get_legend_handles_labels(), title="Shared time offset bound",
               loc="outside upper center", ncol=3)
    v.save(fig, "event-sensitivity", [EVIDENCE + "plane-sensitivity.json"], plotted)


def draw_capture(v, rows):
    source = EVIDENCE + "z08-feedback.csv"
    profiles = {r["profile"]: r for r in rows}
    freq = [25, 60, 120, 240]
    fig, (capture, phase) = plt.subplots(1, 2, figsize=(WIDTH, 2.76), layout="constrained")
    ready = [int(profiles[f"{f}hz"]["input_ready"]) for f in freq]
    later = int(profiles["latency6ms"]["input_ready"])
    capture.bar(range(4), ready, color=TEAL, width=.53)
    capture.scatter(3.37, later, color=OCHRE, marker="D", s=29)
    for i, n in enumerate(ready):
        capture.text(i, n + 1.1, str(n), ha="center", fontsize=8)
    capture.annotate(f"{later}\n(6 ms)", (3.37, later), xytext=(6, -4),
                     textcoords="offset points", va="top", fontsize=8, color=OCHRE)
    capture.set(xlim=(-.6, 4.22), ylim=(0, 55), xticks=range(4), xticklabels=freq,
                yticks=[0, 12, 24, 36, 48], xlabel="Camera rate (Hz)",
                ylabel="Kicks with both frames (of 48)")
    capture.text(.045, .94, "Bars: 2 ms delay", transform=capture.transAxes,
                 va="top", color=TEAL, fontsize=8)
    categories = [("Fixed phase", "phase3ms_fixed"), ("Marginalized", "phase3ms")]
    plotted = {}
    for i, (label, key) in enumerate(categories):
        p = profiles[key]
        metrics = [(int(p["ess25_estimates"]), int(p["attempts"])),
                   (int(p["nominal90_hits"]), int(p["nominal90_goal_n"]))]
        plotted[key] = metrics
        for j, ((n, total), color) in enumerate(zip(metrics, (SLATE, TEAL))):
            y = i + (.14 if j else -.14)
            phase.barh(y, n / total, color=color, height=.21)
            phase.text(n / total - .03, y, f"{n}/{total}", va="center", ha="right",
                       color="white", fontsize=8)
    phase.set(xlim=(0, 1.02), ylim=(1.66, -.66), yticks=[0, 1],
              yticklabels=[name for name, _ in categories], xlabel="Fraction of attempts")
    phase.tick_params(axis="y", length=0)
    phase.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    phase.legend(handles=[Rectangle((0, 0), 1, 1, color=SLATE, label="ESS ≥ 25"),
                          Rectangle((0, 0), 1, 1, color=TEAL, label="Raw region hit")],
                 loc="lower left", bbox_to_anchor=(0, -.01), ncol=2, columnspacing=1.0)
    panel(capture, "A   Readiness at both deadlines")
    panel(phase, "B   Handling a ±3 ms timing offset")
    grid(capture)
    grid(phase, "x")
    v.save(fig, "capture-readiness", [source], {
        "camera_rate_hz": freq, "ready_of_48_at_2ms": ready, "ready_of_48_at_240hz_6ms": later,
        "timing": plotted, "timing_metrics": ["ESS >= 25", "raw region hit"],
    })


def draw_field(v, support, references, scores):
    by_event = {r["event_id"]: r for r in references}
    assert len(support) == len(by_event) == 3 and {r["event_id"] for r in support} == by_event.keys()
    fig, (accel, gate) = plt.subplots(1, 2, figsize=(WIDTH, 2.76), layout="constrained",
                                    gridspec_kw={"width_ratios": [1.13, 1]})
    names = {"18226500001426": "Cologne", "18232100000995": "Regensburg", "18242100001386": "Kaiserslautern"}
    opening = Rectangle((-3.66, 0), 7.32, 2.44, ec=SLATE, fc=PALE, lw=1)
    gate.add_patch(opening)
    ceiling = float(support[0]["a_ceiling_all_m_s2"])
    accel.axvline(ceiling, c=OCHRE, ls="--", lw=1.05)
    accel.text(ceiling + 14, -.40, f"Model cap {ceiling:.1f}", color=OCHRE, fontsize=8)
    plotted = []
    for i, row in enumerate(support):
        eid = row["event_id"]
        name = names[eid]
        ref = by_event[eid]
        y, z = float(ref["gate_y_m"]), float(ref["gate_z_m"])
        value = float(row["min_a_needed_m_s2"])
        assert float(row["a_ceiling_all_m_s2"]) == ceiling and value > ceiling
        accel.hlines(i, 0, value, color=TEAL, lw=1.4)
        accel.scatter(value, i, color=TEAL, s=24)
        accel.text(value + 15, i, f"{value:.1f}", va="center", fontsize=8)
        gate.scatter(y, z, marker=["o", "s", "^"][i], color=TEAL, s=26)
        gate.annotate(str(i + 1), (y, z), xytext=(-7, 0), ha="right", va="center",
                      textcoords="offset points", fontweight="bold", fontsize=8)
        plotted.append({"event_id": eid, "case": name, "min_accel_m_s2": value, "y_z_m": [y, z]})
    accel.set(xlim=(0, 790), ylim=(2.5, -.67), yticks=range(3),
              yticklabels=[f"{i+1}   {case['case']}" for i, case in enumerate(plotted)],
              xlabel="Acceleration lower bound (m/s²)")
    late, = [r for r in scores if r["mask"] == "late" and r["method"] == "aero" and r["point_y_m"]]
    reference = by_event[late["event_id"]]
    observed = [float(reference["gate_y_m"]), float(reference["gate_z_m"])]
    forecast = [float(late["point_y_m"]), float(late["point_z_m"])]
    error = np.linalg.norm(np.subtract(observed, forecast))
    assert np.isclose(error, float(late["gate_error_m"]))
    gate.plot(*zip(observed, forecast), color=OCHRE, ls="--", lw=1, zorder=1)
    gate.scatter(*forecast, marker="x", color=OCHRE, s=35)
    gate.annotate(f"Late forecast\n{error:.3f} m away", forecast, xytext=(-4, -8),
                  textcoords="offset points", ha="right", va="top", color=OCHRE, fontsize=8)
    gate.set(xlim=(1.03, 3.82), ylim=(-.11, 1.56), aspect="equal", yticks=[0, .5, 1, 1.5],
             xticks=[1.5, 2, 2.5, 3, 3.66], xlabel="$Y$ (m)", ylabel="$Z$ (m)")
    accel.tick_params(axis="y", length=0)
    panel(accel, "A   Input compatibility test")
    panel(gate, "B   Crossings near the post")
    grid(accel, "x")
    v.save(fig, "field-diagnostics",
           [EVIDENCE + "field/support.csv", EVIDENCE + "field/reference.csv", EVIDENCE + "field/scores.csv"],
           {"cases": plotted, "assumed_acceleration_cap_m_s2": ceiling,
            "late_forecast": {"event_id": late["event_id"], "yz_m": forecast, "error_m": error}})


def draw_stable_spin(v, data):
    """Compare family-specific coverage, then show the area cost on stable-spin kicks."""
    groups = {(r["method"], r["calibration"], r["family"]): r for r in data["groups"]
              if r["profile"] == "tracking"}
    fig, (coverage, cost) = plt.subplots(1, 2, figsize=(WIDTH, 2.65))
    fig.subplots_adjust(left=.155, right=.885, bottom=.23, top=.81, wspace=.93)
    families = ("no_spin", "stable_spin", "wake")
    labels = ("Zero spin", "Stable spin", "Low-spin wake")
    plotted = {"family_coverage": [], "stable_spin_area": []}
    for label, method, color, marker, offset in [
        ("Two-frame aero", "nominal", TEAL, "o", -.10),
        ("Gravity", "gravity", OCHRE, "^", .10),
    ]:
        for i, family in enumerate(families):
            row = groups[method, "pooled", family]
            hit, n = row["hits"], row["goals"]
            rate = 100*hit/n
            lo, hi = 100*np.asarray(row["wilson95"])
            coverage.errorbar(rate, i+offset, xerr=[[max(0.,rate-lo)], [max(0.,hi-rate)]],
                              marker=marker, color=color, ms=4, lw=1, capsize=2,
                              label=label if i == 0 else None)
            plotted["family_coverage"].append([method, family, hit, n, lo/100., hi/100.])
    coverage.set(yticks=range(3), yticklabels=labels, ylim=(2.45,-.45),
                 xlim=(min(50, int(min(r[-2] for r in plotted["family_coverage"])*10)*10),102),
                 xlabel="Observed coverage (%)")
    coverage.axvline(90, color=SLATE, ls=":", lw=.85, zorder=0)
    coverage.legend(loc="upper left", bbox_to_anchor=(-.03,-.29), ncol=2, fontsize=7.6,
                    handlelength=1.3, columnspacing=1.1, borderaxespad=0.)
    panel(coverage, "A   Coverage by spin family")
    rows = [("Pooled", "nominal", "pooled"), ("Curvature split", "nominal", "observable"),
            ("Family maximum", "nominal", "worst_family"), ("Gravity", "gravity", "pooled")]
    max_area = max(groups[m, rule, "stable_spin"]["mean_area_m2"] for _,m,rule in rows)
    for i, (label, method, rule) in enumerate(rows):
        r = groups[method, rule, "stable_spin"]
        area = r["mean_area_m2"]
        cost.barh(i, area, color=OCHRE if method == "gravity" else TEAL, height=.50)
        cost.annotate(f"{r['hits']}/{r['goals']}", (area, i), xytext=(4, 0),
                      textcoords="offset points", va="center", ha="left", fontsize=7.7, clip_on=False)
        plotted["stable_spin_area"].append([method, rule, r["hits"], r["goals"], area])
    cost.set(yticks=range(len(rows)), yticklabels=[r[0] for r in rows], ylim=(3.55,-.55),
             xlim=(0, max_area*1.18), xlabel="Mean region area (m²)")
    panel(cost, "B   Area for stable spin")
    for ax in (coverage, cost):
        ax.tick_params(axis="y",length=0)
        grid(ax, "x")
    v.save(fig, "stable-spin", [EVIDENCE+"z10-summary.json"], plotted)


def main():
    FIGURES.mkdir(exist_ok=True)
    v = Visuals()
    cfg = v.json("design/settings.json")
    draw_geometry(v, cfg)
    draw_pipeline(v, cfg)
    measurements = v.json(EVIDENCE + "measurements.json")
    grid_rows = v.rows(EVIDENCE + "grid.csv")
    draw_goal(v, measurements["official"], grid_rows)
    draw_witness(v, cfg, v.json("experiment/runs/B01/pair.json"),
                 v.json(EVIDENCE + "review-rounded-pair.json"), grid_rows)
    draw_factors(v, v.rows(EVIDENCE + "z05-factors.csv"))
    summary = v.json(EVIDENCE + "z09-summary.json")
    scores, ids = coverage_data(v, summary)
    draw_coverage(v, summary)
    draw_paired(v, scores, ids, summary)
    draw_waiting(v, v.json(EVIDENCE + "z06-summary.json")["metrics"])
    draw_capture(v, v.rows(EVIDENCE + "z08-feedback.csv"))
    draw_field(v, v.rows(EVIDENCE + "field/support.csv"), v.rows(EVIDENCE + "field/reference.csv"),
               v.rows(EVIDENCE + "field/scores.csv"))
    draw_event(v, v.json(EVIDENCE + "plane-sensitivity.json"))
    draw_stable_spin(v, v.json(EVIDENCE + "z10-summary.json"))
    ledger = {"sources_sha256": v.sources, "figures": v.figures}
    (PAPER / "visual-data.json").write_text(json.dumps(ledger, ensure_ascii=True, indent=2) + "\n",
                                           encoding="utf-8", newline="\n")
    print(f"Built {len(v.figures)} vector figures from {len(v.sources)} source files.")


if __name__ == "__main__":
    main()
