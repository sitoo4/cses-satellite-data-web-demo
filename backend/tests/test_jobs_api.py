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


class JobsApiTest(unittest.TestCase):
    def test_plot_export_and_stats_register_completed_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hpm_root = root / "HPM"
            output_root = root / "outputs"
            hpm_root.mkdir()
            with h5py.File(hpm_root / "sample.h5", "w") as h5:
                h5.create_dataset("UTC_TIME", data=np.arange(8, dtype=np.int64).reshape(8, 1))
                h5.create_dataset("B_FGM", data=np.arange(24, dtype=np.float64).reshape(8, 3))
                h5.create_dataset("FLAG_MT", data=np.array([0, 1, 0, 1, 0, 1, 0, 1], dtype=np.int32).reshape(8, 1))

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

            plot_response = client.post(
                "/api/datasources/cses_hpm/plot",
                json={
                    "file_id": "sample.h5",
                    "plot_type": "magnetic_timeseries",
                    "variables": ["/B_FGM"],
                    "time_variable": "/UTC_TIME",
                    "range": {"mode": "sample_index", "start_index": 1, "end_index": 5},
                },
            )
            self.assertEqual(plot_response.status_code, 200)
            plot_payload = plot_response.json()
            self.assertIn("job_id", plot_payload)

            plot_job = client.get(f"/api/jobs/{plot_payload['job_id']}")
            self.assertEqual(plot_job.status_code, 200)
            plot_job_payload = plot_job.json()
            self.assertEqual(plot_job_payload["job_id"], plot_payload["job_id"])
            self.assertEqual(plot_job_payload["status"], "completed")
            self.assertEqual(plot_job_payload["kind"], "plot")
            self.assertEqual(plot_job_payload["datasource"], "cses_hpm")
            self.assertEqual(plot_job_payload["result"]["plot_type"], "magnetic_timeseries")
            self.assertEqual(plot_job_payload["result"]["artifact"]["media_type"], "image/png")

            export_response = client.post(
                "/api/datasources/cses_hpm/export",
                json={
                    "file_id": "sample.h5",
                    "variables": ["/B_FGM"],
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 3},
                    "format": "csv",
                },
            )
            self.assertEqual(export_response.status_code, 200)
            export_payload = export_response.json()
            export_job = client.get(f"/api/jobs/{export_payload['job_id']}")
            self.assertEqual(export_job.status_code, 200)
            export_job_payload = export_job.json()
            self.assertEqual(export_job_payload["kind"], "export")
            self.assertEqual(export_job_payload["result"]["format"], "csv")
            self.assertEqual(export_job_payload["result"]["artifact"]["media_type"], "text/csv")
            self.assertEqual(export_job_payload["result"]["manifest_artifact"]["media_type"], "application/json")

            stats_response = client.post(
                "/api/datasources/cses_hpm/stats",
                json={
                    "file_id": "sample.h5",
                    "variables": ["/B_FGM", "/FLAG_MT"],
                    "range": {"mode": "sample_index", "start_index": 0, "end_index": 4},
                },
            )
            self.assertEqual(stats_response.status_code, 200)
            stats_payload = stats_response.json()
            stats_job = client.get(f"/api/jobs/{stats_payload['job_id']}")
            self.assertEqual(stats_job.status_code, 200)
            stats_job_payload = stats_job.json()
            self.assertEqual(stats_job_payload["kind"], "stats")
            self.assertEqual(stats_job_payload["result"]["file_id"], "sample.h5")
            self.assertEqual(stats_job_payload["result"]["range"]["sample_count"], 4)

    def test_unknown_job_returns_404(self) -> None:
        client = TestClient(create_app())

        response = client.get("/api/jobs/not-a-real-job")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "job_not_found")


if __name__ == "__main__":
    unittest.main()
