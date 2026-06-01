import unittest

from perfbench.analysis.scale_compliance import (
    aggregate_scale_compliance,
    calculate_scale_compliance,
)


class ScaleComplianceTests(unittest.TestCase):
    def test_calculates_coverage_from_dcu_samples(self):
        records = [
            {"node": "n1", "sample_idx": 1, "dcu_id": "0", "dcu_pct": "20%"},
            {"node": "n1", "sample_idx": 1, "dcu_id": "1", "dcu_pct": "30%"},
            {"node": "n2", "sample_idx": 1, "dcu_id": "0", "dcu_pct": "40%"},
            {"node": "n2", "sample_idx": 1, "dcu_id": "1", "dcu_pct": "0%"},
            {"node": "n1", "sample_idx": 2, "dcu_id": "0", "dcu_pct": "25%"},
            {"node": "n1", "sample_idx": 2, "dcu_id": "1", "dcu_pct": "35%"},
            {"node": "n2", "sample_idx": 2, "dcu_id": "0", "dcu_pct": "45%"},
            {"node": "n2", "sample_idx": 2, "dcu_id": "1", "dcu_pct": "55%"},
        ]

        result = calculate_scale_compliance(
            records,
            expected_devices=4,
            active_util_threshold=10.0,
            scale_fraction_threshold=0.8,
            coverage_threshold=0.5,
        )

        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(result["active_sample_count"], 1)
        self.assertAlmostEqual(result["coverage"], 0.5)
        self.assertTrue(result["compliance_pass"])
        self.assertAlmostEqual(result["mean_active_fraction"], 0.875)

    def test_missing_devices_count_against_expected_scale(self):
        records = [
            {"node": "n1", "sample_idx": 1, "dcu_id": "0", "dcu_pct": "20%"},
            {"node": "n1", "sample_idx": 1, "dcu_id": "1", "dcu_pct": "20%"},
        ]

        result = calculate_scale_compliance(
            records,
            expected_devices=4,
            active_util_threshold=10.0,
            scale_fraction_threshold=0.8,
            coverage_threshold=0.9,
        )

        self.assertAlmostEqual(result["mean_active_fraction"], 0.5)
        self.assertFalse(result["compliance_pass"])

    def test_aggregates_per_run_results(self):
        first = {"coverage": 1.0, "mean_active_fraction": 1.0,
                 "min_active_fraction": 1.0, "max_active_fraction": 1.0,
                 "expected_devices": 4, "sample_count": 2,
                 "sampled_nodes": 2, "sampled_devices": 4,
                 "active_util_threshold": 10.0,
                 "scale_fraction_threshold": 0.8,
                 "coverage_threshold": 0.9,
                 "compliance_pass": True}
        second = dict(first)
        second["coverage"] = 0.5
        second["mean_active_fraction"] = 0.75
        second["compliance_pass"] = False

        summary = aggregate_scale_compliance([first, second])

        self.assertEqual(summary["run_count"], 2)
        self.assertEqual(summary["pass_count"], 1)
        self.assertAlmostEqual(summary["pass_rate"], 0.5)
        self.assertFalse(summary["compliance_pass"])
        self.assertAlmostEqual(summary["coverage_mean"], 0.75)


if __name__ == "__main__":
    unittest.main()
