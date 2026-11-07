"""Plot the independently integrated witness pair using only the handoff evidence."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

ROOT = Path(__file__).resolve().parent


def main():
    pair = json.loads((ROOT / "evidence/measurements.json").read_text())["pair"]
    fig, (early, gate) = plt.subplots(
        1, 2, figsize=(7.3, 3.05), gridspec_kw={"width_ratios": [1.3, 1]}, layout="constrained"
    )
    ink, copper = "#194960", "#a14622"
    observations = pair["third_frames"]
    times = [int(round(d["t_s"] * 1000)) for d in observations]
    differences = [1000 * d["max_coordinate_difference_m"] for d in observations]
    early.bar(times, differences, width=22, color=ink)
    threshold = 2000 * pair["hard_coordinate_error_m"]
    early.axhline(threshold, color=copper, linewidth=1.2, linestyle="--")
    early.text(136, threshold + 0.5, "Disjoint above 10 mm", color=copper, fontsize=9)
    for t, v in zip(times, differences):
        early.text(t, v + 0.25, f"{v:.2f}", ha="center", fontsize=9)
    early.set(xlim=(130, 270), ylim=(0, 15), xticks=times,
              xlabel="Additional frame time after kick (ms)",
              ylabel="Largest coordinate difference (mm)")
    early.set_title("(a) What a third frame resolves", loc="left", fontsize=11)
    (y1, z1), (y2, z2) = [shot["goal_yz_m"] for shot in pair["shots"]]
    gate.plot([y1, y2], [z1, z2], color="0.5", linestyle="--", linewidth=1)
    for y, z, label, offset in [(y1, z1, "A", (-13, 4)), (y2, z2, "B", (5, -3))]:
        gate.scatter(y, z, s=45, facecolor="white", edgecolor=ink, linewidth=1.8, zorder=3)
        gate.annotate(label, (y, z), xytext=offset, textcoords="offset points", color=ink)
    gate.text(0.025, 0.035, f"Separation {100 * pair['goal_separation_m']:.2f} cm",
              transform=gate.transAxes, fontsize=9, color=ink)
    gate.set(xlim=(2.54, 2.66), ylim=(1.90, 2.025), aspect="equal",
             xlabel="Lateral position at goal (m)", ylabel="Height at goal (m)")
    gate.xaxis.set_major_locator(MultipleLocator(0.04))
    gate.yaxis.set_major_locator(MultipleLocator(0.04))
    gate.set_title("(b) Two goal crossings", loc="left", fontsize=11)
    for ax in (early, gate):
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=9)
    fig.savefig(ROOT / "evidence/ambiguity.png", dpi=220)
    plt.close(fig)


if __name__ == "__main__":
    main()
