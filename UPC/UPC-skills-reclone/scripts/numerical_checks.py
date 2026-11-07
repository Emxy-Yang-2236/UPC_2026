#!/usr/bin/env python3
"""Small, dependency-free numerical diagnostics for UPC research.

Commands:
  numerical_checks.py biquad --a1 -1.9 --a2 .88
  numerical_checks.py convergence result.csv

The biquad denominator is 1 + a1*z^-1 + a2*z^-2. Stability requires
both poles to be strictly inside the unit circle, with no hidden tolerance.

Convergence input is a CSV with h,value columns and at least three rows in
coarse-to-fine order. Every h must be finite, positive, strictly decreasing,
and geometrically refined. Additional CSV columns are ignored. The complete
sequence is checked for spacing, roundoff, oscillation, shrinking differences,
and consistent local orders. Orders are computed on all consecutive triples;
the reported order and Richardson error use the finest triple only. No fit
to an unknown exact solution is performed. A successful diagnostic is evidence
of apparent numerical convergence, not proof of convergence or model validity.

Normal diagnostics, including unstable/nonconvergent results, exit 0 and print
JSON to stdout. Malformed files or nonfinite/nonnumeric inputs exit 2 and print
a JSON error to stderr. No files are written by this program.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Iterable


GEOMETRIC_RTOL = 1e-6
MIN_LOG_REFINEMENT = 1e-8
ROUNDOFF_ULPS = 64
ORDER_ATOL = 0.25
ORDER_RTOL = 0.10
CONVERGENCE_LIMITATION = (
    "Empirical scalar-sequence diagnostic only: it does not prove convergence, "
    "correct implementation, or physical model validity. The error estimate "
    "assumes a dominant C*h**p term with a common limiting value."
)


def finite_number(value: object, name: str) -> float:
    """Parse a real scalar and reject NaN/infinity rather than emitting them."""
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite real number; got {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite; got {value!r}")
    return result


def check_biquad(a1: object, a2: object) -> dict:
    """Return poles of z**2 + a1*z + a2 using scaled quadratic arithmetic."""
    a1 = finite_number(a1, "a1")
    a2 = finite_number(a2, "a2")
    scale = max(abs(a1), math.sqrt(abs(a2)))
    if scale == 0.0:
        poles = [complex(0.0, 0.0), complex(0.0, 0.0)]
    else:
        b = a1 / scale
        c = (a2 / scale) / scale
        discriminant = b * b - 4.0 * c
        if discriminant < 0.0:
            real = -0.5 * a1
            imag = (0.5 * math.sqrt(-discriminant)) * scale
            poles = [complex(real, imag), complex(real, -imag)]
        else:
            # Compute the root with addition of same-sign magnitudes first.
            # The product relation recovers a small second root without
            # catastrophic cancellation in the direct quadratic formula.
            q = (-0.5 * (b + math.copysign(math.sqrt(discriminant), b))) * scale
            second = a2 / q if q != 0.0 else 0.0
            poles = [complex(q, 0.0), complex(second, 0.0)]
    if any(not math.isfinite(part) for pole in poles for part in (pole.real, pole.imag)):
        raise ValueError("Pole calculation exceeded floating-point range")
    poles.sort(key=lambda pole: (abs(pole), pole.real, pole.imag), reverse=True)
    max_radius = max(abs(pole) for pole in poles)
    if not math.isfinite(max_radius):
        raise ValueError("Pole radius exceeded floating-point range")
    stable = max_radius < 1.0
    return {
        "check": "biquad",
        "denominator": "1 + a1*z^-1 + a2*z^-2",
        "a1": a1,
        "a2": a2,
        "poles": [{"real": pole.real, "imag": pole.imag} for pole in poles],
        "max_radius": max_radius,
        "stability_margin": 1.0 - max_radius,
        "stable": stable,
        "status": "stable" if stable else ("boundary" if max_radius == 1.0 else "unstable"),
        "criterion": "All pole radii must be strictly less than 1, using the supplied coefficients.",
        "limitation": "Double-precision pole test only; not a frequency-response or model-validity check.",
    }


def read_convergence_csv(path: str | Path) -> list[tuple[float, float]]:
    """Read all rows; report malformed data with its CSV line number."""
    rows = []
    with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        names = reader.fieldnames or []
        if names.count("h") != 1 or names.count("value") != 1:
            raise ValueError("CSV must have exactly one 'h' column and one 'value' column")
        for row in reader:
            if None in row:
                raise ValueError(f"CSV line {reader.line_num} has more fields than the header")
            h = finite_number(row.get("h"), f"CSV line {reader.line_num} h")
            value = finite_number(row.get("value"), f"CSV line {reader.line_num} value")
            rows.append((h, value))
    if len(rows) < 3:
        raise ValueError("Convergence diagnosis requires at least three h,value rows")
    return rows


def check_convergence(rows: Iterable[tuple[object, object]]) -> dict:
    """Qualify the entire series, then estimate order/error on its finest triple.

    For d_i = value_i - value_(i+1) and r = h_i/h_(i+1),
    p_i = log(abs(d_i)/abs(d_(i+1))) / log(r).
    The finest-grid absolute error estimate is abs(d_last)/(r**p_last - 1).
    All neighboring p_i must lie within max(0.25, 10% of the largest absolute
    order) of each other before an order/error is reported as applicable.
    Differences <= 64 ulps of either endpoint are considered unresolved.
    """
    parsed = []
    for index, pair in enumerate(rows, start=1):
        try:
            h_raw, value_raw = pair
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Row {index} must contain exactly h,value") from exc
        h = finite_number(h_raw, f"row {index} h")
        value = finite_number(value_raw, f"row {index} value")
        if h <= 0.0:
            raise ValueError(f"row {index} h must be positive")
        parsed.append((h, value))
    if len(parsed) < 3:
        raise ValueError("Convergence diagnosis requires at least three h,value rows")

    hs, values = zip(*parsed)
    result = {
        "check": "convergence",
        "rows": len(parsed),
        "status": None,
        "reason": None,
        "observed_order": None,
        "fine_grid_error_estimate": None,
        "extrapolated_value": None,
        "fine_h": hs[-1],
        "fine_value": values[-1],
        "local_orders": [],
        "estimate_basis": "Finest three rows; all rows must pass sequence checks first.",
        "geometric_relative_tolerance": GEOMETRIC_RTOL,
        "roundoff_threshold_ulps": ROUNDOFF_ULPS,
        "limitation": CONVERGENCE_LIMITATION,
    }

    def diagnose(status: str, reason: str) -> dict:
        result.update(status=status, reason=reason)
        return result

    if any(left <= right for left, right in zip(hs, hs[1:])):
        return diagnose("invalid_grid", "h must be strictly decreasing in coarse-to-fine row order.")

    log_ratios = [math.log(left) - math.log(right) for left, right in zip(hs, hs[1:])]
    # Comparing logarithms handles h ranges for which left/right would overflow.
    if max(log_ratios) - min(log_ratios) > math.log1p(GEOMETRIC_RTOL):
        return diagnose("non_geometric", "Refinement ratios are not equal within the stated tolerance.")
    log_r = log_ratios[-1]
    if log_r <= MIN_LOG_REFINEMENT:
        return diagnose("insufficient_refinement", "The refinement ratio is too close to 1 for a reliable order estimate.")
    try:
        ratio = math.exp(log_r)
    except OverflowError:
        return diagnose("numerical_range", "The refinement ratio exceeds floating-point range.")
    result["refinement_ratio"] = ratio

    differences = [left - right for left, right in zip(values, values[1:])]
    if any(not math.isfinite(delta) for delta in differences):
        return diagnose("numerical_range", "A value difference exceeds floating-point range.")
    result["adjacent_differences"] = differences
    if any(delta == 0.0 for delta in differences):
        return diagnose("plateau", "At least one adjacent difference is zero; an order cannot be resolved.")

    thresholds = [ROUNDOFF_ULPS * max(math.ulp(left), math.ulp(right))
                  for left, right in zip(values, values[1:])]
    if any(abs(delta) <= threshold for delta, threshold in zip(differences, thresholds)):
        return diagnose("roundoff_limited", "At least one difference is too small relative to endpoint floating-point resolution.")
    if any((left > 0.0) != (right > 0.0) for left, right in zip(differences, differences[1:])):
        return diagnose("oscillatory", "Adjacent differences change sign; a single monotone C*h**p estimate is inapplicable.")

    magnitudes = [abs(delta) for delta in differences]
    local_orders = [(math.log(left) - math.log(right)) / log_r
                    for left, right in zip(magnitudes, magnitudes[1:])]
    result["local_orders"] = local_orders
    if any(not math.isfinite(order) for order in local_orders):
        return diagnose("numerical_range", "An observed order exceeds floating-point range.")
    if any(order <= 0.0 for order in local_orders):
        return diagnose("nonconvergent", "Adjacent difference magnitudes do not consistently decrease; no positive-order estimate is accepted.")
    order_tolerance = max(ORDER_ATOL, ORDER_RTOL * max(abs(order) for order in local_orders))
    result["order_consistency_tolerance"] = order_tolerance
    if max(local_orders) - min(local_orders) > order_tolerance:
        return diagnose("inconsistent_order", "Local orders vary too much; the sequence may be pre-asymptotic or mix error regimes.")

    order = local_orders[-1]
    exponent = order * log_r
    # expm1 avoids loss of significance for low order; its reciprocal version
    # avoids overflow for very rapidly shrinking differences.
    if exponent > 700.0:
        inverse_denominator = math.exp(-exponent) / (-math.expm1(-exponent))
        signed_correction = -differences[-1] * inverse_denominator
    else:
        signed_correction = -differences[-1] / math.expm1(exponent)
    estimated_error = abs(signed_correction)
    extrapolated = values[-1] + signed_correction
    if not math.isfinite(estimated_error) or not math.isfinite(extrapolated):
        return diagnose("numerical_range", "The extrapolation exceeds floating-point range.")
    if estimated_error == 0.0:
        return diagnose("numerical_range", "The error estimate underflows to zero; it must not be reported as exact convergence.")
    result.update(observed_order=order, fine_grid_error_estimate=estimated_error,
                  extrapolated_value=extrapolated)
    return diagnose("apparent_convergence", "All sequence checks pass; a finest-triple Richardson estimate is applicable under the stated assumptions.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    biquad = commands.add_parser("biquad", help="Check the poles of 1+a1*z^-1+a2*z^-2")
    biquad.add_argument("--a1", required=True)
    biquad.add_argument("--a2", required=True)
    convergence = commands.add_parser("convergence", help="Diagnose an h,value CSV in coarse-to-fine order")
    convergence.add_argument("csv", help="CSV containing h,value columns and at least three rows")
    args = parser.parse_args(argv)
    try:
        if args.command == "biquad":
            result = check_biquad(args.a1, args.a2)
        else:
            result = check_convergence(read_convergence_csv(args.csv))
    except (ValueError, OSError, UnicodeError, csv.Error) as exc:
        error = {"check": args.command, "status": "invalid_input", "reason": str(exc)}
        print(json.dumps(error, ensure_ascii=False, allow_nan=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
