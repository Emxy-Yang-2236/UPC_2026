"""Reproduce stipulated cooling calculations and a separate ODE implementation.

Standard-library Python only. Run from any directory: python src/solve.py
Paths are resolved relative to this project, not to this computer's checkout.
No experimental data are generated or claimed.
"""

import csv
import json
import math
import platform
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/inputs.json"


def rk4_step(temperature, heat, dt, capacity, conductance, ambient):
    # Integrate the stipulated temperature law and outward heat flux together.
    def rhs(temp):
        flux = conductance * (temp - ambient)
        return -flux / capacity, flux

    k1 = rhs(temperature)
    k2 = rhs(temperature + dt * k1[0] / 2)
    k3 = rhs(temperature + dt * k2[0] / 2)
    k4 = rhs(temperature + dt * k3[0])
    return tuple(
        old + dt * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]) / 6
        for i, old in enumerate((temperature, heat))
    )


def integrate_to_threshold(c, g, initial, ambient, target, steps_per_tau):
    # This event calculation uses the ODE, with no exp/log temperature solution.
    dt = c / g / steps_per_tau
    t, temp, heat = 0.0, initial, 0.0
    for _ in range(100000):
        trial_temp, trial_heat = rk4_step(temp, heat, dt, c, g, ambient)
        if trial_temp <= target:
            lo, hi = 0.0, dt
            while hi - lo > 1e-11:
                mid = (lo + hi) / 2
                if rk4_step(temp, heat, mid, c, g, ambient)[0] > target:
                    lo = mid
                else:
                    hi = mid
            last_dt = (lo + hi) / 2
            final_temp, final_heat = rk4_step(temp, heat, last_dt, c, g, ambient)
            return t + last_dt, final_temp, final_heat
        t, temp, heat = t + dt, trial_temp, trial_heat
    raise RuntimeError("Threshold event was not reached")


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    c = config["heat_capacity_J_per_K"]
    initial = config["initial_temperature_C"]
    ambient = config["ambient_temperature_C"]
    target = config["threshold_temperature_C"]
    assert c > 0 and ambient < target < initial
    theta_star = (target - ambient) / (initial - ambient)
    dimensionless_time = -math.log(theta_star)
    expected_heat = c * (initial - target)
    results, checks, checks_finest = [], [], []
    for nominal_g in config["nominal_conductances_W_per_K"]:
        for fraction in config["conductance_scenario_fractions"]:
            g = nominal_g * (1 + fraction)
            assert g > 0
            tau = c / g
            exact_time = tau * dimensionless_time
            threshold_residual = ambient + (initial - ambient) * math.exp(-exact_time / tau) - target
            assert abs(threshold_residual) < 1e-10
            results.append({
                "nominal_G_W_per_K": nominal_g,
                "relative_scenario_change": fraction,
                "G_W_per_K": g,
                "tau_s": tau,
                "theta_star": theta_star,
                "dimensionless_threshold_time": dimensionless_time,
                "threshold_time_s": exact_time,
                "relative_time_change": 1 / (1 + fraction) - 1,
                "heat_removed_J": expected_heat,
                "threshold_residual_K": threshold_residual,
            })
            for n in config["numerical_check_steps_per_time_constant"]:
                numerical_time, numerical_temp, numerical_heat = integrate_to_threshold(
                    c, g, initial, ambient, target, n
                )
                checks.append({
                    "nominal_G_W_per_K": nominal_g,
                    "relative_scenario_change": fraction,
                    "G_W_per_K": g,
                    "steps_per_tau": n,
                    "dt_s": tau / n,
                    "numerical_threshold_time_s": numerical_time,
                    "exact_threshold_time_s": exact_time,
                    "absolute_time_error_s": abs(numerical_time - exact_time),
                    "threshold_residual_K": numerical_temp - target,
                    "integrated_heat_J": numerical_heat,
                    "absolute_heat_error_J": abs(numerical_heat - expected_heat),
                })
                if n == max(config["numerical_check_steps_per_time_constant"]):
                    checks_finest.append(checks[-1])
    max_time_error = max(r["absolute_time_error_s"] for r in checks_finest)
    max_heat_error = max(r["absolute_heat_error_J"] for r in checks_finest)
    assert max_time_error < config["finest_event_time_tolerance_s"]
    assert max_heat_error < config["heat_balance_tolerance_J"]
    for group_index in range(len(results)):
        group = checks[group_index * 3:group_index * 3 + 3]
        assert all(group[i+1]["absolute_time_error_s"] < group[i]["absolute_time_error_s"] for i in range(2))
    low_design_fastest = min(r["threshold_time_s"] for r in results if r["nominal_G_W_per_K"] == 8)
    high_design_slowest = max(r["threshold_time_s"] for r in results if r["nominal_G_W_per_K"] == 12)
    assert high_design_slowest < low_design_fastest
    summary = {
        "python_version": platform.python_version(),
        "data_kind": "Deterministic calculations for an invented, stipulated model; no measurements",
        "theta_star": theta_star,
        "dimensionless_threshold_time": dimensionless_time,
        "heat_removed_J_all_scenarios": expected_heat,
        "time_sensitivity_elasticity_to_G": -1.0,
        "design_12_slowest_time_s": high_design_slowest,
        "design_8_fastest_time_s": low_design_fastest,
        "robust_ordering_gap_s": low_design_fastest - high_design_slowest,
        "numerical_check": {
            "method": "RK4 on T and integrated heat; bisection on final partial step",
            "steps_per_time_constant": config["numerical_check_steps_per_time_constant"],
            "event_bisection_bracket_tolerance_s": 1e-11,
            "finest_maximum_absolute_time_error_s": max_time_error,
            "finest_time_tolerance_s": config["finest_event_time_tolerance_s"],
            "finest_maximum_absolute_heat_error_J": max_heat_error,
            "heat_tolerance_J": config["heat_balance_tolerance_J"],
            "all_time_error_sequences_decrease": True,
            "pass": True,
            "scope": "Implementation and arithmetic self-check only; not empirical validation of the physical model"
        }
    }
    output = ROOT / "data/derived"
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "results.csv", results)
    write_csv(output / "numerical_check.csv", checks)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    table = ["# Accepted result table", "", "All entries are stipulated-model calculations, not measurements.", "", "| Nominal G (W/K) | G change | Actual G (W/K) | Time to 30 C (s) | Heat removed (kJ) |", "| ---: | ---: | ---: | ---: | ---: |"]
    for row in results:
        table.append(f"| {row['nominal_G_W_per_K']:.0f} | {row['relative_scenario_change']:+.0%} | {row['G_W_per_K']:.1f} | {row['threshold_time_s']:.2f} | {row['heat_removed_J']/1000:.1f} |")
    (output / "results.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
