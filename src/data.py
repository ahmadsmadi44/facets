"""Cache FMA metadata and build Rock features, with an explicit synthetic fallback."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import time
import zipfile

import numpy as np
import pandas as pd
import requests


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
URLS = (
    "https://os.unipi.it/mirror/fma/fma_metadata.zip",
    "https://dl.fbaipublicfiles.com/fma/fma_metadata.zip",
)
SHA1 = "f0df49ffe5f2a6008d7dc83c6915b31835dfe733"


def checksum(path):
    digest = hashlib.sha1()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(data_dir, timeout_seconds=600):
    """Try both mirrors within a shared budget; never cache a partial archive."""
    archive = data_dir / "fma_metadata.zip"
    if archive.exists() and checksum(archive) == SHA1:
        return archive, "cached FMA archive (verified upstream SHA-1)"
    deadline = time.monotonic() + timeout_seconds
    errors = []
    partial = archive.with_suffix(".zip.part")
    for url in URLS:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            errors.append("shared download budget exhausted")
            break
        print(f"Downloading {url}", flush=True)
        try:
            with requests.get(url, stream=True, timeout=(min(10, remaining), min(20, remaining))) as response:
                response.raise_for_status()
                with partial.open("wb") as stream:
                    for block in response.iter_content(256 * 1024):
                        if time.monotonic() >= deadline:
                            raise TimeoutError("shared download budget exhausted")
                        stream.write(block)
            if checksum(partial) != SHA1:
                raise ValueError("archive does not match upstream SHA-1")
            partial.replace(archive)
            return archive, url
        except (requests.RequestException, TimeoutError, ValueError) as exc:
            errors.append(f"{url}: {exc}")
        finally:
            partial.unlink(missing_ok=True)
    raise RuntimeError("; ".join(errors))


def rock_features(archive):
    """Include Rock and its descendants via genres_all, joining by track ID."""
    with zipfile.ZipFile(archive) as bundle:
        with bundle.open("fma_metadata/genres.csv") as stream:
            genres = pd.read_csv(stream, index_col=0)
        rock_ids = set(genres.index[genres["title"].eq("Rock")])
        if not rock_ids:
            raise ValueError("FMA genre taxonomy has no Rock entry")
        with bundle.open("fma_metadata/tracks.csv") as stream:
            tracks = pd.read_csv(stream, header=[0, 1], index_col=0, low_memory=False)
        mask = tracks[("track", "genres_all")].map(
            lambda value: bool(rock_ids.intersection(ast.literal_eval(value)))
        ) | tracks[("track", "genre_top")].eq("Rock")
        selected = tracks.loc[mask]
        if selected.empty:
            raise ValueError("FMA contains no matching Rock tracks")
        metadata = pd.DataFrame({
            "title": selected[("track", "title")],
            "artist": selected[("artist", "name")],
            "genre": "Rock",
            "split": selected[("set", "split")],
            "source": "fma",
        })
        parts = []
        with bundle.open("fma_metadata/features.csv") as stream:
            for chunk in pd.read_csv(stream, header=[0, 1, 2], index_col=0, chunksize=5000):
                chunk = chunk.loc[chunk.index.isin(selected.index)].copy()
                chunk.columns = ["__".join(map(str, column)) for column in chunk.columns]
                parts.append(chunk)
        features = pd.concat(parts)
        result = metadata.join(features, how="inner").sort_index()
        if len(result) != len(metadata):
            raise ValueError("Some selected tracks have no precomputed features")
        if not result.index.is_unique:
            raise ValueError("Duplicate FMA track IDs")
        result.index.name = "track_id"
        return result


def synthetic_features(rows=1000, seed=42):
    """Invented independent distributions, not audio measurements or real songs."""
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(index=pd.Index(range(1, rows + 1), name="track_id"))
    frame["title"] = [f"Synthetic Rock {i:04d}" for i in frame.index]
    frame["artist"] = "Synthetic artist"
    frame["genre"] = "Rock"
    frame["split"] = rng.choice(["training", "validation", "test"], rows, p=[0.8, 0.1, 0.1])
    frame["source"] = "synthetic"
    # Mean/std summaries resemble librosa feature families; no librosa is run.
    for family, dimensions, location, scale in (
        ("mfcc", 20, 0, 30),
        ("chroma_stft", 12, 0.5, 0.15),
        ("spectral_centroid", 1, 2500, 700),
        ("spectral_bandwidth", 1, 2200, 500),
        ("spectral_rolloff", 1, 5000, 1200),
        ("rms", 1, 0.15, 0.04),
        ("zcr", 1, 0.1, 0.03),
    ):
        for dimension in range(dimensions):
            values = rng.normal(location, scale, rows)
            if family != "mfcc":
                values = np.maximum(values, 0)
            if family in {"chroma_stft", "rms", "zcr"}:
                values = np.minimum(values, 1)
            frame[f"{family}__mean__{dimension:02d}"] = values
            frame[f"{family}__std__{dimension:02d}"] = np.abs(rng.normal(scale / 2, scale / 6, rows))
    return frame


def build(data_dir=DATA_DIR, timeout_seconds=600, synthetic=False):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    reason = "Explicit --synthetic option" if synthetic else None
    if not synthetic:
        try:
            archive, source_url = download(data_dir, timeout_seconds)
        except RuntimeError as exc:
            reason = str(exc)
    if reason is not None:
        print(f"USING SYNTHETIC DATA: {reason}", flush=True)
        frame = synthetic_features()
        provenance = {"source": "synthetic", "seed": 42, "fallback_reason": reason}
    else:
        frame = rock_features(archive)
        provenance = {"source": "fma", "download_source": source_url, "archive_sha1": SHA1,
                      "license": "CC BY 4.0", "attribution": "Defferrard, Benzi, Vandergheynst, Bresson; FMA, ISMIR 2017"}
    output = data_dir / "rock_features.csv"
    partial = output.with_suffix(".csv.part")
    frame.to_csv(partial)
    partial.replace(output)
    provenance.update({"rows": len(frame), "feature_columns": len(frame.columns) - 5,
                       "output": output.name, "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest()})
    (data_dir / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(frame):,} rows to {output}; source={provenance['source']}")
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    parser.add_argument("--synthetic", action="store_true", help="Explicitly generate demonstration data offline")
    args = parser.parse_args()
    if not 0 < args.timeout_seconds <= 600:
        parser.error("--timeout-seconds must be between 0 and 600")
    build(args.data_dir, args.timeout_seconds, args.synthetic)


if __name__ == "__main__":
    main()
