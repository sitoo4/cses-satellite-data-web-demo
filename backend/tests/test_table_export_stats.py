from __future__ import annotations

import unittest

import numpy as np

from app.services.table_export import numeric_stats_extended


class TableExportStatsTest(unittest.TestCase):
    def test_numeric_stats_extended_reports_all_missing_component_ratio(self) -> None:
        result = numeric_stats_extended(
            "/B_FGM",
            np.array(
                [
                    [np.nan, 1.0],
                    [np.nan, 2.0],
                    [np.nan, 3.0],
                ],
                dtype=np.float64,
            ),
        )

        first_component = result["stats"][0]
        self.assertEqual(first_component["count"], 3)
        self.assertEqual(first_component["finite_count"], 0)
        self.assertIsNone(first_component["median"])
        self.assertEqual(first_component["missing_ratio"], 1.0)


if __name__ == "__main__":
    unittest.main()
