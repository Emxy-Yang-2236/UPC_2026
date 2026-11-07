"""Render the two manuscript figures from the archived report measurements."""

import csv
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parents[1] / "report" / "evidence"
INK = "#183f4b"
TEAL = "#247481"
OCHRE = "#94541b"
GRID = "#cbd6d8"
PAPER = "#fafcfc"
PROBABILITY = LinearSegmentedColormap.from_list(
    "conditional_mass", [PAPER, "#a5cbd0", "#4d949c", "#145367"]
)
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.labelcolor": INK,
    "axes.edgecolor": "#6a7c80",
    "axes.linewidth": 0.65,
    "xtick.color": "#475a60",
    "ytick.color": "#475a60",
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "pdf.fonttype": 42,
    "mathtext.fontset": "dejavusans",
})


def save_figure(fig, filename):
    fig.savefig(HERE / filename, metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def panel_heading(fig, ax, text):
    fig.text(ax.get_position(original=True).x0, 0.94, text, color=INK,
             fontsize=10, fontweight="bold", va="top")


def cell_edges(centres):
    half_step = (centres[1] - centres[0]) / 2
    return np.r_[centres - half_step, centres[-1] + half_step]


def goal_figure():
    with (EVIDENCE / "grid.csv").open(newline="", encoding="utf-8") as stream:
        cells = list(csv.DictReader(stream))
    lateral = np.array(sorted({float(c["y_m"]) for c in cells}))
    height = np.array(sorted({float(c["z_m"]) for c in cells}))
    y_edges, z_edges = cell_edges(lateral), cell_edges(height)
    mass = np.zeros((len(height), len(lateral)))
    selected = np.zeros_like(mass, dtype=bool)
    for cell in cells:
        col = np.searchsorted(lateral, float(cell["y_m"]))
        row = np.searchsorted(height, float(cell["z_m"]))
        mass[row, col] = float(cell["probability"])
        selected[row, col] = cell["in_raw_90"] == "1"

    rows, cols = np.nonzero(mass)
    left = y_edges[max(0, cols.min() - 1)]
    right = y_edges[min(len(lateral), cols.max() + 1)]
    bottom, top = z_edges[rows.min()], z_edges[rows.max() + 1]
    fig, (overview, detail) = plt.subplots(
        1, 2, figsize=(7.1, 2.62), gridspec_kw={"width_ratios": [1.24, 1]}
    )
    fig.subplots_adjust(left=0.085, right=0.98, bottom=0.22, top=0.83, wspace=0.37)
    panel_heading(fig, overview, "a   Full goal opening")
    panel_heading(fig, detail, "b   Cell probability (%)")
    for ax in (overview, detail):
        ax.pcolormesh(y_edges, z_edges, mass, cmap=PROBABILITY, vmin=0,
                      vmax=mass.max(), shading="flat")
        ax.set_aspect("equal")
        ax.set_xlabel("Lateral position  Y  (m)", labelpad=4)
        ax.set_ylabel("Height  Z  (m)", labelpad=4)
        ax.tick_params(length=2.8, pad=3)
    overview.set_xticks([y_edges[0], 0, y_edges[-1]], ["−3.66", "0", "3.66"])
    overview.set_yticks([z_edges[0], z_edges[-1]], ["0", "2.44"])
    overview.axvline(0, color=GRID, linewidth=0.7, linestyle=(0, (2, 2)))
    overview.add_patch(Rectangle((left, bottom), right-left, top-bottom, fill=False,
                                 edgecolor=OCHRE, linewidth=1.1, linestyle=(0, (3, 2)),
                                 clip_on=False))
    detail.set(xlim=(left, right), ylim=(bottom, top), xticks=[2.0, 2.5, 3.0],
               yticks=[1.5, 1.9, 2.3])
    for y in y_edges[(y_edges > left) & (y_edges < right)]:
        detail.axvline(y, color=GRID, linewidth=0.45)
    for z in z_edges[(z_edges > bottom) & (z_edges < top)]:
        detail.axhline(z, color=GRID, linewidth=0.45)
    for row, col in zip(*np.nonzero(selected)):
        detail.add_patch(Rectangle((y_edges[col], z_edges[row]),
                                   y_edges[col + 1] - y_edges[col],
                                   z_edges[row + 1] - z_edges[row], fill=False,
                                   edgecolor=INK, linewidth=0.9))
        value = mass[row, col]
        detail.text(lateral[col], height[row], f"{100 * value:.1f}",
                    ha="center", va="center", fontsize=8.8, fontweight="bold",
                    color="white" if value > 0.19 else INK)
    save_figure(fig, "goal-forecast.pdf")


def pair_figure(pair):
    fig, (early, goal) = plt.subplots(1, 2, figsize=(7.1, 2.55),
                                     gridspec_kw={"width_ratios": [1.14, 1]})
    fig.subplots_adjust(left=0.09, right=0.98, bottom=0.22, top=0.82, wspace=0.37)
    panel_heading(fig, early, "a   Separation at a third observation")
    panel_heading(fig, goal, "b   Goal-plane crossings")
    frames = pair["third_frames"]
    times = np.array([f["t_s"] for f in frames]) * 1000
    offsets = np.array([f["max_coordinate_difference_m"] for f in frames]) * 1000
    threshold = 2000 * pair["hard_coordinate_error_m"]
    early.set(xlim=(132, 270), ylim=(0, 16), xticks=times, yticks=[0, 5, 10, 15],
              xlabel="Time after release (ms)", ylabel="Max. coordinate gap (mm)")
    early.grid(axis="y", color=GRID, linewidth=0.5, zorder=0)
    early.axhline(threshold, color=OCHRE, linewidth=1.2, linestyle=(0, (4, 3)))
    early.text(135, threshold + 0.55, f"{threshold:g} mm threshold", color=OCHRE, fontsize=8)
    early.scatter(times, offsets, s=28, color=TEAL, zorder=4)
    for x, y in zip(times, offsets):
        early.annotate(f"{y:.2f}", (x, y), xytext=(0, 5.5), textcoords="offset points",
                       ha="center", color=INK, fontsize=8.5)
    early.spines[["top", "right"]].set_visible(False)

    positions = np.array([shot["goal_yz_m"] for shot in pair["shots"]])
    goal.plot(*positions.T, color=OCHRE, linestyle=(0, (3, 2)), linewidth=1.2)
    goal.annotate(f"{100 * pair['goal_separation_m']:.2f} cm", positions.mean(axis=0),
                  xytext=(5, 9), textcoords="offset points", fontsize=8, color=OCHRE)
    for (y, z), label, marker in zip(positions, ("A", "B"), ("o", "s")):
        goal.scatter(y, z, marker=marker, s=31, color=TEAL, zorder=3)
        goal.annotate(label, (y, z), xytext=(6, 3), textcoords="offset points",
                      fontsize=9, color=INK, fontweight="bold")
    goal.set(xlabel="Lateral position  Y  (m)", ylabel="Height  Z  (m)",
             xlim=(2.545, 2.657), ylim=(1.912, 2.024),
             xticks=[2.56, 2.60, 2.64], yticks=[1.92, 1.96, 2.00])
    goal.set_aspect("equal")
    goal.set_facecolor(PAPER)
    goal.grid(color=GRID, linewidth=0.5)
    for ax in (early, goal):
        ax.tick_params(length=2.8, pad=3)
    save_figure(fig, "trajectory-pair.pdf")


if __name__ == "__main__":
    goal_figure()
    with (EVIDENCE / "measurements.json").open(encoding="utf-8") as stream:
        pair_figure(json.load(stream)["pair"])
