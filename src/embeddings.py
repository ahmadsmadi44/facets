"""Training-only, independently standardised PCA spaces for audio aspects."""

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler


MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
# Match feature families exactly, never metadata or unrelated numeric columns.
# FMA's standard features.csv has no beat/tempo measurements. These two
# aspects become available only when callers supply measured extra features.
ASPECT_GROUPS = {
    "rhythm": ("tempogram", "fourier_tempogram", "onset_strength", "beat"),
    "tempo": ("tempo", "bpm"),
    "melody": ("chroma_stft", "chroma_cqt", "chroma_cens"),
    "timbre": ("mfcc", "spectral_contrast"),
    "energy": ("rms", "rmse", "zcr", "zero_crossing_rate"),
    "mood": ("tonnetz", "spectral_centroid", "spectral_rolloff"),
}


def aspect_columns(frame):
    """Accept flattened data.py columns or original FMA MultiIndex columns."""
    return {
        aspect: [column for column in frame.columns
                 if (str(column[0]) if isinstance(column, tuple)
                     else str(column).split("__")[0]) in families]
        for aspect, families in ASPECT_GROUPS.items()
    }


class AspectEmbeddings:
    """Fit on training rows; impute, scale and reduce each aspect independently.

    Mood uses harmonic/brightness proxies, not measured emotional labels.
    Missing families are reported in unavailable_aspects rather than fabricated.
    """

    def __init__(self, n_components=8):
        if not isinstance(n_components, int) or n_components < 1:
            raise ValueError("n_components must be a positive integer")
        self.n_components = n_components
        self.models = {}

    @property
    def unavailable_aspects(self):
        return sorted(set(ASPECT_GROUPS) - self.models.keys())

    def fit(self, frame, training_mask=None):
        if not frame.index.is_unique or not frame.columns.is_unique:
            raise ValueError("Track IDs and feature columns must be unique")
        if training_mask is None:
            training_mask = frame["split"].eq("training") if "split" in frame else np.ones(len(frame), dtype=bool)
        training = frame.loc[training_mask]
        if len(training) < 2:
            raise ValueError("At least two training tracks are required")
        self.models = {}
        for aspect, columns in aspect_columns(frame).items():
            if not columns:
                continue
            values = training[columns].astype(float).replace([np.inf, -np.inf], np.nan)
            columns = values.columns[values.notna().any()].tolist()
            if not columns:
                continue
            imputer = SimpleImputer(strategy="median")
            scaler = StandardScaler()
            scaled = scaler.fit_transform(imputer.fit_transform(values[columns]))
            # Constant groups carry no similarity information.
            if not np.any(scaler.var_ > 0):
                continue
            pca = PCA(n_components=min(self.n_components, len(training) - 1, len(columns)), svd_solver="full")
            pca.fit(scaled)
            self.models[aspect] = (columns, imputer, scaler, pca)
        if not self.models:
            raise ValueError("No usable audio aspect features")
        return self

    def transform(self, frame):
        if not self.models:
            raise ValueError("Fit embeddings before transforming")
        if not frame.index.is_unique:
            raise ValueError("Track IDs must be unique")
        result = {}
        for aspect, (columns, imputer, scaler, pca) in self.models.items():
            missing = set(columns) - set(frame.columns)
            if missing:
                raise ValueError(f"Missing features for {aspect}: {missing}")
            values = frame[columns].astype(float).replace([np.inf, -np.inf], np.nan)
            result[aspect] = pd.DataFrame(
                pca.transform(scaler.transform(imputer.transform(values))), index=frame.index)
        return result

    def save(self, directory=MODELS_DIR):
        if not self.models:
            raise ValueError("Fit embeddings before saving")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "aspect_embeddings.joblib"
        joblib.dump(self, path)
        return path

    @classmethod
    def load(cls, directory=MODELS_DIR):
        """Load a trusted local model file (joblib uses pickle)."""
        model = joblib.load(Path(directory) / "aspect_embeddings.joblib")
        if not isinstance(model, cls):
            raise ValueError("Invalid aspect embedding model")
        return model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=Path("data/rock_features.csv"))
    parser.add_argument("--models-dir", type=Path, default=MODELS_DIR)
    parser.add_argument("--components", type=int, default=8)
    args = parser.parse_args()
    model = AspectEmbeddings(args.components).fit(pd.read_csv(args.features, index_col=0))
    print(f"Saved {model.save(args.models_dir)}; unavailable: {model.unavailable_aspects}")


if __name__ == "__main__":
    main()
