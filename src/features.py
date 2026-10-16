"""Extract per-aspect audio features from 30 s previews with librosa.

Columns are `family__statistic__dimension`, matching src.embeddings.ASPECT_GROUPS.
Drums use the percussive component; vocals are a stereo-centre / voice-band proxy
(not source separation); tempo comes from beat tracking on the clip.
"""

import argparse
import subprocess
from pathlib import Path

import librosa
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SR = 22050


def load_stereo(path):
    """Decode m4a/mp3 to float32 stereo via ffmpeg."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-t", "30", "-f", "f32le",
                          "-ac", "2", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.copy()


def summarize(name, matrix, out):
    """Mean and std over time for each row of a (dims, frames) matrix."""
    matrix = np.atleast_2d(matrix)
    for i, row in enumerate(matrix):
        out[f"{name}__mean__{i:02d}"] = float(np.mean(row))
        out[f"{name}__std__{i:02d}"] = float(np.std(row))


def extract(path):
    stereo = load_stereo(path)
    mid, side = stereo.mean(axis=0), (stereo[0] - stereo[1]) / 2
    harmonic, percussive = librosa.effects.hpss(mid)
    out = {}
    summarize("mfcc", librosa.feature.mfcc(y=mid, sr=SR, n_mfcc=20), out)
    summarize("spectral_contrast", librosa.feature.spectral_contrast(y=mid, sr=SR), out)
    summarize("chroma_stft", librosa.feature.chroma_stft(y=harmonic, sr=SR), out)
    summarize("tonnetz", librosa.feature.tonnetz(y=harmonic, sr=SR), out)
    summarize("spectral_centroid", librosa.feature.spectral_centroid(y=mid, sr=SR), out)
    summarize("spectral_rolloff", librosa.feature.spectral_rolloff(y=mid, sr=SR), out)
    summarize("rms", librosa.feature.rms(y=mid), out)
    summarize("zcr", librosa.feature.zero_crossing_rate(mid), out)
    # Drums: the percussive component's timbre, contrast, loudness and low-end (kick/808) share.
    summarize("perc_mfcc", librosa.feature.mfcc(y=percussive, sr=SR, n_mfcc=13), out)
    summarize("perc_contrast", librosa.feature.spectral_contrast(y=percussive, sr=SR), out)
    perc_spec = np.abs(librosa.stft(percussive)) ** 2
    freqs = librosa.fft_frequencies(sr=SR)
    out["perc_rms__mean__00"] = float(np.sqrt(perc_spec.sum(axis=0).mean()))
    out["perc_low__mean__00"] = float(perc_spec[freqs < 150].sum() / (perc_spec.sum() + 1e-9))
    # Rhythm: onset strength and a 24-bin summary of the tempogram.
    onset = librosa.onset.onset_strength(y=percussive + 0.5 * mid, sr=SR)
    summarize("onset_strength", onset, out)
    tempogram = librosa.feature.tempogram(onset_envelope=onset, sr=SR)
    bins = np.array_split(tempogram, 24, axis=0)
    for i, block in enumerate(bins):
        out[f"tempogram__mean__{i:02d}"] = float(block.mean())
    # Tempo: BPM, onset density, beat regularity and pulse clarity.
    tempo, beats = librosa.beat.beat_track(onset_envelope=onset, sr=SR)
    intervals = np.diff(librosa.frames_to_time(beats, sr=SR))
    out["tempo__value__00"] = float(np.atleast_1d(tempo)[0])
    out["tempo__value__01"] = float(len(librosa.onset.onset_detect(onset_envelope=onset, sr=SR)) / (len(mid) / SR))
    out["tempo__value__02"] = float(intervals.std() / intervals.mean()) if len(intervals) > 2 else 0.0
    out["tempo__value__03"] = float(np.max(tempogram.mean(axis=1)[1:]))
    # Vocals: voice-band (200-4000 Hz) timbre of the stereo-centre harmonic signal, plus
    # centre-vs-side energy. Rough proxy: lead vocals sit mid-channel, but so do kick and bass.
    voice_mel = librosa.feature.melspectrogram(y=librosa.effects.harmonic(mid), sr=SR, n_mels=40, fmin=200, fmax=4000)
    summarize("vocal_mfcc", librosa.feature.mfcc(S=librosa.power_to_db(voice_mel), n_mfcc=13), out)
    out["vocal_band__mean__00"] = float(voice_mel.sum() / (np.abs(librosa.stft(mid)) ** 2).sum())
    out["vocal_band__mean__01"] = float((mid ** 2).sum() / ((mid ** 2).sum() + (side ** 2).sum() + 1e-9))
    return out


def safe_extract(track_id, path):
    try:
        return track_id, extract(path)
    except Exception as exc:  # one bad clip must not stop the batch
        print(f"  {track_id}: skipped ({exc})", flush=True)
        return track_id, None


def build_features(data_dir=DATA_DIR, jobs=-1):
    data_dir = Path(data_dir)
    catalog = pd.read_csv(data_dir / "catalog.csv", index_col=0)
    paths = {i: data_dir / "previews" / f"{i}.m4a" for i in catalog.index}
    todo = [(i, p) for i, p in paths.items() if p.exists()]
    print(f"Extracting {len(todo)} clips", flush=True)
    results = Parallel(n_jobs=jobs, verbose=5)(delayed(safe_extract)(i, p) for i, p in todo)
    features = pd.DataFrame({i: row for i, row in results if row is not None}).T
    features.index.name = "track_id"
    keep = ["title", "artist", "genre", "split", "source", "preview_url", "artwork"]
    table = catalog[keep].join(features, how="inner")
    table.to_csv(data_dir / "hiphop_features.csv")
    print(f"Wrote {len(table)} tracks x {features.shape[1]} features")
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--jobs", type=int, default=-1)
    args = parser.parse_args()
    build_features(args.data_dir, args.jobs)


if __name__ == "__main__":
    main()
