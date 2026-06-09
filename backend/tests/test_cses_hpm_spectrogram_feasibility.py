from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import numpy as np


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "test_cses_hpm_spectrogram_feasibility.py"
SPEC = importlib.util.spec_from_file_location("cses_hpm_spectrogram_feasibility", SCRIPT_PATH)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CsesHpmSpectrogramFeasibilityTest(unittest.TestCase):
    def test_parse_compact_utc_time_millis(self) -> None:
        parsed = MODULE.parse_cses_utc_time(
            np.array([20230420004305000, 20230420004306000], dtype=np.int64)
        )

        self.assertEqual(parsed["success_fraction"], 1.0)
        self.assertEqual(parsed["iso"][0], "2023-04-20T00:43:05+00:00")
        self.assertEqual(parsed["unix_seconds"][1] - parsed["unix_seconds"][0], 1.0)

    def test_cadence_summary_detects_stable_one_second_series(self) -> None:
        time_s = np.arange(0, 20, dtype=float)

        summary = MODULE.summarize_cadence(time_s)

        self.assertTrue(summary["monotonic_increasing"])
        self.assertEqual(summary["duplicate_timestamp_count"], 0)
        self.assertEqual(summary["large_gap_count"], 0)
        self.assertEqual(summary["diff_seconds"]["median"], 1.0)
        self.assertTrue(summary["stable_for_stft"])

    def test_choose_stft_params_requires_minimum_resolution_but_stays_within_file(self) -> None:
        params, warnings = MODULE.choose_stft_params(
            sample_count=2064,
            sample_rate_hz=1.0,
            freq_min_mhz=1.0,
        )

        self.assertEqual(params["nperseg"], 2048)
        self.assertEqual(params["noverlap"], 1024)
        self.assertTrue(any("lowest requested frequency" in item for item in warnings))

    def test_pc5_duration_warning_for_short_single_file(self) -> None:
        warnings = MODULE.pc5_duration_warnings(duration_seconds=2063.0)

        self.assertTrue(any("1.6 mHz" in item for item in warnings))
        self.assertTrue(any("single-file Pc5 interpretation" in item for item in warnings))

    def test_single_stft_time_bin_gets_drawable_edges(self) -> None:
        edges = MODULE.stft_time_edges_seconds(np.array([1024.0]))

        np.testing.assert_allclose(edges, np.array([0.0, 2048.0]))

    def test_single_stft_time_bin_warning(self) -> None:
        warnings = MODULE.stft_time_bin_warnings({"B1": {"time_bin_count": 1}})

        self.assertTrue(any("only 1 time bin" in item for item in warnings))


if __name__ == "__main__":
    unittest.main()
