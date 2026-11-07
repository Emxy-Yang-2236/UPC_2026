"""Behavioral regression tests for physical/numerical diagnostic boundaries.

Run: python3 -m unittest discover -s tests -p test_numerical_checks.py -v
"""

import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/numerical_checks.py"
SPEC = importlib.util.spec_from_file_location("numerical_checks", SCRIPT)
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)


class BiquadTests(unittest.TestCase):
    def test_published_rounded_coefficients_are_unstable(self):
        result = checks.check_biquad(-1.9, 0.88)
        self.assertFalse(result["stable"])
        self.assertEqual(result["status"], "unstable")
        self.assertAlmostEqual(result["poles"][0]["real"], 1.1)
        self.assertAlmostEqual(result["poles"][1]["real"], 0.8)
        self.assertAlmostEqual(result["max_radius"], 1.1)
        self.assertAlmostEqual(result["stability_margin"], -0.1)

    def test_stable_complex_pair(self):
        result = checks.check_biquad(-1.5, 0.7)
        self.assertTrue(result["stable"])
        self.assertAlmostEqual(result["max_radius"], math.sqrt(0.7))
        roots = [complex(p["real"], p["imag"]) for p in result["poles"]]
        self.assertAlmostEqual(roots[0].real, roots[1].real)
        self.assertAlmostEqual(roots[0].imag, -roots[1].imag)
        for root in roots:
            self.assertAlmostEqual(abs(root * root - 1.5 * root + 0.7), 0.0)

    def test_unit_circle_is_not_asymptotically_stable(self):
        for coefficients in [(-1.0, 0.0), (0.0, 1.0)]:
            with self.subTest(coefficients=coefficients):
                result = checks.check_biquad(*coefficients)
                self.assertFalse(result["stable"])
                self.assertEqual(result["status"], "boundary")

    def test_zero_roots(self):
        result = checks.check_biquad(0.0, 0.0)
        self.assertTrue(result["stable"])
        self.assertEqual(result["stability_margin"], 1.0)

    def test_unequal_roots_do_not_lose_the_small_root(self):
        result = checks.check_biquad(-1e100, 1.0)
        roots = [p["real"] for p in result["poles"]]
        self.assertAlmostEqual(roots[0] * roots[1], 1.0)
        self.assertGreater(roots[1], 0.0)

    def test_invalid_coefficients(self):
        for value in ["abc", "NaN", "inf", "-inf", None]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    checks.check_biquad(value, 0.7)


class ConvergenceTests(unittest.TestCase):
    def assert_no_accepted_estimate(self, result, status):
        self.assertEqual(result["status"], status)
        self.assertIsNone(result["observed_order"])
        self.assertIsNone(result["fine_grid_error_estimate"])
        self.assertIsNone(result["extrapolated_value"])
        self.assertTrue(result["reason"])

    def test_fourth_order_sequence_and_known_fine_grid_error(self):
        hs = [1.0, 0.5, 0.25, 0.125]
        result = checks.check_convergence([(h, 3.0 + 2.0 * h**4) for h in hs])
        self.assertEqual(result["status"], "apparent_convergence")
        self.assertAlmostEqual(result["observed_order"], 4.0)
        self.assertEqual(len(result["local_orders"]), 2)
        self.assertAlmostEqual(result["fine_grid_error_estimate"], 2.0 * hs[-1]**4)
        self.assertAlmostEqual(result["extrapolated_value"], 3.0)
        self.assertIn("does not prove", result["limitation"])

    def test_monotone_convergence_from_below(self):
        result = checks.check_convergence([(h, 2.0 - h**2) for h in [1.0, 0.5, 0.25]])
        self.assertEqual(result["status"], "apparent_convergence")
        self.assertAlmostEqual(result["observed_order"], 2.0)
        self.assertAlmostEqual(result["extrapolated_value"], 2.0)

    def test_plateau_does_not_mean_exact_solution(self):
        result = checks.check_convergence([(1.0, 4.0), (0.5, 4.0), (0.25, 4.0)])
        self.assert_no_accepted_estimate(result, "plateau")

    def test_roundoff_plateau(self):
        ulp = math.ulp(1.0)
        result = checks.check_convergence([(1.0, 1.0 + 4 * ulp), (0.5, 1.0 + 2 * ulp), (0.25, 1.0 + ulp)])
        self.assert_no_accepted_estimate(result, "roundoff_limited")

    def test_diverging_difference_magnitudes(self):
        result = checks.check_convergence([(1.0, 1.0), (0.5, 2.0), (0.25, 4.0)])
        self.assert_no_accepted_estimate(result, "nonconvergent")

    def test_constant_differences_are_not_positive_order(self):
        result = checks.check_convergence([(1.0, 3.0), (0.5, 2.0), (0.25, 1.0)])
        self.assert_no_accepted_estimate(result, "nonconvergent")

    def test_oscillating_sequence_is_not_richardson_qualified(self):
        result = checks.check_convergence([(1.0, 1.0), (0.5, 0.5), (0.25, 0.75)])
        self.assert_no_accepted_estimate(result, "oscillatory")

    def test_non_geometric_refinement(self):
        result = checks.check_convergence([(1.0, 1.0), (0.5, 0.25), (0.2, 0.04)])
        self.assert_no_accepted_estimate(result, "non_geometric")

    def test_h_order_is_not_silently_sorted(self):
        result = checks.check_convergence([(1.0, 1.0), (0.25, 0.0625), (0.5, 0.25)])
        self.assert_no_accepted_estimate(result, "invalid_grid")

    def test_all_triples_must_be_consistent(self):
        result = checks.check_convergence([(8.0, 22.0), (4.0, 6.0), (2.0, 2.0), (1.0, 0.0)])
        self.assert_no_accepted_estimate(result, "inconsistent_order")
        self.assertAlmostEqual(result["local_orders"][0], 2.0)
        self.assertAlmostEqual(result["local_orders"][1], 1.0)

    def test_invalid_h_or_value(self):
        for bad_h in [0.0, -1.0, math.nan, math.inf, "x"]:
            with self.subTest(h=bad_h):
                with self.assertRaises(ValueError):
                    checks.check_convergence([(1.0, 1.0), (0.5, 0.25), (bad_h, 0.0625)])
        for bad_value in [math.nan, math.inf, "x"]:
            with self.subTest(value=bad_value):
                with self.assertRaises(ValueError):
                    checks.check_convergence([(1.0, 1.0), (0.5, 0.25), (0.25, bad_value)])

    def test_at_least_three_rows(self):
        with self.assertRaises(ValueError):
            checks.check_convergence([(1.0, 1.0), (0.5, 0.25)])


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False)

    def test_unstable_filter_is_a_successful_diagnostic_command(self):
        completed = self.run_cli("biquad", "--a1", "-1.9", "--a2", ".88")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(json.loads(completed.stdout)["stable"])

    def test_nonnumeric_and_nonfinite_coefficients_fail_clearly(self):
        for value in ["nonsense", "NaN", "inf"]:
            with self.subTest(value=value):
                completed = self.run_cli("biquad", "--a1", value, "--a2", ".88")
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stdout, "")
                error = json.loads(completed.stderr)
                self.assertEqual(error["status"], "invalid_input")
                self.assertIn("finite", error["reason"])

    def test_csv_success_and_invalid_rows(self):
        examples = [
            ("h,value\n1,5\n0.5,3.125\n0.25,3.0078125\n", 0, "apparent_convergence"),
            ("h,value\n1,1\n0.5,NaN\n0.25,2\n", 2, "invalid_input"),
            ("h,value\n1,1\n0.5,abc\n0.25,2\n", 2, "invalid_input"),
            ("h,wrong\n1,1\n0.5,2\n0.25,3\n", 2, "invalid_input"),
            ("h,value\n1,1\n0.5,2\n", 2, "invalid_input"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sequence.csv"
            for contents, exit_code, status in examples:
                with self.subTest(contents=contents):
                    path.write_text(contents, encoding="utf-8")
                    completed = self.run_cli("convergence", str(path))
                    self.assertEqual(completed.returncode, exit_code, completed.stderr)
                    report = json.loads(completed.stdout if exit_code == 0 else completed.stderr)
                    self.assertEqual(report["status"], status)

    def test_csv_nongeometric_is_a_successful_diagnostic_command(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sequence.csv"
            path.write_text("h,value\n1,1\n0.5,0.25\n0.2,0.04\n", encoding="utf-8")
            completed = self.run_cli("convergence", str(path))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["status"], "non_geometric")


if __name__ == "__main__":
    unittest.main()
