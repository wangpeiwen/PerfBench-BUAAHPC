import unittest

from perfbench.analysis.metrics import calculate_parallelism


class MetricsGranularityTests(unittest.TestCase):
    def test_node_granularity_counts_nodes(self):
        info = calculate_parallelism("DCU Z100", 2, "node")

        self.assertEqual(info["core_num"], 2)
        self.assertEqual(info["granularity"], "node")
        self.assertEqual(info["method"], "node\\_num")

    def test_board_granularity_counts_accelerator_cards(self):
        info = calculate_parallelism("DCU Z100", 2, "board")

        self.assertEqual(info["core_num"], 8)
        self.assertEqual(info["granularity"], "board")

    def test_core_granularity_counts_card_internal_cores(self):
        info = calculate_parallelism("DCU Z100", 2, "core")

        self.assertEqual(info["core_num"], 2304)
        self.assertEqual(info["granularity"], "core")
        self.assertEqual(info["method"], "node\\_num \\times 4 \\times 288")


if __name__ == "__main__":
    unittest.main()
