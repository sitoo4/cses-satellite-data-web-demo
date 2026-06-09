from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import create_app


class ClusterDatasourceApiTest(unittest.TestCase):
    def test_cluster_processed_outputs_are_listed_and_served_read_only(self) -> None:
        client = TestClient(create_app())

        datasources = client.get("/api/datasources")
        self.assertEqual(datasources.status_code, 200)
        cluster_summary = next(item for item in datasources.json()["datasources"] if item["name"] == "cluster")
        self.assertFalse(cluster_summary["capabilities"]["plot_existing"])
        self.assertIn("plot_generate", cluster_summary["capabilities"])
        self.assertTrue(cluster_summary["capabilities"]["plot_generate"])

        catalog = client.get("/api/datasources/cluster/plot-catalog", params={"file_id": "20051203"})
        self.assertEqual(catalog.status_code, 200)
        catalog_payload = catalog.json()
        self.assertEqual(catalog_payload["datasource"], "cluster")
        self.assertEqual(catalog_payload["datasource_type"], "Cluster CDF multi-instrument datasource")
        catalog_by_type = {item["plot_type"]: item for item in catalog_payload["plots"]}
        self.assertEqual(
            list(catalog_by_type),
            [
                "cluster_magnetic_overview",
                "cluster_electric_overview",
                "cluster_spectrogram_overview",
                "cluster_orbit_overview",
            ],
        )
        self.assertTrue(catalog_by_type["cluster_magnetic_overview"]["enabled"])
        self.assertEqual(catalog_by_type["cluster_magnetic_overview"]["output_group"], "cluster")
        self.assertEqual(
            catalog_by_type["cluster_magnetic_overview"]["confirmed_fields"],
            [
                "segment_time_context_unix",
                "segment_time_wavelet_unix",
                "segment_frequency_axis",
                "segment_B_GSE",
                "segment_B_MFA_after_delete",
                "segment_dB_MFA_detrended",
                "segment_dB_radial_psd",
                "segment_dB_phi_psd",
                "segment_dB_parallel_psd",
                "segment_sqrt_Br_band_power",
                "segment_sqrt_Bphi_band_power",
                "segment_sqrt_Bpar_band_power",
                "segment_L",
                "segment_MLT",
                "segment_MLAT",
            ],
        )
        self.assertTrue(catalog_by_type["cluster_electric_overview"]["enabled"])
        self.assertTrue(catalog_by_type["cluster_spectrogram_overview"]["enabled"])
        self.assertTrue(catalog_by_type["cluster_orbit_overview"]["enabled"])
        self.assertNotIn("cluster_solar_wind_overview", catalog_by_type)

        files = client.get("/api/datasources/cluster/files", params={"year": "2005", "limit": 200})
        self.assertEqual(files.status_code, 200)
        payload = files.json()
        self.assertEqual(payload["datasource"], "cluster")
        self.assertGreaterEqual(payload["total_count"], 157)
        by_date = {item["file_id"]: item for item in payload["files"]}
        self.assertIn("20051203", by_date)
        self.assertTrue(by_date["20051203"]["products"]["daily_full"]["exists"])
        self.assertTrue(by_date["20051203"]["products"]["quicklook_B"]["exists"])

        metadata = client.get("/api/datasources/cluster/metadata", params={"file_id": "20051203"})
        self.assertEqual(metadata.status_code, 200)
        meta = metadata.json()
        self.assertEqual(meta["file_id"], "20051203")
        self.assertEqual(meta["daily_full"]["key_count"], 74)
        self.assertEqual(meta["daily_compact"]["column_count"], 41)
        self.assertEqual(meta["manifest"]["quicklook_window_mode"], "segment_only")
        self.assertEqual(meta["time_summary"]["status"], "parsed")
        self.assertEqual(meta["time_summary"]["time_variable"], "segment_time_context_unix")
        self.assertEqual(meta["time_summary"]["time_confidence"], "confirmed")
        self.assertEqual(meta["time_summary"]["time_units"], "unix_seconds")
        self.assertEqual(meta["time_summary"]["sample_count"], 3191)
        self.assertEqual(meta["time_summary"]["start"], "2005-12-03T14:45:02.852997Z")
        self.assertEqual(meta["time_summary"]["end"], "2005-12-03T18:24:58.252998Z")
        self.assertAlmostEqual(meta["time_summary"]["cadence_ms"]["median"], 4135.002, places=3)
        self.assertEqual(meta["quality_summary"]["status"], "parsed")
        self.assertEqual(meta["quality_summary"]["flag_variable"], "segment_E_quality")
        self.assertEqual(meta["quality_summary"]["flag_confidence"], "confirmed")
        self.assertEqual(meta["quality_summary"]["sample_count"], 3299)
        self.assertEqual(meta["quality_summary"]["distribution"], {"0": 6, "1": 1023, "2": 178, "3": 2092})
        self.assertIn("segment_B_MFA_after_delete", {item["name"] for item in meta["daily_full"]["keys"]})

        variables = client.get("/api/datasources/cluster/variables", params={"file_id": "20051203"})
        self.assertEqual(variables.status_code, 200)
        by_name = {item["name"]: item for item in variables.json()["variables"]}
        self.assertEqual(by_name["segment_B_MFA_after_delete"]["data_kind"], "magnetic_vector")
        self.assertEqual(by_name["segment_E_MFA"]["data_kind"], "electric_vector")
        self.assertEqual(by_name["segment_dB_phi_psd"]["data_kind"], "spectrogram")
        self.assertEqual(by_name["segment_MLAT"]["data_kind"], "context")

        timeseries = client.post(
            "/api/datasources/cluster/timeseries",
            json={
                "file_id": "20051203",
                "variables": ["segment_MLAT"],
                "range": {"mode": "sample_index", "start_index": 2, "end_index": 5},
            },
        )
        self.assertEqual(timeseries.status_code, 200)
        timeseries_payload = timeseries.json()
        self.assertEqual(timeseries_payload["datasource"], "cluster")
        self.assertEqual(timeseries_payload["range"]["sample_count"], 3)
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
        self.assertEqual(timeseries_payload["variables"][0]["path"], "segment_MLAT")
        self.assertEqual(len(timeseries_payload["variables"][0]["data"]), 3)

        quicklook = client.post(
            "/api/datasources/cluster/plot",
            json={"file_id": "20051203", "plot_type": "existing_quicklook_b"},
        )
        self.assertEqual(quicklook.status_code, 200)
        self.assertEqual(quicklook.json()["status"], "unsupported")
        self.assertIn("Existing quicklook images are reference/debug only", quicklook.json()["reason"])
        self.assertNotIn("artifact", quicklook.json())

        magnetic_overview = client.post(
            "/api/datasources/cluster/plot",
            json={"file_id": "20051203", "plot_type": "cluster_magnetic_overview", "range": {"mode": "sample_index", "start_index": 0, "end_index": 64}},
        )
        self.assertEqual(magnetic_overview.status_code, 200)
        magnetic_payload = magnetic_overview.json()
        self.assertEqual(magnetic_payload["plot_type"], "cluster_magnetic_overview")
        self.assertEqual(magnetic_payload["source_product"], "daily_full")
        self.assertEqual(magnetic_payload["coordinate_system"], "GSE/MFA stored segment fields")
        field_paths = {field["path"] for field in magnetic_payload["fields"]}
        self.assertIn("segment_B_GSE", field_paths)
        self.assertIn("segment_B_MFA_after_delete", field_paths)
        self.assertIn("segment_dB_phi_psd", field_paths)
        self.assertIn("segment_sqrt_Bphi_band_power", field_paths)
        self.assertIn("outputs/generated_plots/cluster", magnetic_payload["artifact"]["path"])
        self.assertEqual(magnetic_payload["processing_log"][1], "Matched /Volumes/Elements/data/idlpython_v2/plot_daily_quicklook.py B panel recipe.")
        magnetic_artifact = client.get(f"/api/artifacts/{magnetic_payload['artifact']['artifact_id']}")
        self.assertEqual(magnetic_artifact.status_code, 200)
        self.assertEqual(magnetic_artifact.headers["content-type"], "image/png")
        self.assertGreater(len(magnetic_artifact.content), 1000)

        spectrogram = client.post(
            "/api/datasources/cluster/plot",
            json={"file_id": "20051203", "plot_type": "cluster_spectrogram_overview"},
        )
        self.assertEqual(spectrogram.status_code, 200)
        spectrogram_payload = spectrogram.json()
        self.assertEqual(spectrogram_payload["plot_type"], "cluster_spectrogram_overview")
        self.assertEqual(spectrogram_payload["source_product"], "daily_full")
        self.assertEqual(spectrogram_payload["psd_variables"], ["segment_dB_phi_psd", "segment_dE_phi_psd"])
        self.assertIn("outputs/generated_plots/cluster", spectrogram_payload["artifact"]["path"])
        spectrogram_artifact_id = spectrogram_payload["artifact"]["artifact_id"]
        self.assertTrue(spectrogram_artifact_id.startswith("cluster:spectrogram_overview:20051203"))
        spectrogram_artifact = client.get(f"/api/artifacts/{spectrogram_artifact_id}")
        self.assertEqual(spectrogram_artifact.status_code, 200)
        self.assertEqual(spectrogram_artifact.headers["content-type"], "image/png")
        self.assertGreater(len(spectrogram_artifact.content), 1000)

        electric_overview = client.post(
            "/api/datasources/cluster/plot",
            json={"file_id": "20051203", "plot_type": "cluster_electric_overview", "range": {"mode": "sample_index", "start_index": 0, "end_index": 64}},
        )
        self.assertEqual(electric_overview.status_code, 200)
        electric_payload = electric_overview.json()
        self.assertEqual(electric_payload["plot_type"], "cluster_electric_overview")
        self.assertEqual(electric_payload["fields"][0]["path"], "segment_E_MFA")
        self.assertEqual(electric_payload["fields"][0]["unit"], "mV/m")
        self.assertIn("outputs/generated_plots/cluster", electric_payload["artifact"]["path"])

        generated_timeseries = client.post(
            "/api/datasources/cluster/plot",
            json={
                "file_id": "20051203",
                "plot_type": "timeseries",
                "variables": ["segment_B_MFA_after_delete"],
                "range": {"mode": "sample_index", "start_index": 0, "end_index": 64},
            },
        )
        self.assertEqual(generated_timeseries.status_code, 200)
        generated_timeseries_payload = generated_timeseries.json()
        self.assertEqual(generated_timeseries_payload["plot_type"], "timeseries")
        self.assertEqual(generated_timeseries_payload["source_product"], "daily_full")
        self.assertEqual(generated_timeseries_payload["range"]["sample_count"], 64)
        self.assertEqual(generated_timeseries_payload["artifact"]["media_type"], "image/png")
        generated_timeseries_artifact = client.get(f"/api/artifacts/{generated_timeseries_payload['artifact']['artifact_id']}")
        self.assertEqual(generated_timeseries_artifact.status_code, 200)
        self.assertEqual(generated_timeseries_artifact.headers["content-type"], "image/png")
        self.assertGreater(len(generated_timeseries_artifact.content), 1000)

        generated_e_timeseries = client.post(
            "/api/datasources/cluster/plot",
            json={
                "file_id": "20051203",
                "plot_type": "electric_timeseries",
                "range": {"mode": "sample_index", "start_index": 0, "end_index": 64},
            },
        )
        self.assertEqual(generated_e_timeseries.status_code, 200)
        generated_e_payload = generated_e_timeseries.json()
        self.assertEqual(generated_e_payload["plot_type"], "electric_timeseries")
        self.assertEqual(generated_e_payload["source_product"], "daily_full")
        self.assertEqual(generated_e_payload["variable"], "segment_E_MFA")
        self.assertEqual(generated_e_payload["range"]["sample_count"], 64)
        generated_e_artifact = client.get(f"/api/artifacts/{generated_e_payload['artifact']['artifact_id']}")
        self.assertEqual(generated_e_artifact.status_code, 200)
        self.assertEqual(generated_e_artifact.headers["content-type"], "image/png")
        self.assertGreater(len(generated_e_artifact.content), 1000)

        generated_orbit = client.post(
            "/api/datasources/cluster/plot",
            json={
                "file_id": "20051203",
                "plot_type": "orbit_2d",
                "range": {"mode": "sample_index", "start_index": 0, "end_index": 64},
            },
        )
        self.assertEqual(generated_orbit.status_code, 200)
        generated_orbit_payload = generated_orbit.json()
        self.assertEqual(generated_orbit_payload["plot_type"], "orbit_2d")
        self.assertEqual(generated_orbit_payload["source_product"], "daily_full")
        self.assertEqual(generated_orbit_payload["coordinate_variables"], ["segment_MLT", "segment_MLAT"])
        self.assertEqual(generated_orbit_payload["artifact"]["media_type"], "image/png")
        generated_orbit_artifact = client.get(f"/api/artifacts/{generated_orbit_payload['artifact']['artifact_id']}")
        self.assertEqual(generated_orbit_artifact.status_code, 200)
        self.assertEqual(generated_orbit_artifact.headers["content-type"], "image/png")
        self.assertGreater(len(generated_orbit_artifact.content), 1000)

        generated_orbit_3d = client.post(
            "/api/datasources/cluster/plot",
            json={
                "file_id": "20051203",
                "plot_type": "orbit_3d",
                "range": {"mode": "sample_index", "start_index": 0, "end_index": 64},
            },
        )
        self.assertEqual(generated_orbit_3d.status_code, 200)
        generated_orbit_3d_payload = generated_orbit_3d.json()
        self.assertEqual(generated_orbit_3d_payload["plot_type"], "orbit_3d")
        self.assertEqual(generated_orbit_3d_payload["source_product"], "daily_full")
        self.assertEqual(generated_orbit_3d_payload["coordinate_variables"], ["segment_MLT", "segment_MLAT", "segment_L"])
        self.assertEqual(generated_orbit_3d_payload["artifact"]["media_type"], "image/png")
        generated_orbit_3d_artifact = client.get(f"/api/artifacts/{generated_orbit_3d_payload['artifact']['artifact_id']}")
        self.assertEqual(generated_orbit_3d_artifact.status_code, 200)
        self.assertEqual(generated_orbit_3d_artifact.headers["content-type"], "image/png")
        self.assertGreater(len(generated_orbit_3d_artifact.content), 1000)

        orbit_overview = client.post(
            "/api/datasources/cluster/plot",
            json={
                "file_id": "20051203",
                "plot_type": "cluster_orbit_overview",
                "range": {"mode": "sample_index", "start_index": 0, "end_index": 64},
            },
        )
        self.assertEqual(orbit_overview.status_code, 200)
        orbit_overview_payload = orbit_overview.json()
        self.assertEqual(orbit_overview_payload["plot_type"], "cluster_orbit_overview")
        self.assertEqual(orbit_overview_payload["coordinate_variables"], ["segment_MLT", "segment_MLAT", "segment_L"])
        self.assertIn("outputs/generated_plots/cluster", orbit_overview_payload["artifact"]["path"])

        solar_wind = client.post(
            "/api/datasources/cluster/plot",
            json={"file_id": "20051203", "plot_type": "cluster_solar_wind_overview"},
        )
        self.assertEqual(solar_wind.status_code, 200)
        solar_payload = solar_wind.json()
        self.assertEqual(solar_payload["status"], "unavailable")
        self.assertEqual(solar_payload["plot_type"], "cluster_solar_wind_overview")
        self.assertIn("flow_speed", solar_payload["missing_fields"])
        self.assertIn("SYM-H", solar_payload["missing_fields"])
        self.assertIn("not exposed in daily_full", solar_payload["reason"])
        self.assertNotIn("artifact", solar_payload)


if __name__ == "__main__":
    unittest.main()
