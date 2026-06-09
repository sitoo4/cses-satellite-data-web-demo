from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.cses_h5_inspector import inspect_h5_tree


class CsesDatasourceApiTest(unittest.TestCase):
    def test_cses_metadata_reports_inferred_time_range_and_cadence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hpm_root = root / "HPM"
            output_root = root / "outputs"
            hpm_root.mkdir()
            h5_path = hpm_root / "timed.h5"

            with h5py.File(h5_path, "w") as h5:
                utc = h5.create_dataset(
                    "UTC_TIME",
                    data=np.array(
                        [
                            20230419235544000,
                            20230419235545000,
                            20230419235546000,
                            20230419235547000,
                        ],
                        dtype=np.int64,
                    ).reshape(4, 1),
                )
                utc.attrs["Units"] = "yyyymmddhhmmssmmm"
                h5.create_dataset("B_FGM", data=np.arange(12, dtype=np.float64).reshape(4, 3))

            inspection_root = output_root / "cses_hpm_inspection"
            inspect_h5_tree(hpm_root, inspection_root, max_preview=2, sample_size=16)

            config_path = root / "local_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "cses_hpm_root": str(hpm_root),
                        "outputs_root": str(output_root),
                    }
                ),
                encoding="utf-8",
            )

            client = TestClient(create_app(config_path=config_path))

            metadata = client.get("/api/datasources/cses_hpm/metadata", params={"file_id": "timed.h5"})
            self.assertEqual(metadata.status_code, 200)
            time_summary = metadata.json()["time_summary"]
            self.assertEqual(time_summary["status"], "parsed")
            self.assertEqual(time_summary["time_variable"], "/UTC_TIME")
            self.assertEqual(time_summary["time_confidence"], "inferred")
            self.assertEqual(time_summary["time_units"], "yyyymmddhhmmssmmm")
            self.assertEqual(time_summary["sample_count"], 4)
            self.assertEqual(time_summary["start"], "2023-04-19T23:55:44Z")
            self.assertEqual(time_summary["end"], "2023-04-19T23:55:47Z")
            self.assertEqual(time_summary["cadence_ms"]["min"], 1000)
            self.assertEqual(time_summary["cadence_ms"]["median"], 1000)
            self.assertEqual(time_summary["cadence_ms"]["max"], 1000)

    def test_cses_metadata_reports_inferred_quality_flag_distribution(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hpm_root = root / "HPM"
            output_root = root / "outputs"
            hpm_root.mkdir()
            h5_path = hpm_root / "flags.h5"

            with h5py.File(h5_path, "w") as h5:
                h5.create_dataset("UTC_TIME", data=np.arange(6, dtype=np.int64).reshape(6, 1))
                h5.create_dataset("FLAG_MT", data=np.array([0, 0, 1, 1, 1, 3], dtype=np.int32).reshape(6, 1))
                h5.create_dataset("B_FGM", data=np.arange(18, dtype=np.float64).reshape(6, 3))

            inspection_root = output_root / "cses_hpm_inspection"
            inspect_h5_tree(hpm_root, inspection_root, max_preview=2, sample_size=16)

            config_path = root / "local_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "cses_hpm_root": str(hpm_root),
                        "outputs_root": str(output_root),
                    }
                ),
                encoding="utf-8",
            )

            client = TestClient(create_app(config_path=config_path))

            metadata = client.get("/api/datasources/cses_hpm/metadata", params={"file_id": "flags.h5"})
            self.assertEqual(metadata.status_code, 200)
            quality_summary = metadata.json()["quality_summary"]
            self.assertEqual(quality_summary["status"], "parsed")
            self.assertEqual(quality_summary["flag_variable"], "/FLAG_MT")
            self.assertEqual(quality_summary["flag_confidence"], "inferred")
            self.assertEqual(quality_summary["sample_count"], 6)
            self.assertEqual(quality_summary["distribution"], {"0": 2, "1": 3, "3": 1})

    def test_cses_minimal_api_reads_inspection_and_previews_h5_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hpm_root = root / "HPM"
            output_root = root / "outputs"
            hpm_root.mkdir()
            h5_path = hpm_root / "sample.h5"

            with h5py.File(h5_path, "w") as h5:
                utc = h5.create_dataset(
                    "UTC_TIME",
                    data=np.array(
                        [
                            20230419235544000,
                            20230419235545000,
                            20230419235546000,
                            20230419235547000,
                            20230419235548000,
                            20230419235549000,
                        ],
                        dtype=np.int64,
                    ).reshape(6, 1),
                )
                utc.attrs["Units"] = "yyyymmddhhmmssmmm"
                b = h5.create_dataset("B_FGM", data=np.arange(18, dtype=np.float64).reshape(6, 3))
                b.attrs["Units"] = "nT"
                h5.create_dataset("GEO_LAT", data=np.linspace(-2, 2, 6).reshape(6, 1))
                h5.create_dataset("GEO_LON", data=np.linspace(100, 104, 6).reshape(6, 1))
                h5.create_dataset("ALTITUDE", data=np.linspace(500, 505, 6).reshape(6, 1))
                h5.create_dataset("FLAG_MT", data=np.zeros((6, 1), dtype=np.int32))

            inspection_root = output_root / "cses_hpm_inspection"
            inspect_h5_tree(hpm_root, inspection_root, max_preview=2, sample_size=16)

            config_path = root / "local_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "cses_hpm_root": str(hpm_root),
                        "outputs_root": str(output_root),
                    }
                ),
                encoding="utf-8",
            )

            client = TestClient(create_app(config_path=config_path))

            health = client.get("/api/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["status"], "ok")

            datasources = client.get("/api/datasources")
            self.assertEqual(datasources.status_code, 200)
            names = {item["name"] for item in datasources.json()["datasources"]}
            self.assertEqual(names, {"cses_hpm"})
            cses_summary = next(item for item in datasources.json()["datasources"] if item["name"] == "cses_hpm")
            unsupported = {item["feature"]: item["reason"] for item in cses_summary["unsupported"]}
            self.assertIn("electric_field", unsupported)
            self.assertIn("magnetometer-only datasource", unsupported["electric_field"])
            self.assertIn("solar_wind", unsupported)
            self.assertIn("magnetometer-only datasource", unsupported["solar_wind"])
            self.assertIn("spectrogram", unsupported)

            files = client.get("/api/datasources/cses_hpm/files")
            self.assertEqual(files.status_code, 200)
            file_items = files.json()["files"]
            self.assertEqual(len(file_items), 1)
            self.assertEqual(file_items[0]["file_id"], "sample.h5")
            self.assertTrue(file_items[0]["inspection"]["summary_exists"])

            metadata = client.get("/api/datasources/cses_hpm/metadata", params={"file_id": "sample.h5"})
            self.assertEqual(metadata.status_code, 200)
            self.assertEqual(metadata.json()["file"]["relative_path"], "sample.h5")
            self.assertEqual(metadata.json()["dataset_count"], 6)
            report_artifact = metadata.json()["report_artifact"]
            self.assertEqual(report_artifact["media_type"], "text/markdown")
            self.assertTrue(report_artifact["artifact_id"].startswith("cses_hpm:inspection_report:sample_h5"))
            report_response = client.get(f"/api/artifacts/{report_artifact['artifact_id']}")
            self.assertEqual(report_response.status_code, 200)
            self.assertEqual(report_response.headers["content-type"].split(";")[0], "text/markdown")
            self.assertIn("# H5 Inspection Report: sample.h5", report_response.text)

            variables = client.get("/api/datasources/cses_hpm/variables", params={"file_id": "sample.h5"})
            self.assertEqual(variables.status_code, 200)
            by_name = {item["name"]: item for item in variables.json()["variables"]}
            self.assertEqual(by_name["/B_FGM"]["data_kind"], "magnetic_vector")
            self.assertEqual(by_name["/B_FGM"]["confidence"], "inferred")
            self.assertEqual(by_name["/UTC_TIME"]["data_kind"], "time")
            self.assertEqual(by_name["/FLAG_MT"]["data_kind"], "quality_flag")

            catalog = client.get("/api/datasources/cses_hpm/plot-catalog", params={"file_id": "sample.h5"})
            self.assertEqual(catalog.status_code, 200)
            catalog_payload = catalog.json()
            self.assertEqual(catalog_payload["datasource"], "cses_hpm")
            self.assertEqual(catalog_payload["datasource_type"], "CSES-01 HPM magnetometer-only H5 datasource")
            catalog_by_type = {item["plot_type"]: item for item in catalog_payload["plots"]}
            self.assertEqual(
                list(catalog_by_type),
                [
                    "cses_hpm_magnetic_overview",
                    "cses_hpm_quality_overview",
                    "cses_hpm_trajectory_overview",
                    "cses_hpm_cadence_overview",
                    "cses_hpm_batch_statistics_overview",
                    "cses_hpm_spectrogram_overview",
                    "cses_hpm_electric_field_overview",
                    "cses_hpm_solar_wind_overview",
                ],
            )
            self.assertTrue(catalog_by_type["cses_hpm_magnetic_overview"]["enabled"])
            self.assertEqual(catalog_by_type["cses_hpm_magnetic_overview"]["inferred_fields"], ["/B_FGM"])
            self.assertTrue(catalog_by_type["cses_hpm_quality_overview"]["enabled"])
            self.assertTrue(catalog_by_type["cses_hpm_trajectory_overview"]["enabled"])
            self.assertTrue(catalog_by_type["cses_hpm_cadence_overview"]["enabled"])
            self.assertTrue(catalog_by_type["cses_hpm_batch_statistics_overview"]["enabled"])
            self.assertFalse(catalog_by_type["cses_hpm_spectrogram_overview"]["enabled"])
            self.assertIn("requires confirmed time semantics", catalog_by_type["cses_hpm_spectrogram_overview"]["disabled_reason"])
            self.assertFalse(catalog_by_type["cses_hpm_electric_field_overview"]["enabled"])
            self.assertIn("magnetometer-only datasource", catalog_by_type["cses_hpm_electric_field_overview"]["disabled_reason"])
            self.assertFalse(catalog_by_type["cses_hpm_solar_wind_overview"]["enabled"])
            self.assertIn("magnetometer-only datasource", catalog_by_type["cses_hpm_solar_wind_overview"]["disabled_reason"])

            preview = client.post(
                "/api/datasources/cses_hpm/subset",
                json={
                    "file_id": "sample.h5",
                    "variables": ["/B_FGM", "/UTC_TIME"],
                    "range": {"mode": "sample_index", "start_index": 1, "end_index": 4},
                    "preview_limit": 3,
                },
            )
            self.assertEqual(preview.status_code, 200)
            payload = preview.json()
            self.assertEqual(payload["range"]["sample_count"], 3)
            self.assertEqual(payload["variables"][0]["path"], "/B_FGM")
            self.assertEqual(payload["variables"][0]["data"], [[3.0, 4.0, 5.0], [6.0, 7.0, 8.0], [9.0, 10.0, 11.0]])

            timeseries_plot = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "sample.h5",
                    "plot_type": "magnetic_timeseries",
                    "variables": ["/B_FGM"],
                    "time_variable": "/UTC_TIME",
                    "range": {"mode": "sample_index", "start_index": 1, "end_index": 5},
                },
            )
            self.assertEqual(timeseries_plot.status_code, 200)
            timeseries_payload = timeseries_plot.json()
            self.assertEqual(timeseries_payload["plot_type"], "magnetic_timeseries")
            self.assertEqual(timeseries_payload["range"]["sample_count"], 4)
            self.assertEqual(timeseries_payload["artifact"]["media_type"], "image/png")
            self.assertIn("outputs/generated_plots/cses_hpm", timeseries_payload["artifact"]["path"])
            self.assertTrue(timeseries_payload["artifact"]["exists"])
            timeseries_artifact = client.get(f"/api/artifacts/{timeseries_payload['artifact']['artifact_id']}")
            self.assertEqual(timeseries_artifact.status_code, 200)
            self.assertEqual(timeseries_artifact.headers["content-type"].split(";")[0], "image/png")
            self.assertTrue(timeseries_artifact.content.startswith(b"\x89PNG\r\n\x1a\n"))

            magnetic_overview = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "sample.h5",
                    "plot_type": "cses_hpm_magnetic_overview",
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 6},
                },
            )
            self.assertEqual(magnetic_overview.status_code, 200)
            magnetic_payload = magnetic_overview.json()
            self.assertEqual(magnetic_payload["plot_type"], "cses_hpm_magnetic_overview")
            self.assertEqual(magnetic_payload["fields"][0]["path"], "/B_FGM")
            self.assertEqual(magnetic_payload["fields"][0]["unit"], "nT")
            self.assertEqual(magnetic_payload["time"]["field"], "/UTC_TIME")
            self.assertEqual(magnetic_payload["time"]["confidence"], "inferred")
            self.assertIn("outputs/generated_plots/cses_hpm", magnetic_payload["artifact"]["path"])

            quality_overview = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "sample.h5",
                    "plot_type": "cses_hpm_quality_overview",
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 6},
                },
            )
            self.assertEqual(quality_overview.status_code, 200)
            quality_payload = quality_overview.json()
            self.assertEqual(quality_payload["plot_type"], "cses_hpm_quality_overview")
            self.assertEqual(quality_payload["fields"][0]["path"], "/FLAG_MT")
            self.assertEqual(quality_payload["quality_distribution"], {"0": 6})
            self.assertIn("outputs/generated_plots/cses_hpm", quality_payload["artifact"]["path"])

            trajectory_overview = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "sample.h5",
                    "plot_type": "cses_hpm_trajectory_overview",
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 6},
                },
            )
            self.assertEqual(trajectory_overview.status_code, 200)
            trajectory_payload = trajectory_overview.json()
            self.assertEqual(trajectory_payload["plot_type"], "cses_hpm_trajectory_overview")
            self.assertEqual(trajectory_payload["fields"], [{"path": "/GEO_LAT", "unit": None}, {"path": "/GEO_LON", "unit": None}, {"path": "/ALTITUDE", "unit": None}])
            self.assertIn("outputs/generated_plots/cses_hpm", trajectory_payload["artifact"]["path"])

            cadence_overview = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "sample.h5",
                    "plot_type": "cses_hpm_cadence_overview",
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 6},
                },
            )
            self.assertEqual(cadence_overview.status_code, 200)
            cadence_payload = cadence_overview.json()
            self.assertEqual(cadence_payload["plot_type"], "cses_hpm_cadence_overview")
            self.assertEqual(cadence_payload["time"]["field"], "/UTC_TIME")
            self.assertEqual(cadence_payload["time"]["confidence"], "inferred")
            self.assertIn("inferred time semantics", " ".join(cadence_payload["processing_log"]))
            self.assertIn("outputs/generated_plots/cses_hpm", cadence_payload["artifact"]["path"])

            trajectory_plot = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "sample.h5",
                    "plot_type": "trajectory_3d",
                    "lat_variable": "/GEO_LAT",
                    "lon_variable": "/GEO_LON",
                    "alt_variable": "/ALTITUDE",
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 6},
                },
            )
            self.assertEqual(trajectory_plot.status_code, 200)
            self.assertEqual(trajectory_plot.json()["artifact"]["media_type"], "image/png")

            spectrogram_plot = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "sample.h5",
                    "plot_type": "spectrogram",
                    "variables": ["/B_FGM"],
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 6},
                },
            )
            self.assertEqual(spectrogram_plot.status_code, 200)
            self.assertEqual(spectrogram_plot.json()["status"], "unsupported")
            self.assertIn("requires confirmed time semantics", spectrogram_plot.json()["reason"])
            self.assertNotIn("artifact", spectrogram_plot.json())

            electric_plot = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "sample.h5",
                    "plot_type": "electric_field",
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 6},
                },
            )
            self.assertEqual(electric_plot.status_code, 200)
            self.assertEqual(electric_plot.json()["status"], "unsupported")
            self.assertIn("magnetometer-only datasource", electric_plot.json()["reason"])
            self.assertNotIn("artifact", electric_plot.json())

            solar_plot = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "sample.h5",
                    "plot_type": "solar_wind",
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 6},
                },
            )
            self.assertEqual(solar_plot.status_code, 200)
            self.assertEqual(solar_plot.json()["status"], "unsupported")
            self.assertIn("magnetometer-only datasource", solar_plot.json()["reason"])
            self.assertNotIn("artifact", solar_plot.json())

    def test_cses_trajectory_plot_reports_not_available_when_coordinate_variables_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hpm_root = root / "HPM"
            output_root = root / "outputs"
            hpm_root.mkdir()
            h5_path = hpm_root / "partial_track.h5"

            with h5py.File(h5_path, "w") as h5:
                h5.create_dataset("UTC_TIME", data=np.arange(6, dtype=np.int64).reshape(6, 1))
                h5.create_dataset("B_FGM", data=np.arange(18, dtype=np.float64).reshape(6, 3))
                h5.create_dataset("GEO_LAT", data=np.linspace(-2, 2, 6).reshape(6, 1))

            inspection_root = output_root / "cses_hpm_inspection"
            inspect_h5_tree(hpm_root, inspection_root, max_preview=2, sample_size=16)

            config_path = root / "local_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "cses_hpm_root": str(hpm_root),
                        "outputs_root": str(output_root),
                    }
                ),
                encoding="utf-8",
            )

            client = TestClient(create_app(config_path=config_path))

            trajectory_2d = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "partial_track.h5",
                    "plot_type": "trajectory_2d",
                    "lat_variable": "/GEO_LAT",
                    "lon_variable": "/GEO_LON",
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 6},
                },
            )
            self.assertEqual(trajectory_2d.status_code, 200)
            payload_2d = trajectory_2d.json()
            self.assertEqual(payload_2d["status"], "not_available")
            self.assertEqual(payload_2d["missing_variables"], ["/GEO_LON"])
            self.assertIn("requires /GEO_LAT and /GEO_LON", payload_2d["reason"])
            self.assertNotIn("artifact", payload_2d)

            trajectory_3d = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "partial_track.h5",
                    "plot_type": "trajectory_3d",
                    "lat_variable": "/GEO_LAT",
                    "lon_variable": "/GEO_LON",
                    "alt_variable": "/ALTITUDE",
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 6},
                },
            )
            self.assertEqual(trajectory_3d.status_code, 200)
            payload_3d = trajectory_3d.json()
            self.assertEqual(payload_3d["status"], "not_available")
            self.assertEqual(payload_3d["missing_variables"], ["/GEO_LON", "/ALTITUDE"])
            self.assertIn("requires /GEO_LAT, /GEO_LON, and /ALTITUDE", payload_3d["reason"])
            self.assertNotIn("artifact", payload_3d)


if __name__ == "__main__":
    unittest.main()
