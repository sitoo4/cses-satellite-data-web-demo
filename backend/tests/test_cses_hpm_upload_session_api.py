from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np
from fastapi.testclient import TestClient

from app.main import create_app


def write_hpm5(path: Path, times: list[int], offset: float = 0.0) -> None:
    n = len(times)
    with h5py.File(path, "w") as h5:
        utc = h5.create_dataset("UTC_TIME", data=np.asarray(times, dtype=np.int64).reshape(n, 1))
        utc.attrs["Units"] = "yyyymmddhhmmssmmm"
        b = h5.create_dataset("B_FGM", data=(np.arange(n * 3, dtype=np.float64).reshape(n, 3) + offset))
        b.attrs["Units"] = "nT"
        h5.create_dataset("GEO_LAT", data=np.linspace(-5, 5, n).reshape(n, 1))
        h5.create_dataset("GEO_LON", data=np.linspace(100, 110, n).reshape(n, 1))
        h5.create_dataset("ALTITUDE", data=np.linspace(500, 505, n).reshape(n, 1))
        h5.create_dataset("FLAG_MT", data=np.asarray([0, 0, 1, 1][:n], dtype=np.int32).reshape(n, 1))
        h5.create_dataset("FLAG_SHW", data=np.zeros((n, 1), dtype=np.int32))
        h5.create_dataset("FLAG_TBB", data=np.ones((n, 1), dtype=np.int32))


def write_hpm5_with_orbit(path: Path, times: list[int], lat: list[float], lon: list[float], alt: list[float], offset: float = 0.0) -> None:
    n = len(times)
    with h5py.File(path, "w") as h5:
        utc = h5.create_dataset("UTC_TIME", data=np.asarray(times, dtype=np.int64).reshape(n, 1))
        utc.attrs["Units"] = "yyyymmddhhmmssmmm"
        b = h5.create_dataset("B_FGM", data=(np.arange(n * 3, dtype=np.float64).reshape(n, 3) + offset))
        b.attrs["Units"] = "nT"
        h5.create_dataset("GEO_LAT", data=np.asarray(lat, dtype=np.float64).reshape(n, 1))
        h5.create_dataset("GEO_LON", data=np.asarray(lon, dtype=np.float64).reshape(n, 1))
        h5.create_dataset("ALTITUDE", data=np.asarray(alt, dtype=np.float64).reshape(n, 1))
        h5.create_dataset("FLAG_MT", data=np.zeros((n, 1), dtype=np.int32))
        h5.create_dataset("FLAG_SHW", data=np.zeros((n, 1), dtype=np.int32))
        h5.create_dataset("FLAG_TBB", data=np.zeros((n, 1), dtype=np.int32))


def write_hpm6(path: Path, times: list[int]) -> None:
    n = len(times)
    with h5py.File(path, "w") as h5:
        h5.create_dataset("UTC_TIME", data=np.asarray(times, dtype=np.int64).reshape(n, 1))
        a211 = h5.create_dataset("A211", data=np.linspace(20000, 20020, n).reshape(n, 1))
        a211.attrs["Units"] = "nT"
        h5.create_dataset("GEO_LAT", data=np.linspace(10, 11, n).reshape(n, 1))
        h5.create_dataset("GEO_LON", data=np.linspace(20, 21, n).reshape(n, 1))
        h5.create_dataset("ALTITUDE", data=np.linspace(510, 512, n).reshape(n, 1))
        h5.create_dataset("FLAG_N3", data=np.asarray([0, 2, 2, 2][:n], dtype=np.int32).reshape(n, 1))


def make_client(root: Path) -> TestClient:
    config_path = root / "local_config.json"
    config_path.write_text(
        json.dumps(
            {
                "cses_hpm_root": str(root / "unused_hpm_root"),
                "outputs_root": str(root / "outputs"),
            }
        ),
        encoding="utf-8",
    )
    return TestClient(create_app(config_path=config_path))


def upload_files(client: TestClient, paths: list[Path]):
    opened = [path.open("rb") for path in paths]
    try:
        files = [("files", (path.name, handle, "application/x-hdf5")) for path, handle in zip(paths, opened, strict=True)]
        return client.post("/api/cses-hpm/uploads", files=files)
    finally:
        for handle in opened:
            handle.close()


class CsesHpmUploadSessionApiTest(unittest.TestCase):
    def test_single_hpm5_upload_returns_metadata_and_single_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sample = root / "CSES_01_HPM_5_L02_A2_1_20230419_235500_20230419_235503_000.h5"
            write_hpm5(
                sample,
                [20230419235500000, 20230419235501000, 20230419235502000, 20230419235503000],
            )
            client = make_client(root)

            response = upload_files(client, [sample])

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["mode"], "single")
            self.assertTrue(payload["upload_session_id"])
            self.assertEqual(payload["merged_time_range"]["start"], "2023-04-19T23:55:00Z")
            self.assertEqual(payload["merged_time_range"]["end"], "2023-04-19T23:55:03Z")
            self.assertEqual(len(payload["segments"]), 1)
            record = payload["per_file_records"][0]
            self.assertEqual(record["hpm_product"], "HPM_5")
            self.assertTrue(record["has_vector_magnetic"])
            self.assertFalse(record["has_scalar_magnetic"])
            self.assertEqual(record["quality_flag_summary"]["/FLAG_MT"]["distribution"], {"0": 2, "1": 2})
            self.assertIn("解析成功", "\n".join(payload["run_log"]))

    def test_duplicate_file_upload_reports_duplicate_file_and_dedupes_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sample = root / "CSES_01_HPM_5_L02_A2_1_20230419_235500_20230419_235503_000.h5"
            duplicate = root / "copy_of_same.h5"
            write_hpm5(
                sample,
                [20230419235500000, 20230419235501000, 20230419235502000, 20230419235503000],
            )
            duplicate.write_bytes(sample.read_bytes())
            client = make_client(root)

            response = upload_files(client, [sample, duplicate])

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["mode"], "batch")
            self.assertEqual(payload["dedupe"]["duplicate_file_count"], 1)
            self.assertEqual(payload["dedupe"]["duplicate_sample_count"], 4)
            self.assertEqual(payload["sample_count"], 4)
            self.assertIn("重复文件去除", "\n".join(payload["run_log"]))

    def test_out_of_order_upload_is_sorted_by_parsed_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            late = root / "CSES_01_HPM_5_L02_A2_2_20230420_000000_20230420_000002_000.h5"
            early = root / "CSES_01_HPM_5_L02_A2_1_20230419_235500_20230419_235502_000.h5"
            write_hpm5(late, [20230420000000000, 20230420000001000, 20230420000002000], offset=100)
            write_hpm5(early, [20230419235500000, 20230419235501000, 20230419235502000])
            client = make_client(root)

            response = upload_files(client, [late, early])

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["merged_time_range"]["start"], "2023-04-19T23:55:00Z")
            self.assertEqual(payload["merged_time_range"]["end"], "2023-04-20T00:00:02Z")
            self.assertEqual(payload["sorted_files"][0]["filename"], early.name)
            self.assertEqual(payload["sorted_files"][1]["filename"], late.name)
            self.assertGreaterEqual(len(payload["segments"]), 2)
            self.assertIn("时间排序完成", "\n".join(payload["run_log"]))

    def test_upload_session_returns_beijing_display_range_and_plot_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "CSES_01_HPM_5_L02_A2_1_20230419_230000_20230419_230100_000.h5"
            second = root / "CSES_01_HPM_5_L02_A2_2_20230420_000000_20230420_000100_000.h5"
            third = root / "CSES_01_HPM_5_L02_A2_3_20230420_020000_20230420_020100_000.h5"
            write_hpm5(first, [20230419230000000, 20230419230100000])
            write_hpm5(second, [20230419235000000, 20230419235100000])
            write_hpm5(third, [20230420020000000, 20230420020100000])
            client = make_client(root)

            payload = upload_files(client, [third, first, second]).json()

            self.assertEqual(payload["display_time_zone"], "Asia/Shanghai")
            self.assertEqual(payload["display_time_range"]["start"], "2023-04-20 07:00")
            self.assertEqual(payload["display_time_range"]["end"], "2023-04-20 10:01")
            self.assertEqual(payload["crop_options"]["start"]["years"], [2023])
            self.assertEqual(payload["crop_options"]["start"]["months"], [4])
            self.assertEqual(payload["crop_options"]["start"]["days"], [20])
            self.assertEqual(len(payload["plot_groups"]), 1)
            self.assertEqual(payload["plot_groups"][0]["segment_ids"], ["segment_1", "segment_2", "segment_3"])
            self.assertEqual(payload["plot_groups"][0]["reason"], "same_beijing_day_or_gap_lt_60min")
            self.assertIn("绘图分组数量: 1", "\n".join(payload["run_log"]))

    def test_plot_groups_split_across_beijing_days_when_gap_is_large(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "CSES_01_HPM_5_L02_A2_1_20230419_150000_20230419_150100_000.h5"
            second = root / "CSES_01_HPM_5_L02_A2_2_20230419_173000_20230419_173100_000.h5"
            write_hpm5(first, [20230419150000000, 20230419150100000])
            write_hpm5(second, [20230419173000000, 20230419173100000])
            client = make_client(root)

            payload = upload_files(client, [second, first]).json()

            self.assertEqual(payload["display_time_range"]["start"], "2023-04-19 23:00")
            self.assertEqual(payload["display_time_range"]["end"], "2023-04-20 01:31")
            self.assertEqual(len(payload["segments"]), 2)
            self.assertEqual(len(payload["plot_groups"]), 2)
            self.assertEqual(payload["plot_groups"][0]["segment_ids"], ["segment_1"])
            self.assertEqual(payload["plot_groups"][1]["segment_ids"], ["segment_2"])

    def test_orbit_html_marks_start_points_and_curved_gap_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "CSES_01_HPM_5_L02_A2_1_20230419_230000_20230419_230100_000.h5"
            second = root / "CSES_01_HPM_5_L02_A2_2_20230419_232000_20230419_232100_000.h5"
            write_hpm5_with_orbit(
                first,
                [20230419230000000, 20230419230100000],
                [0.0, 5.0],
                [10.0, 15.0],
                [500.0, 501.0],
            )
            write_hpm5_with_orbit(
                second,
                [20230419232000000, 20230419232100000],
                [8.0, 12.0],
                [20.0, 25.0],
                [502.0, 503.0],
                offset=100,
            )
            client = make_client(root)
            upload = upload_files(client, [first, second]).json()

            orbit = client.post(
                f"/api/cses-hpm/uploads/{upload['upload_session_id']}/plot",
                json={"plot_type": "orbit"},
            ).json()

            self.assertEqual(orbit["status"], "ok")
            self.assertEqual(len(orbit["plot_groups"]), 1)
            orbit_html = Path(orbit["artifact"]["path"]).read_text(encoding="utf-8")
            self.assertNotIn("START", orbit_html)
            self.assertNotIn("END $", orbit_html)
            self.assertIn("gap_links", orbit_html)
            self.assertIn("drawCurvedGapLinks", orbit_html)
            self.assertIn("drawOrbitStroke", orbit_html)
            self.assertIn("segmentHighlightColor", orbit_html)
            self.assertIn("earthTextureUrl", orbit_html)
            self.assertIn("drawTexturedEarth", orbit_html)
            self.assertIn("createImageData", orbit_html)
            self.assertIn("createRadialGradient", orbit_html)
            self.assertIn("#d94b3d", orbit_html)
            self.assertIn("rgba(244,236,216,.94)", orbit_html)
            self.assertIn("rgba(42,41,35,.86)", orbit_html)
            self.assertIn("setLineDash([6, 6])", orbit_html)
            self.assertIn("北京时间", orbit_html)
            self.assertIn("display_time", orbit_html)

    def test_mixed_hpm5_hpm6_marks_magnetic_plot_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hpm5 = root / "CSES_01_HPM_5_L02_A2_1_20230419_235500_20230419_235502_000.h5"
            hpm6 = root / "CSES_01_HPM_6_L02_A2_2_20230420_000000_20230420_000002_000.h5"
            write_hpm5(hpm5, [20230419235500000, 20230419235501000, 20230419235502000])
            write_hpm6(hpm6, [20230420000000000, 20230420000001000, 20230420000002000])
            client = make_client(root)
            upload = upload_files(client, [hpm5, hpm6]).json()

            plot = client.post(
                f"/api/cses-hpm/uploads/{upload['upload_session_id']}/plot",
                json={"plot_type": "magnetic"},
            )

            self.assertEqual(plot.status_code, 200)
            payload = plot.json()
            self.assertEqual(payload["status"], "unavailable")
            self.assertIn("混合", payload["reason"])

    def test_hpm6_single_file_uses_scalar_field_for_magnetic_plot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sample = root / "CSES_01_HPM_6_L02_A2_1_20230419_235500_20230419_235503_000.h5"
            write_hpm6(
                sample,
                [20230419235500000, 20230419235501000, 20230419235502000, 20230419235503000],
            )
            client = make_client(root)
            upload = upload_files(client, [sample]).json()

            response = client.post(
                f"/api/cses-hpm/uploads/{upload['upload_session_id']}/plot",
                json={"plot_type": "magnetic"},
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["artifact"]["media_type"], "image/png")
            self.assertTrue(Path(payload["artifact"]["path"]).exists())

    def test_hpm5_upload_generates_magnetic_png_orbit_html_and_export_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sample = root / "CSES_01_HPM_5_L02_A2_1_20230419_235500_20230419_235503_000.h5"
            write_hpm5(
                sample,
                [20230419235500000, 20230419235501000, 20230419235502000, 20230419235503000],
            )
            client = make_client(root)
            upload = upload_files(client, [sample]).json()
            session_id = upload["upload_session_id"]

            magnetic = client.post(f"/api/cses-hpm/uploads/{session_id}/plot", json={"plot_type": "magnetic"})
            self.assertEqual(magnetic.status_code, 200)
            magnetic_payload = magnetic.json()
            self.assertEqual(magnetic_payload["status"], "ok")
            self.assertEqual(magnetic_payload["artifact"]["media_type"], "image/png")
            self.assertTrue(Path(magnetic_payload["artifact"]["path"]).exists())

            orbit = client.post(f"/api/cses-hpm/uploads/{session_id}/plot", json={"plot_type": "orbit"})
            self.assertEqual(orbit.status_code, 200)
            orbit_payload = orbit.json()
            self.assertEqual(orbit_payload["status"], "ok")
            self.assertEqual(orbit_payload["artifact"]["media_type"], "text/html")
            orbit_html = Path(orbit_payload["artifact"]["path"]).read_text(encoding="utf-8")
            self.assertIn("drawLatitudeLongitudeGrid", orbit_html)
            self.assertIn("Lat/Lon grid", orbit_html)
            self.assertIn("segment_1", orbit_html)
            self.assertNotIn("colorbar", orbit_html.lower())
            artifact_response = client.get(f"/api/artifacts/{orbit_payload['artifact']['artifact_id']}")
            self.assertEqual(artifact_response.status_code, 200)
            self.assertIn("text/html", artifact_response.headers["content-type"])
            self.assertNotIn("attachment", artifact_response.headers.get("content-disposition", "").lower())
            artifact_download = client.get(f"/api/artifacts/{orbit_payload['artifact']['artifact_id']}?download=1")
            self.assertEqual(artifact_download.status_code, 200)
            self.assertIn("attachment", artifact_download.headers.get("content-disposition", "").lower())

            export = client.post(
                f"/api/cses-hpm/uploads/{session_id}/export",
                json={"format": "csv", "crop_range": {"start": "2023-04-19T23:55:01Z", "end": "2023-04-19T23:55:03Z"}},
            )
            self.assertEqual(export.status_code, 200)
            export_payload = export.json()
            self.assertEqual(export_payload["status"], "ok")
            self.assertEqual(export_payload["row_count"], 3)
            self.assertEqual(export_payload["manifest"]["format"], "csv")
            self.assertEqual(export_payload["manifest"]["crop_range"]["start"], "2023-04-19T23:55:01Z")
            self.assertTrue(Path(export_payload["manifest_artifact"]["path"]).exists())

            cdf = client.post(f"/api/cses-hpm/uploads/{session_id}/export", json={"format": "cdf"})
            self.assertEqual(cdf.status_code, 200)
            self.assertEqual(cdf.json()["status"], "unsupported")
            self.assertIn("CDF", cdf.json()["reason"])


if __name__ == "__main__":
    unittest.main()
