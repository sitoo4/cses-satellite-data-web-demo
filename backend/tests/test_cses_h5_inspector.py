from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from app.services.cses_h5_inspector import inspect_h5_file


class CsesH5InspectorTest(unittest.TestCase):
    def test_inspects_tree_attrs_candidates_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            h5_path = root / "sample_hpm.h5"
            out_root = root / "inspection"

            with h5py.File(h5_path, "w") as h5:
                h5.attrs["Mission"] = "CSES-01"
                group = h5.create_group("Data")
                time = group.create_dataset("UTC_TIME", data=np.arange(10, dtype=np.float64))
                time.attrs["units"] = "seconds since 2024-01-01T00:00:00Z"
                time.attrs["long_name"] = "UTC time"

                b = group.create_dataset(
                    "B_NEC",
                    data=np.column_stack(
                        [
                            np.linspace(1.0, 2.0, 10),
                            np.linspace(2.0, 3.0, 10),
                            np.linspace(3.0, 4.0, 10),
                        ]
                    ),
                )
                b.attrs["units"] = "nT"
                b.attrs["description"] = "three-component magnetic field"
                b.attrs["valid_range"] = np.array([-70000.0, 70000.0])

                f = group.create_dataset("F", data=np.linspace(4.0, 5.0, 10))
                f.attrs["units"] = "nT"
                f.attrs["long_name"] = "magnetic field scalar"

                for name, values, units in [
                    ("Latitude", np.linspace(-10.0, 10.0, 10), "degree"),
                    ("Longitude", np.linspace(100.0, 110.0, 10), "degree"),
                    ("Altitude", np.linspace(500.0, 510.0, 10), "km"),
                ]:
                    ds = group.create_dataset(name, data=values)
                    ds.attrs["units"] = units

                quality = group.create_dataset("Quality_Flag", data=np.array([0, 1] * 5, dtype=np.uint8))
                quality.attrs["description"] = "quality flag"

                group.create_dataset("FLAG_MT", data=np.array([1, 0] * 5, dtype=np.int32))

            result = inspect_h5_file(h5_path, out_root, input_root=root, max_preview=3, sample_size=5)

            self.assertEqual(result["file"]["relative_path"], "sample_hpm.h5")
            self.assertTrue((out_root / "sample_hpm" / "h5_tree.json").exists())
            self.assertTrue((out_root / "sample_hpm" / "h5_tree.txt").exists())
            self.assertTrue((out_root / "sample_hpm" / "summary.json").exists())
            self.assertTrue((out_root / "sample_hpm" / "report.md").exists())

            summary = json.loads((out_root / "sample_hpm" / "summary.json").read_text())
            dataset_paths = {item["path"] for item in summary["datasets"]}
            self.assertIn("/Data/B_NEC", dataset_paths)
            self.assertIn("/Data/UTC_TIME", dataset_paths)

            candidates = summary["candidates"]
            self.assertEqual(candidates["time"][0]["path"], "/Data/UTC_TIME")
            self.assertEqual(candidates["magnetic_vector"][0]["path"], "/Data/B_NEC")
            self.assertEqual(candidates["magnetic_scalar"][0]["path"], "/Data/F")
            self.assertEqual(candidates["latitude"][0]["path"], "/Data/Latitude")
            self.assertEqual(candidates["longitude"][0]["path"], "/Data/Longitude")
            self.assertEqual(candidates["altitude"][0]["path"], "/Data/Altitude")
            self.assertIn("/Data/FLAG_MT", {item["path"] for item in candidates["quality_flag"]})
            self.assertEqual(candidates["quality_flag"][0]["path"], "/Data/Quality_Flag")

            b_summary = next(item for item in summary["datasets"] if item["path"] == "/Data/B_NEC")
            self.assertEqual(b_summary["attrs"]["units"]["value"], "nT")
            self.assertEqual(b_summary["attrs"]["units"]["confidence"], "confirmed")
            self.assertEqual(b_summary["preview"]["head_count"], 3)
            self.assertIn("finite_count", b_summary["sample_stats"])


if __name__ == "__main__":
    unittest.main()
