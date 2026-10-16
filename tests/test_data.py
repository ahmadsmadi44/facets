"""Exercise multirow FMA headers, genre ancestry, ID joins, and fallback."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
import pandas as pd

from src.data import build, rock_features, synthetic_features


class DataTests(unittest.TestCase):
    def test_fma_filters_descendants_and_joins_by_id(self):
        tracks = pd.DataFrame(
            [["[42]", "Rock", "First", "A", "training"],
             ["[42, 99]", np.nan, "Descendant", "B", "test"],
             ["[10]", "Pop", "Excluded", "C", "validation"]],
            index=pd.Index([1, 2, 3], name="track_id"),
            columns=pd.MultiIndex.from_tuples([
                ("track", "genres_all"), ("track", "genre_top"),
                ("track", "title"), ("artist", "name"), ("set", "split")]),
        )
        features = pd.DataFrame(
            [30.0, 20.0, 10.0], index=pd.Index([3, 2, 1], name="track_id"),
            columns=pd.MultiIndex.from_tuples([("mfcc", "mean", "01")]),
        )
        genres = pd.DataFrame({"title": ["Rock", "Pop"]}, index=[42, 10])
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "fixture.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                for name, frame in [("tracks", tracks), ("features", features), ("genres", genres)]:
                    bundle.writestr(f"fma_metadata/{name}.csv", frame.to_csv())
            result = rock_features(archive)
        self.assertEqual(result.index.tolist(), [1, 2])
        self.assertEqual(result["mfcc__mean__01"].tolist(), [10, 20])
        self.assertEqual(result.loc[2, "title"], "Descendant")
        self.assertEqual(result.loc[2, "split"], "test")

    def test_blocked_download_generates_identified_reproducible_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("src.data.download", side_effect=RuntimeError("HTTP 403")):
                result = build(directory)
            saved = pd.read_csv(Path(directory) / "rock_features.csv", index_col=0)
            provenance = json.loads((Path(directory) / "provenance.json").read_text())
        self.assertEqual(len(saved), 1000)
        self.assertEqual(set(saved.source), {"synthetic"})
        self.assertEqual(provenance["source"], "synthetic")
        self.assertIn("403", provenance["fallback_reason"])
        self.assertTrue(np.isfinite(saved.select_dtypes("number")).all().all())
        pd.testing.assert_frame_equal(result, synthetic_features())


if __name__ == "__main__":
    unittest.main()
