from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np
from fastapi.testclient import TestClient

from app.datasources.cses_hpm import parse_cses_utc_time_millis
from app.main import create_app
from app.services.cses_h5_inspector import inspect_h5_tree


class Phase6ExportStatsApiTest(unittest.TestCase):
    def test_cses_stats_and_csv_export_use_bounded_sample_index_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hpm_root = root / "HPM"
            output_root = root / "outputs"
            hpm_root.mkdir()
            h5_path = hpm_root / "sample.h5"

            with h5py.File(h5_path, "w") as h5:
                utc = h5.create_dataset("UTC_TIME", data=np.arange(8, dtype=np.int64).reshape(8, 1))
                utc.attrs["Units"] = "ms"
                b_values = np.arange(24, dtype=np.float64).reshape(8, 3)
                b_values[3, 0] = np.nan
                b_fgm = h5.create_dataset("B_FGM", data=b_values)
                b_fgm.attrs["Units"] = np.bytes_("nT")
                flag = h5.create_dataset("FLAG_MT", data=np.array([0, 1, 0, 1, 0, 1, 0, 1], dtype=np.int32).reshape(8, 1))
                flag.attrs["Units"] = "flag"

            inspect_h5_tree(hpm_root, output_root / "cses_hpm_inspection", max_preview=2, sample_size=16)
            config_path = root / "local_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "cluster_raw_root": str(root / "cluster"),
                        "cluster_processed_root": str(root / "idlpython_v2"),
                        "cses_hpm_root": str(hpm_root),
                        "outputs_root": str(output_root),
                    }
                ),
                encoding="utf-8",
            )
            client = TestClient(create_app(config_path=config_path))

            stats = client.post(
                "/api/datasources/cses_hpm/stats",
                json={
                    "file_id": "sample.h5",
                    "variables": ["/B_FGM", "/FLAG_MT"],
                    "range": {"mode": "sample_index", "start_index": 2, "end_index": 6},
                },
            )
            self.assertEqual(stats.status_code, 200)
            stats_payload = stats.json()
            self.assertEqual(stats_payload["range"]["sample_count"], 4)
            by_name = {item["path"]: item for item in stats_payload["variables"]}
            self.assertEqual(by_name["/B_FGM"]["component_count"], 3)
            self.assertEqual(by_name["/B_FGM"]["stats"][0]["min"], 6.0)
            self.assertEqual(by_name["/B_FGM"]["stats"][0]["max"], 15.0)
            self.assertEqual(by_name["/B_FGM"]["stats"][0]["count"], 4)
            self.assertEqual(by_name["/B_FGM"]["stats"][0]["finite_count"], 3)
            self.assertEqual(by_name["/B_FGM"]["stats"][0]["median"], 12.0)
            self.assertEqual(by_name["/B_FGM"]["stats"][0]["missing_ratio"], 0.25)
            self.assertEqual(by_name["/FLAG_MT"]["stats"][0]["mean"], 0.5)

            saved_stats = client.post(
                "/api/datasources/cses_hpm/stats",
                json={
                    "file_id": "sample.h5",
                    "variables": ["/B_FGM", "/FLAG_MT"],
                    "range": {"mode": "sample_index", "start_index": 2, "end_index": 6},
                    "save_format": "json",
                },
            )
            self.assertEqual(saved_stats.status_code, 200)
            saved_payload = saved_stats.json()
            self.assertIn("stats_artifact", saved_payload)
            json_artifact = saved_payload["stats_artifact"]
            self.assertEqual(json_artifact["media_type"], "application/json")
            self.assertTrue(str(json_artifact["artifact_id"]).startswith("cses_hpm:stats:sample_h5:"))
            saved_json = client.get(f"/api/artifacts/{json_artifact['artifact_id']}")
            self.assertEqual(saved_json.status_code, 200)
            self.assertEqual(saved_json.json()["variables"][0]["path"], "/B_FGM")

            saved_csv = client.post(
                "/api/datasources/cses_hpm/stats",
                json={
                    "file_id": "sample.h5",
                    "variables": ["/B_FGM"],
                    "range": {"mode": "sample_index", "start_index": 2, "end_index": 6},
                    "save_format": "csv",
                },
            )
            self.assertEqual(saved_csv.status_code, 200)
            csv_artifact = saved_csv.json()["stats_artifact"]
            self.assertEqual(csv_artifact["media_type"], "text/csv")
            csv_text = client.get(f"/api/artifacts/{csv_artifact['artifact_id']}").text
            self.assertTrue(csv_text.startswith("variable,component,count,finite_count,min,max,mean,median,std,missing_ratio\n"))
            self.assertIn("/B_FGM,0,4,3,6.0,15.0,11.0,12.0", csv_text)
            self.assertIn(",0.25", csv_text)

            saved_h5 = client.post(
                "/api/datasources/cses_hpm/stats",
                json={
                    "file_id": "sample.h5",
                    "variables": ["/B_FGM"],
                    "range": {"mode": "sample_index", "start_index": 2, "end_index": 6},
                    "save_format": "h5",
                },
            )
            self.assertEqual(saved_h5.status_code, 200)
            h5_artifact = saved_h5.json()["stats_artifact"]
            self.assertEqual(h5_artifact["media_type"], "application/x-hdf5")
            with h5py.File(h5_artifact["path"], "r") as saved_h5_file:
                self.assertEqual(saved_h5_file.attrs["datasource"], "cses_hpm")
                self.assertIn("variables", saved_h5_file)
                self.assertIn("B_FGM", saved_h5_file["variables"])
                self.assertEqual(saved_h5_file["variables"]["B_FGM"].attrs["path"], "/B_FGM")
                np.testing.assert_array_equal(saved_h5_file["variables"]["B_FGM"]["component"][:], np.array([0, 1, 2]))

            saved_dat = client.post(
                "/api/datasources/cses_hpm/stats",
                json={
                    "file_id": "sample.h5",
                    "variables": ["/B_FGM"],
                    "range": {"mode": "sample_index", "start_index": 2, "end_index": 6},
                    "save_format": "dat",
                },
            )
            self.assertEqual(saved_dat.status_code, 200)
            dat_stats_artifact = saved_dat.json()["stats_artifact"]
            self.assertEqual(dat_stats_artifact["media_type"], "text/plain")
            dat_stats_text = client.get(f"/api/artifacts/{dat_stats_artifact['artifact_id']}").text
            self.assertTrue(dat_stats_text.startswith("variable\tcomponent\tcount\tfinite_count\tmin\tmax\tmean\tmedian\tstd\tmissing_ratio\n"))
            self.assertIn("/B_FGM\t0\t4\t3\t6.0\t15.0\t11.0\t12.0", dat_stats_text)
            self.assertIn("\t0.25", dat_stats_text)

            saved_cdf = client.post(
                "/api/datasources/cses_hpm/stats",
                json={
                    "file_id": "sample.h5",
                    "variables": ["/B_FGM"],
                    "range": {"mode": "sample_index", "start_index": 2, "end_index": 6},
                    "save_format": "cdf",
                },
            )
            self.assertEqual(saved_cdf.status_code, 200)
            cdf_stats_payload = saved_cdf.json()
            self.assertEqual(cdf_stats_payload["status"], "unsupported")
            self.assertEqual(cdf_stats_payload["save_format"], "cdf")
            self.assertEqual(cdf_stats_payload["reserved"], True)
            self.assertNotIn("stats_artifact", cdf_stats_payload)
            self.assertIn("CDF remains reserved", cdf_stats_payload["reason"])

            export = client.post(
                "/api/datasources/cses_hpm/export",
                json={
                    "file_id": "sample.h5",
                    "variables": ["/UTC_TIME", "/B_FGM"],
                    "range": {"mode": "sample_index", "start_index": 1, "end_index": 4},
                    "format": "csv",
                },
            )
            self.assertEqual(export.status_code, 200)
            export_payload = export.json()
            artifact = export_payload["artifact"]
            self.assertEqual(artifact["media_type"], "text/csv")
            self.assertTrue(str(artifact["artifact_id"]).startswith("cses_hpm:export:sample_h5:"))
            self.assertIn(str(output_root / "exports"), artifact["path"])
            self.assertIn("manifest_artifact", export_payload)
            self.assertEqual(export_payload["manifest"]["format"], "csv")
            self.assertEqual(export_payload["manifest"]["sample_count"], 3)
            self.assertEqual(export_payload["manifest"]["variables"][1]["path"], "/B_FGM")
            self.assertEqual(export_payload["manifest"]["variables"][1]["unit"], "nT")

            artifact_response = client.get(f"/api/artifacts/{artifact['artifact_id']}")
            self.assertEqual(artifact_response.status_code, 200)
            self.assertEqual(artifact_response.headers["content-type"].split(";")[0], "text/csv")
            rows = list(csv.DictReader(artifact_response.text.splitlines()))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["sample_index"], "1")
            self.assertEqual(rows[0]["UTC_TIME"], "1")
            self.assertEqual(rows[0]["B_FGM_0"], "3.0")
            self.assertEqual(rows[0]["B_FGM_2"], "5.0")

            manifest_response = client.get(f"/api/artifacts/{export_payload['manifest_artifact']['artifact_id']}")
            self.assertEqual(manifest_response.status_code, 200)
            manifest = manifest_response.json()
            self.assertEqual(manifest["datasource"], "cses_hpm")
            self.assertEqual(manifest["original_file"], str(h5_path.resolve()))
            self.assertEqual(manifest["range"], {"mode": "sample_index", "start_index": 1, "end_index": 4})
            self.assertEqual(manifest["export_format"], "csv")

            dat_export = client.post(
                "/api/datasources/cses_hpm/export",
                json={
                    "file_id": "sample.h5",
                    "variables": ["/B_FGM"],
                    "range": {"mode": "sample_index", "start_index": 1, "end_index": 4},
                    "format": "dat",
                },
            )
            self.assertEqual(dat_export.status_code, 200)
            dat_artifact = dat_export.json()["artifact"]
            self.assertEqual(dat_artifact["media_type"], "text/plain")
            dat_text = client.get(f"/api/artifacts/{dat_artifact['artifact_id']}").text
            self.assertTrue(dat_text.startswith("sample_index\tB_FGM_0\tB_FGM_1\tB_FGM_2\n"))

            h5_export = client.post(
                "/api/datasources/cses_hpm/export",
                json={
                    "file_id": "sample.h5",
                    "variables": ["/B_FGM"],
                    "range": {"mode": "sample_index", "start_index": 1, "end_index": 4},
                    "format": "h5",
                },
            )
            self.assertEqual(h5_export.status_code, 200)
            h5_artifact = h5_export.json()["artifact"]
            self.assertEqual(h5_artifact["media_type"], "application/x-hdf5")
            with h5py.File(h5_artifact["path"], "r") as exported_h5:
                np.testing.assert_array_equal(exported_h5["sample_index"][:], np.array([1, 2, 3]))
                expected_b_export = np.arange(3, 12, dtype=np.float64).reshape(3, 3)
                expected_b_export[2, 0] = np.nan
                np.testing.assert_array_equal(exported_h5["variables"]["B_FGM"][:], expected_b_export)
                self.assertEqual(exported_h5["variables"]["B_FGM"].attrs["original_path"], "/B_FGM")

            cdf_export = client.post(
                "/api/datasources/cses_hpm/export",
                json={
                    "file_id": "sample.h5",
                    "variables": ["/B_FGM"],
                    "range": {"mode": "sample_index", "start_index": 1, "end_index": 4},
                    "format": "cdf",
                },
            )
            self.assertEqual(cdf_export.status_code, 200)
            cdf_payload = cdf_export.json()
            self.assertEqual(cdf_payload["status"], "unsupported")
            self.assertEqual(cdf_payload["format"], "cdf")
            self.assertEqual(cdf_payload["reserved"], True)
            self.assertNotIn("artifact", cdf_payload)
            self.assertIn("CDF remains reserved", cdf_payload["reason"])

    def test_cses_time_range_subset_and_stats_use_parseable_utc_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hpm_root = root / "HPM"
            output_root = root / "outputs"
            hpm_root.mkdir()
            h5_path = hpm_root / "time_sample.h5"

            with h5py.File(h5_path, "w") as h5:
                utc = h5.create_dataset(
                    "UTC_TIME",
                    data=np.array(
                        [
                            20230419235543000,
                            20230419235544000,
                            20230419235545000,
                            20230419235546000,
                            20230419235547000,
                        ],
                        dtype=np.int64,
                    ).reshape(5, 1),
                )
                utc.attrs["Units"] = np.bytes_("YYYYMMDDHHMMSS.mmm")
                b_fgm = h5.create_dataset("B_FGM", data=np.arange(15, dtype=np.float64).reshape(5, 3))
                b_fgm.attrs["Units"] = np.bytes_("nT")
                geo_lat = h5.create_dataset("GEO_LAT", data=np.linspace(-10, -6, 5, dtype=np.float64).reshape(5, 1))
                geo_lat.attrs["Units"] = np.bytes_("deg")

            inspect_h5_tree(hpm_root, output_root / "cses_hpm_inspection", max_preview=2, sample_size=16)
            config_path = root / "local_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "cluster_raw_root": str(root / "cluster"),
                        "cluster_processed_root": str(root / "idlpython_v2"),
                        "cses_hpm_root": str(hpm_root),
                        "outputs_root": str(output_root),
                    }
                ),
                encoding="utf-8",
            )
            client = TestClient(create_app(config_path=config_path))

            subset = client.post(
                "/api/datasources/cses_hpm/subset",
                json={
                    "file_id": "time_sample.h5",
                    "variables": ["/B_FGM"],
                    "range": {
                        "mode": "time",
                        "start": "2023-04-19T23:55:44Z",
                        "end": "2023-04-19T23:55:47Z",
                    },
                },
            )
            self.assertEqual(subset.status_code, 200)
            subset_payload = subset.json()
            self.assertEqual(subset_payload["range"]["mode"], "time")
            self.assertEqual(subset_payload["range"]["resolved_mode"], "sample_index")
            self.assertEqual(subset_payload["range"]["start_index"], 1)
            self.assertEqual(subset_payload["range"]["end_index"], 4)
            self.assertEqual(subset_payload["range"]["sample_count"], 3)
            self.assertEqual(subset_payload["range"]["time_variable"], "/UTC_TIME")
            self.assertEqual(subset_payload["range"]["time_confidence"], "inferred")
            self.assertEqual(subset_payload["variables"][0]["data"], [[3.0, 4.0, 5.0], [6.0, 7.0, 8.0], [9.0, 10.0, 11.0]])

            timeseries = client.post(
                "/api/datasources/cses_hpm/timeseries",
                json={
                    "file_id": "time_sample.h5",
                    "variables": ["/B_FGM"],
                    "range": {
                        "mode": "time",
                        "start": "2023-04-19T23:55:44Z",
                        "end": "2023-04-19T23:55:47Z",
                    },
                },
            )
            self.assertEqual(timeseries.status_code, 200)
            timeseries_payload = timeseries.json()
            self.assertEqual(timeseries_payload["range"]["start_index"], 1)
            self.assertEqual(timeseries_payload["range"]["end_index"], 4)
            self.assertEqual(timeseries_payload["time_axis"]["path"], "/UTC_TIME")
            self.assertEqual(timeseries_payload["time_axis"]["confidence"], "inferred")
            self.assertEqual(
                timeseries_payload["time_axis"]["data"],
                ["2023-04-19T23:55:44Z", "2023-04-19T23:55:45Z", "2023-04-19T23:55:46Z"],
            )
            self.assertEqual(timeseries_payload["variables"][0]["data"], [[3.0, 4.0, 5.0], [6.0, 7.0, 8.0], [9.0, 10.0, 11.0]])

            stats = client.post(
                "/api/datasources/cses_hpm/stats",
                json={
                    "file_id": "time_sample.h5",
                    "variables": ["/B_FGM"],
                    "range": {
                        "mode": "time",
                        "start": "2023-04-19T23:55:44Z",
                        "end": "2023-04-19T23:55:47Z",
                    },
                },
            )
            self.assertEqual(stats.status_code, 200)
            stats_payload = stats.json()
            self.assertEqual(stats_payload["range"]["start_index"], 1)
            self.assertEqual(stats_payload["range"]["end_index"], 4)
            self.assertEqual(stats_payload["range"]["sample_count"], 3)
            self.assertEqual(stats_payload["range"]["time_confidence"], "inferred")
            by_name = {item["path"]: item for item in stats_payload["variables"]}
            self.assertEqual(by_name["/B_FGM"]["stats"][0]["min"], 3.0)
            self.assertEqual(by_name["/B_FGM"]["stats"][0]["max"], 9.0)

            plot = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "time_sample.h5",
                    "plot_type": "magnetic_timeseries",
                    "variables": ["/B_FGM"],
                    "time_variable": "/UTC_TIME",
                    "range": {
                        "mode": "time",
                        "start": "2023-04-19T23:55:44Z",
                        "end": "2023-04-19T23:55:47Z",
                    },
                },
            )
            self.assertEqual(plot.status_code, 200)
            plot_payload = plot.json()
            self.assertEqual(plot_payload["range"]["mode"], "time")
            self.assertEqual(plot_payload["range"]["resolved_mode"], "sample_index")
            self.assertEqual(plot_payload["range"]["sample_count"], 3)
            self.assertEqual(plot_payload["artifact"]["media_type"], "image/png")

            scalar_plot = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "time_sample.h5",
                    "plot_type": "scalar_timeseries",
                    "variables": ["/GEO_LAT"],
                    "time_variable": "/UTC_TIME",
                    "range": {
                        "mode": "time",
                        "start": "2023-04-19T23:55:44Z",
                        "end": "2023-04-19T23:55:47Z",
                    },
                },
            )
            self.assertEqual(scalar_plot.status_code, 200)
            scalar_payload = scalar_plot.json()
            self.assertEqual(scalar_payload["plot_type"], "scalar_timeseries")
            self.assertEqual(scalar_payload["range"]["sample_count"], 3)
            self.assertEqual(scalar_payload["artifact"]["media_type"], "image/png")
            scalar_artifact = client.get(f"/api/artifacts/{scalar_payload['artifact']['artifact_id']}")
            self.assertEqual(scalar_artifact.status_code, 200)
            self.assertEqual(scalar_artifact.headers["content-type"].split(";")[0], "image/png")
            self.assertTrue(scalar_artifact.content.startswith(b"\x89PNG\r\n\x1a\n"))

            export = client.post(
                "/api/datasources/cses_hpm/export",
                json={
                    "file_id": "time_sample.h5",
                    "variables": ["/B_FGM"],
                    "range": {
                        "mode": "time",
                        "start": "2023-04-19T23:55:44Z",
                        "end": "2023-04-19T23:55:47Z",
                    },
                    "format": "csv",
                },
            )
            self.assertEqual(export.status_code, 200)
            export_payload = export.json()
            self.assertEqual(export_payload["range"]["mode"], "time")
            self.assertEqual(export_payload["range"]["resolved_mode"], "sample_index")
            self.assertEqual(export_payload["range"]["start_index"], 1)
            self.assertEqual(export_payload["range"]["end_index"], 4)
            self.assertEqual(export_payload["range"]["sample_count"], 3)
            self.assertEqual(export_payload["manifest"]["range"]["mode"], "time")
            csv_text = client.get(f"/api/artifacts/{export_payload['artifact']['artifact_id']}").text
            rows = list(csv.DictReader(csv_text.splitlines()))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["sample_index"], "1")
            self.assertEqual(rows[0]["B_FGM_0"], "3.0")

    def test_cses_utc_time_parser_accepts_dotted_and_byte_values(self) -> None:
        parsed = parse_cses_utc_time_millis(
            np.array(
                [
                    b"20230419235544.000",
                    "20230419235545.250",
                    20230419235546250,
                ],
                dtype=object,
            )
        )

        self.assertEqual(parsed[1] - parsed[0], 1250)
        self.assertEqual(parsed[2] - parsed[1], 1000)

    def test_cluster_processed_subset_stats_and_export_use_daily_full_only(self) -> None:
        client = TestClient(create_app())

        subset = client.post(
            "/api/datasources/cluster/subset",
            json={
                "file_id": "20051203",
                "variables": ["segment_B_MFA_after_delete", "segment_MLAT"],
                "range": {"mode": "sample_index", "start_index": 0, "end_index": 5},
                "preview_limit": 5,
            },
        )
        self.assertEqual(subset.status_code, 200)
        subset_payload = subset.json()
        self.assertEqual(subset_payload["range"]["sample_count"], 5)
        self.assertEqual(subset_payload["variables"][0]["path"], "segment_B_MFA_after_delete")
        self.assertEqual(len(subset_payload["variables"][0]["data"]), 5)

        stats = client.post(
            "/api/datasources/cluster/stats",
            json={
                "file_id": "20051203",
                "variables": ["segment_B_MFA_after_delete", "segment_MLAT"],
                "range": {"mode": "sample_index", "start_index": 0, "end_index": 10},
            },
        )
        self.assertEqual(stats.status_code, 200)
        stats_payload = stats.json()
        by_name = {item["path"]: item for item in stats_payload["variables"]}
        self.assertEqual(by_name["segment_B_MFA_after_delete"]["component_count"], 3)
        self.assertEqual(by_name["segment_MLAT"]["component_count"], 1)
        self.assertEqual(by_name["segment_B_MFA_after_delete"]["stats"][0]["count"], 10)

        saved_cluster_stats = client.post(
            "/api/datasources/cluster/stats",
            json={
                "file_id": "20051203",
                "variables": ["segment_B_MFA_after_delete"],
                "range": {"mode": "sample_index", "start_index": 0, "end_index": 10},
                "save_format": "json",
            },
        )
        self.assertEqual(saved_cluster_stats.status_code, 200)
        cluster_stats_artifact = saved_cluster_stats.json()["stats_artifact"]
        self.assertEqual(cluster_stats_artifact["media_type"], "application/json")
        self.assertTrue(str(cluster_stats_artifact["artifact_id"]).startswith("cluster:stats:20051203:"))
        self.assertIn("/Volumes/Elements/satellite_data_web/outputs/stats", cluster_stats_artifact["path"])
        self.assertNotIn("/Volumes/Elements/data/cluster", cluster_stats_artifact["path"])

        saved_cluster_dat_stats = client.post(
            "/api/datasources/cluster/stats",
            json={
                "file_id": "20051203",
                "variables": ["segment_MLAT"],
                "range": {"mode": "sample_index", "start_index": 0, "end_index": 3},
                "save_format": "dat",
            },
        )
        self.assertEqual(saved_cluster_dat_stats.status_code, 200)
        cluster_dat_stats_artifact = saved_cluster_dat_stats.json()["stats_artifact"]
        self.assertEqual(cluster_dat_stats_artifact["media_type"], "text/plain")
        self.assertIn("/Volumes/Elements/satellite_data_web/outputs/stats", cluster_dat_stats_artifact["path"])
        self.assertNotIn("/Volumes/Elements/data/cluster", cluster_dat_stats_artifact["path"])
        cluster_dat_stats_text = client.get(f"/api/artifacts/{cluster_dat_stats_artifact['artifact_id']}").text
        self.assertTrue(cluster_dat_stats_text.startswith("variable\tcomponent\tcount\tfinite_count\tmin\tmax\tmean\tmedian\tstd\tmissing_ratio\n"))
        self.assertIn("segment_MLAT\t0\t3\t3", cluster_dat_stats_text)

        saved_cluster_cdf_stats = client.post(
            "/api/datasources/cluster/stats",
            json={
                "file_id": "20051203",
                "variables": ["segment_MLAT"],
                "range": {"mode": "sample_index", "start_index": 0, "end_index": 3},
                "save_format": "cdf",
            },
        )
        self.assertEqual(saved_cluster_cdf_stats.status_code, 200)
        cluster_cdf_stats_payload = saved_cluster_cdf_stats.json()
        self.assertEqual(cluster_cdf_stats_payload["status"], "unsupported")
        self.assertEqual(cluster_cdf_stats_payload["save_format"], "cdf")
        self.assertEqual(cluster_cdf_stats_payload["reserved"], True)
        self.assertNotIn("stats_artifact", cluster_cdf_stats_payload)
        self.assertIn("CDF remains reserved", cluster_cdf_stats_payload["reason"])

        export = client.post(
            "/api/datasources/cluster/export",
            json={
                "file_id": "20051203",
                "variables": ["segment_B_MFA_after_delete", "segment_MLAT"],
                "range": {"mode": "sample_index", "start_index": 0, "end_index": 3},
                "format": "csv",
            },
        )
        self.assertEqual(export.status_code, 200)
        export_payload = export.json()
        artifact = export_payload["artifact"]
        self.assertTrue(str(artifact["artifact_id"]).startswith("cluster:export:20051203:"))
        self.assertIn("/Volumes/Elements/satellite_data_web/outputs/exports", artifact["path"])
        self.assertNotIn("/Volumes/Elements/data/cluster", artifact["path"])
        self.assertIn("manifest_artifact", export_payload)
        self.assertEqual(export_payload["manifest"]["datasource"], "cluster")
        self.assertEqual(export_payload["manifest"]["export_format"], "csv")
        self.assertEqual(export_payload["manifest"]["sample_count"], 3)
        self.assertEqual(export_payload["manifest"]["variables"][0]["path"], "segment_B_MFA_after_delete")

        artifact_response = client.get(f"/api/artifacts/{artifact['artifact_id']}")
        self.assertEqual(artifact_response.status_code, 200)
        rows = list(csv.DictReader(artifact_response.text.splitlines()))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["sample_index"], "0")
        self.assertIn("segment_B_MFA_after_delete_0", rows[0])
        self.assertIn("segment_MLAT", rows[0])

        manifest_response = client.get(f"/api/artifacts/{export_payload['manifest_artifact']['artifact_id']}")
        self.assertEqual(manifest_response.status_code, 200)
        self.assertIn("/Volumes/Elements/data/idlpython_v2/daily_full/2005/daily_full_20051203.npz", manifest_response.json()["original_file"])

        dat_export = client.post(
            "/api/datasources/cluster/export",
            json={
                "file_id": "20051203",
                "variables": ["segment_MLAT"],
                "range": {"mode": "sample_index", "start_index": 0, "end_index": 2},
                "format": "dat",
            },
        )
        self.assertEqual(dat_export.status_code, 200)
        dat_artifact = dat_export.json()["artifact"]
        self.assertEqual(dat_artifact["media_type"], "text/plain")
        self.assertIn("/Volumes/Elements/satellite_data_web/outputs/exports", dat_artifact["path"])
        self.assertNotIn("/Volumes/Elements/data/cluster", dat_artifact["path"])
        dat_text = client.get(f"/api/artifacts/{dat_artifact['artifact_id']}").text
        self.assertTrue(dat_text.startswith("sample_index\tsegment_MLAT\n"))

        cluster_cdf_export = client.post(
            "/api/datasources/cluster/export",
            json={
                "file_id": "20051203",
                "variables": ["segment_MLAT"],
                "range": {"mode": "sample_index", "start_index": 0, "end_index": 2},
                "format": "cdf",
            },
        )
        self.assertEqual(cluster_cdf_export.status_code, 200)
        cluster_cdf_payload = cluster_cdf_export.json()
        self.assertEqual(cluster_cdf_payload["status"], "unsupported")
        self.assertEqual(cluster_cdf_payload["format"], "cdf")
        self.assertEqual(cluster_cdf_payload["reserved"], True)
        self.assertNotIn("artifact", cluster_cdf_payload)
        self.assertIn("CDF remains reserved", cluster_cdf_payload["reason"])

    def test_cluster_time_range_uses_confirmed_processed_time_axis(self) -> None:
        client = TestClient(create_app())
        range_spec = {
            "mode": "time",
            "start": "2005-12-03T14:45:11.122997Z",
            "end": "2005-12-03T14:45:23.527997Z",
        }

        subset = client.post(
            "/api/datasources/cluster/subset",
            json={
                "file_id": "20051203",
                "variables": ["segment_MLAT"],
                "range": range_spec,
                "preview_limit": 20,
            },
        )
        self.assertEqual(subset.status_code, 200)
        subset_payload = subset.json()
        self.assertEqual(subset_payload["range"]["mode"], "time")
        self.assertEqual(subset_payload["range"]["resolved_mode"], "sample_index")
        self.assertEqual(subset_payload["range"]["start_index"], 2)
        self.assertEqual(subset_payload["range"]["end_index"], 5)
        self.assertEqual(subset_payload["range"]["sample_count"], 3)
        self.assertEqual(subset_payload["range"]["time_variable"], "segment_time_context_unix")
        self.assertEqual(subset_payload["range"]["time_confidence"], "confirmed")

        timeseries = client.post(
            "/api/datasources/cluster/timeseries",
            json={
                "file_id": "20051203",
                "variables": ["segment_MLAT"],
                "range": range_spec,
            },
        )
        self.assertEqual(timeseries.status_code, 200)
        timeseries_payload = timeseries.json()
        self.assertEqual(timeseries_payload["range"]["start_index"], 2)
        self.assertEqual(timeseries_payload["range"]["end_index"], 5)
        self.assertEqual(timeseries_payload["time_axis"]["kind"], "utc")
        self.assertEqual(timeseries_payload["time_axis"]["path"], "segment_time_context_unix")
        self.assertEqual(timeseries_payload["time_axis"]["confidence"], "confirmed")
        self.assertEqual(
            timeseries_payload["time_axis"]["data"],
            [
                "2005-12-03T14:45:11.123001Z",
                "2005-12-03T14:45:15.259003Z",
                "2005-12-03T14:45:19.393997Z",
            ],
        )

        stats = client.post(
            "/api/datasources/cluster/stats",
            json={
                "file_id": "20051203",
                "variables": ["segment_MLAT"],
                "range": range_spec,
            },
        )
        self.assertEqual(stats.status_code, 200)
        stats_payload = stats.json()
        self.assertEqual(stats_payload["range"]["sample_count"], 3)
        self.assertEqual(stats_payload["variables"][0]["stats"][0]["count"], 3)

        export = client.post(
            "/api/datasources/cluster/export",
            json={
                "file_id": "20051203",
                "variables": ["segment_MLAT"],
                "range": range_spec,
                "format": "csv",
            },
        )
        self.assertEqual(export.status_code, 200)
        export_payload = export.json()
        self.assertEqual(export_payload["range"]["mode"], "time")
        self.assertEqual(export_payload["range"]["resolved_mode"], "sample_index")
        self.assertEqual(export_payload["manifest"]["range"]["time_confidence"], "confirmed")
        csv_text = client.get(f"/api/artifacts/{export_payload['artifact']['artifact_id']}").text
        rows = list(csv.DictReader(csv_text.splitlines()))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["sample_index"], "2")

    def test_cses_batch_stats_sort_deduplicate_and_summarize_selected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hpm_root = root / "HPM"
            output_root = root / "outputs"
            hpm_root.mkdir()

            with h5py.File(hpm_root / "a.h5", "w") as h5:
                h5.create_dataset("UTC_TIME", data=np.array([3, 1, 2], dtype=np.int64).reshape(3, 1))
                h5.create_dataset("B_FGM", data=np.array([[30.0, 0.0, 0.0], [10.0, 0.0, 0.0], [20.0, 0.0, 0.0]]))
                h5.create_dataset("FLAG_MT", data=np.array([1, 0, 0], dtype=np.int32).reshape(3, 1))
                h5.create_dataset("GEO_LAT", data=np.array([13.0, 11.0, 12.0], dtype=np.float32).reshape(3, 1))
                h5.create_dataset("GEO_LON", data=np.array([103.0, 101.0, 102.0], dtype=np.float32).reshape(3, 1))
                h5.create_dataset("ALTITUDE", data=np.array([503.0, 501.0, 502.0], dtype=np.float32).reshape(3, 1))

            with h5py.File(hpm_root / "b.h5", "w") as h5:
                h5.create_dataset("UTC_TIME", data=np.array([2, 4], dtype=np.int64).reshape(2, 1))
                h5.create_dataset("B_FGM", data=np.array([[200.0, 0.0, 0.0], [40.0, 0.0, 0.0]]))
                h5.create_dataset("FLAG_MT", data=np.array([9, 1], dtype=np.int32).reshape(2, 1))
                h5.create_dataset("GEO_LAT", data=np.array([22.0, 14.0], dtype=np.float32).reshape(2, 1))
                h5.create_dataset("GEO_LON", data=np.array([122.0, 104.0], dtype=np.float32).reshape(2, 1))
                h5.create_dataset("ALTITUDE", data=np.array([602.0, 504.0], dtype=np.float32).reshape(2, 1))

            inspect_h5_tree(hpm_root, output_root / "cses_hpm_inspection", max_preview=2, sample_size=16)
            config_path = root / "local_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "cluster_raw_root": str(root / "cluster"),
                        "cluster_processed_root": str(root / "idlpython_v2"),
                        "cses_hpm_root": str(hpm_root),
                        "outputs_root": str(output_root),
                    }
                ),
                encoding="utf-8",
            )
            client = TestClient(create_app(config_path=config_path))

            response = client.post(
                "/api/datasources/cses_hpm/stats",
                json={
                    "file_ids": ["a.h5", "b.h5"],
                    "variables": ["/B_FGM"],
                    "time_variable": "/UTC_TIME",
                    "flag_variable": "/FLAG_MT",
                    "position_variables": {"lat": "/GEO_LAT", "lon": "/GEO_LON", "alt": "/ALTITUDE"},
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 5},
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["mode"], "batch")
            self.assertEqual(payload["raw_sample_count"], 5)
            self.assertEqual(payload["sample_count"], 4)
            self.assertEqual(payload["duplicate_count"], 1)
            self.assertEqual(payload["time_range"], {"start": 1, "end": 4})
            self.assertEqual(payload["cadence"]["median"], 1.0)
            self.assertEqual(payload["quality_flags"]["/FLAG_MT"]["distribution"], {"0": 2, "1": 2})
            self.assertEqual(payload["spatial_coverage"]["lat"], {"min": 11.0, "max": 14.0})
            by_name = {item["path"]: item for item in payload["variables"]}
            self.assertEqual(by_name["/B_FGM"]["stats"][0]["min"], 10.0)
            self.assertEqual(by_name["/B_FGM"]["stats"][0]["max"], 40.0)
            self.assertEqual(by_name["/B_FGM"]["stats"][0]["median"], 25.0)
            self.assertEqual(payload["vector_magnitude"]["/B_FGM|magnitude"]["stats"][0]["mean"], 25.0)

            saved_response = client.post(
                "/api/datasources/cses_hpm/stats",
                json={
                    "file_ids": ["a.h5", "b.h5"],
                    "variables": ["/B_FGM"],
                    "time_variable": "/UTC_TIME",
                    "flag_variable": "/FLAG_MT",
                    "position_variables": {"lat": "/GEO_LAT", "lon": "/GEO_LON", "alt": "/ALTITUDE"},
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 5},
                    "save_format": "json",
                },
            )
            self.assertEqual(saved_response.status_code, 200)
            saved_payload = saved_response.json()
            self.assertIn("stats_artifact", saved_payload)
            self.assertTrue(str(saved_payload["stats_artifact"]["artifact_id"]).startswith("cses_hpm:stats:batch:"))
            saved_artifact = client.get(f"/api/artifacts/{saved_payload['stats_artifact']['artifact_id']}")
            self.assertEqual(saved_artifact.status_code, 200)
            self.assertEqual(saved_artifact.json()["mode"], "batch")
            self.assertEqual(saved_artifact.json()["sample_count"], 4)

            batch_plot = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "plot_type": "batch_magnetic_timeseries",
                    "file_ids": ["a.h5", "b.h5"],
                    "variables": ["/B_FGM"],
                    "time_variable": "/UTC_TIME",
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 5},
                },
            )
            self.assertEqual(batch_plot.status_code, 200)
            batch_plot_payload = batch_plot.json()
            self.assertEqual(batch_plot_payload["mode"], "batch")
            self.assertEqual(batch_plot_payload["plot_type"], "batch_magnetic_timeseries")
            self.assertEqual(batch_plot_payload["raw_sample_count"], 5)
            self.assertEqual(batch_plot_payload["sample_count"], 4)
            self.assertEqual(batch_plot_payload["duplicate_count"], 1)
            self.assertEqual(batch_plot_payload["time_range"], {"start": 1, "end": 4})
            self.assertEqual(batch_plot_payload["artifact"]["media_type"], "image/png")
            self.assertIn(str(output_root / "plots"), batch_plot_payload["artifact"]["path"])
            self.assertNotIn(str(hpm_root), batch_plot_payload["artifact"]["path"])
            batch_plot_artifact = client.get(f"/api/artifacts/{batch_plot_payload['artifact']['artifact_id']}")
            self.assertEqual(batch_plot_artifact.status_code, 200)
            self.assertEqual(batch_plot_artifact.headers["content-type"].split(";")[0], "image/png")
            self.assertTrue(batch_plot_artifact.content.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
