from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from tests.test_cses_hpm_upload_session_api import make_client, upload_files, write_hpm5, write_hpm6


def write_hpm5_with_mag_coords(path: Path, times: list[int], offset: float = 0.0) -> None:
    n = len(times)
    with h5py.File(path, "w") as h5:
        h5.create_dataset("UTC_TIME", data=np.asarray(times, dtype=np.int64).reshape(n, 1))
        b = h5.create_dataset("B_FGM", data=(np.arange(n * 3, dtype=np.float64).reshape(n, 3) + offset))
        b.attrs["Units"] = "nT"
        h5.create_dataset("GEO_LAT", data=np.linspace(-5, 5, n).reshape(n, 1))
        h5.create_dataset("GEO_LON", data=np.linspace(100, 110, n).reshape(n, 1))
        alt = h5.create_dataset("ALTITUDE", data=np.linspace(500, 505, n).reshape(n, 1))
        alt.attrs["Units"] = "km"
        h5.create_dataset("MAG_LAT", data=np.linspace(-2, 2, n).reshape(n, 1))
        h5.create_dataset("MAG_LON", data=np.linspace(80, 84, n).reshape(n, 1))
        h5.create_dataset("FLAG_MT", data=np.asarray([0, 0, 1, 1][:n], dtype=np.int32).reshape(n, 1))
        h5.create_dataset("FLAG_SHW", data=np.zeros((n, 1), dtype=np.int32))
        h5.create_dataset("FLAG_TBB", data=np.ones((n, 1), dtype=np.int32))


class CsesHpmStatisticsApiTest(unittest.TestCase):
    def test_single_hpm5_outputs_component_and_total_field_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sample = root / "CSES_01_HPM_5_L02_A2_1_20230419_235500_20230419_235503_000.h5"
            write_hpm5_with_mag_coords(
                sample,
                [20230419235500000, 20230419235501000, 20230419235502000, 20230419235503000],
            )
            client = make_client(root)
            upload = upload_files(client, [sample]).json()

            response = client.post(f"/api/sessions/{upload['upload_session_id']}/statistics", json={})

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["session_id"], upload["upload_session_id"])
            self.assertEqual(payload["product_type_status"]["status"], "single")
            magnetic = payload["overall_statistics"]["magnetic"]["variables"]
            self.assertEqual(set(magnetic), {"Bx", "By", "Bz", "B_abs"})
            self.assertEqual(magnetic["Bx"]["finite_count"], 4)
            self.assertEqual(magnetic["Bx"]["min"], 0.0)
            self.assertEqual(magnetic["Bx"]["max"], 9.0)
            self.assertEqual(magnetic["Bx"]["mean"], 4.5)
            self.assertAlmostEqual(magnetic["B_abs"]["min"], np.sqrt(5.0))
            self.assertEqual(payload["overall_statistics"]["position"]["variables"]["MAG_LAT"]["finite_count"], 4)
            self.assertEqual(payload["quality_flag_statistics"]["/FLAG_MT"]["value_counts"], {"0": 2, "1": 2})
            self.assertEqual(payload["processing_summary"]["final_sample_count"], 4)
            self.assertTrue(Path(payload["artifacts"]["statistics_json"]["path"]).exists())
            self.assertTrue(Path(payload["artifacts"]["statistics_summary_csv"]["path"]).exists())
            self.assertTrue(Path(payload["artifacts"]["manifest_json"]["path"]).exists())

    def test_single_hpm6_outputs_scalar_magnetic_statistics_without_components(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sample = root / "CSES_01_HPM_6_L02_A2_1_20230419_235500_20230419_235503_000.h5"
            write_hpm6(sample, [20230419235500000, 20230419235501000, 20230419235502000, 20230419235503000])
            client = make_client(root)
            upload = upload_files(client, [sample]).json()

            payload = client.post(f"/api/sessions/{upload['upload_session_id']}/statistics", json={}).json()

            magnetic = payload["overall_statistics"]["magnetic"]["variables"]
            self.assertEqual(set(magnetic), {"scalar_B"})
            self.assertNotIn("Bx", magnetic)
            self.assertEqual(magnetic["scalar_B"]["finite_count"], 4)
            self.assertEqual(payload["per_file_statistics"][0]["magnetic"]["variables"]["scalar_B"]["finite_count"], 4)

    def test_duplicate_file_statistics_use_deduped_samples_and_record_dedupe_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sample = root / "CSES_01_HPM_5_L02_A2_1_20230419_235500_20230419_235503_000.h5"
            duplicate = root / "copy_of_same.h5"
            write_hpm5(sample, [20230419235500000, 20230419235501000, 20230419235502000, 20230419235503000])
            duplicate.write_bytes(sample.read_bytes())
            client = make_client(root)
            upload = upload_files(client, [sample, duplicate]).json()

            payload = client.post(f"/api/sessions/{upload['upload_session_id']}/statistics", json={}).json()

            self.assertEqual(payload["processing_summary"]["uploaded_file_count"], 2)
            self.assertEqual(payload["processing_summary"]["unique_file_count"], 1)
            self.assertEqual(payload["processing_summary"]["duplicate_file_count"], 1)
            self.assertEqual(payload["processing_summary"]["raw_sample_count"], 8)
            self.assertEqual(payload["processing_summary"]["merged_sample_count"], 4)
            self.assertEqual(payload["processing_summary"]["duplicate_time_removed_count"], 4)
            self.assertEqual(payload["overall_statistics"]["magnetic"]["variables"]["Bx"]["finite_count"], 4)

    def test_out_of_order_upload_statistics_follow_utc_time_sort(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            late = root / "CSES_01_HPM_5_L02_A2_2_20230420_000000_20230420_000002_000.h5"
            early = root / "CSES_01_HPM_5_L02_A2_1_20230419_235500_20230419_235502_000.h5"
            write_hpm5(late, [20230420000000000, 20230420000001000, 20230420000002000], offset=100)
            write_hpm5(early, [20230419235500000, 20230419235501000, 20230419235502000])
            client = make_client(root)
            upload = upload_files(client, [late, early]).json()

            payload = client.post(f"/api/sessions/{upload['upload_session_id']}/statistics", json={}).json()

            self.assertEqual(payload["time_range"]["start_time"], "2023-04-19T23:55:00Z")
            self.assertEqual(payload["time_range"]["end_time"], "2023-04-20T00:00:02Z")
            self.assertTrue(payload["processing_summary"]["sorted_by_time"])

    def test_discontinuous_upload_statistics_are_reported_per_segment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "CSES_01_HPM_5_L02_A2_1_20230419_235500_20230419_235502_000.h5"
            second = root / "CSES_01_HPM_5_L02_A2_2_20230420_010000_20230420_010002_000.h5"
            write_hpm5(first, [20230419235500000, 20230419235501000, 20230419235502000])
            write_hpm5(second, [20230420010000000, 20230420010001000, 20230420010002000], offset=100)
            client = make_client(root)
            upload = upload_files(client, [second, first]).json()

            payload = client.post(f"/api/sessions/{upload['upload_session_id']}/statistics", json={}).json()

            self.assertEqual(payload["processing_summary"]["segment_count"], 2)
            self.assertEqual(len(payload["per_segment_statistics"]), 2)
            self.assertEqual(payload["per_segment_statistics"][0]["time_coverage"]["sample_count"], 3)
            self.assertEqual(payload["per_segment_statistics"][1]["time_coverage"]["sample_count"], 3)

    def test_crop_range_with_no_samples_returns_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sample = root / "CSES_01_HPM_5_L02_A2_1_20230419_235500_20230419_235503_000.h5"
            write_hpm5(sample, [20230419235500000, 20230419235501000, 20230419235502000, 20230419235503000])
            client = make_client(root)
            upload = upload_files(client, [sample]).json()

            response = client.post(
                f"/api/sessions/{upload['upload_session_id']}/statistics",
                json={"crop_range": {"start": "2023-04-20T01:00:00Z", "end": "2023-04-20T01:10:00Z"}},
            )

            self.assertEqual(response.status_code, 400)
            self.assertIn("当前裁剪范围内无有效数据", response.text)


if __name__ == "__main__":
    unittest.main()
