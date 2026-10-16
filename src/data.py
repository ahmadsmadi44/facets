"""Synthetic stand-in catalog for tests and offline demos (not real audio).

Real data comes from `python -m src.catalog` then `python -m src.features`.
"""

import numpy as np
import pandas as pd

SIGNED = {"mfcc", "perc_mfcc", "vocal_mfcc", "tonnetz"}


def synthetic_features(rows=1000, seed=42):
    """Invented independent distributions with the real column layout; no audio is analysed."""
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(index=pd.Index(range(1, rows + 1), name="track_id"))
    frame["title"] = [f"Synthetic Track {i:04d}" for i in frame.index]
    frame["artist"] = "Synthetic artist"
    frame["genre"] = "Hip-Hop/Rap"
    frame["split"] = rng.choice(["training", "validation", "test"], rows, p=[0.8, 0.1, 0.1])
    frame["source"] = "synthetic"
    for family, dimensions, location, scale in (
        ("mfcc", 20, 0, 30), ("spectral_contrast", 7, 20, 5), ("chroma_stft", 12, 0.5, 0.15),
        ("tonnetz", 6, 0, 0.1), ("spectral_centroid", 1, 2500, 700), ("spectral_rolloff", 1, 5000, 1200),
        ("rms", 1, 0.15, 0.04), ("zcr", 1, 0.1, 0.03), ("perc_mfcc", 13, 0, 30),
        ("perc_contrast", 7, 20, 5), ("perc_rms", 1, 0.1, 0.03), ("perc_low", 1, 0.3, 0.1),
        ("onset_strength", 1, 1.5, 0.5), ("tempogram", 24, 0.2, 0.08), ("tempo", 4, 100, 30),
        ("vocal_mfcc", 13, 0, 30), ("vocal_band", 2, 0.4, 0.1),
    ):
        for dimension in range(dimensions):
            values = rng.normal(location, scale, rows)
            if family not in SIGNED:
                values = np.maximum(values, 0)
            stat = "value" if family == "tempo" else "mean"
            frame[f"{family}__{stat}__{dimension:02d}"] = values
            if stat == "mean":
                frame[f"{family}__std__{dimension:02d}"] = np.abs(rng.normal(scale / 2, scale / 6, rows))
    return frame
