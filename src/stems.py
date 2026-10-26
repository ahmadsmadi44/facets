"""Separate each 30 s preview into stems and embed every stem with a music CLAP model (GPU).

Demucs (htdemucs) splits the clip into drums, bass, other (melody/harmony/samples) and vocals.
CLAP (laion/larger_clap_music_and_speech) embeds the full mix and each stem into one 512-d space that is
shared with text, so "the drums" compares isolated drums and "angelic vocals" can be matched
against vocal stems. Stems are never written to disk; only embeddings and stem energies are cached
per track in gitignored data/stem_emb/.
"""

import argparse
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torchaudio.functional as AF

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CLAP_NAME = "laion/larger_clap_music_and_speech"  # larger_clap_music ships a collapsed text tower
PARTS = ("mix", "drums", "bass", "other", "vocals")


def load(path, sr=44100):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-t", "30", "-f", "f32le", "-ac", "2",
                          "-ar", str(sr), "-"], capture_output=True, check=True).stdout
    return torch.from_numpy(np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.copy())


class StemEmbedder:
    def __init__(self, device=None):
        from demucs.pretrained import get_model
        from transformers import ClapModel, ClapProcessor
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.demucs = get_model("htdemucs").to(self.device).eval()
        self.clap = ClapModel.from_pretrained(CLAP_NAME).to(self.device).eval()
        self.processor = ClapProcessor.from_pretrained(CLAP_NAME)

    @torch.no_grad()
    def separate(self, wav):
        from demucs.apply import apply_model
        ref = wav.mean(0)
        mean, std = ref.mean(), ref.std() + 1e-8
        sources = apply_model(self.demucs, ((wav - mean) / std)[None].to(self.device), split=True,
                              overlap=0.1, progress=False)[0]
        sources = sources * std + mean
        return dict(zip(self.demucs.sources, sources.cpu()))

    @torch.no_grad()
    def embed_audio(self, clips):
        """clips: list of mono 48 kHz arrays. Each clip is cut into 10 s windows and averaged."""
        windows, owners = [], []
        for n, clip in enumerate(clips):
            for start in range(0, max(1, len(clip) - 48000 * 5), 48000 * 10):
                windows.append(clip[start:start + 48000 * 10])
                owners.append(n)
        # transformers 5.x CLAP is broken (collapsed text/audio embeddings); we pin 4.46 where the kwarg is audios.
        inputs = self.processor(audios=windows, sampling_rate=48000, return_tensors="pt").to(self.device)
        features = self.clap.get_audio_features(**inputs)
        features = getattr(features, "pooler_output", features)
        features = torch.nn.functional.normalize(features, dim=-1).cpu().numpy()
        owners = np.array(owners)
        out = np.stack([features[owners == n].mean(0) for n in range(len(clips))])
        return out / np.linalg.norm(out, axis=1, keepdims=True)

    @torch.no_grad()
    def embed_text(self, texts):
        inputs = self.processor(text=list(texts), return_tensors="pt", padding=True).to(self.device)
        features = self.clap.get_text_features(**inputs)
        features = getattr(features, "pooler_output", features)
        return torch.nn.functional.normalize(features, dim=-1).cpu().numpy()

    def process(self, path):
        wav = load(path)
        stems = self.separate(wav)
        mono = {"mix": wav.mean(0), **{k: v.mean(0) for k, v in stems.items()}}
        clips = [AF.resample(mono[p], 44100, 48000).numpy() for p in PARTS]
        embeddings = self.embed_audio(clips)
        mix_energy = float((mono["mix"] ** 2).mean()) + 1e-12
        energy = np.array([float((mono[p] ** 2).mean()) / mix_energy for p in PARTS], dtype=np.float32)
        return embeddings.astype(np.float32), energy, self.bpm(mono)

    @staticmethod
    def bpm(mono):
        """Tempo from the isolated drum stem (falls back to the mix when the clip has no drums)."""
        import librosa
        drums = mono["drums"].numpy()
        source = drums if (drums ** 2).mean() > 0.05 * (mono["mix"].numpy() ** 2).mean() else mono["mix"].numpy()
        y = librosa.resample(source, orig_sr=44100, target_sr=22050)
        tempo, _ = librosa.beat.beat_track(y=y, sr=22050)
        return float(np.atleast_1d(tempo)[0])


def gpu_temp():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=10).stdout
        return int(out.split()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def cool_down(max_temp, resume_temp, rest):
    """Thermal governor: rest after every clip; above max_temp, wait until the GPU is back to resume_temp."""
    time.sleep(rest)
    temp = gpu_temp()
    if temp is None or temp < max_temp:
        return
    print(f"  GPU at {temp}C, pausing until {resume_temp}C", flush=True)
    while (temp := gpu_temp()) is not None and temp > resume_temp:
        time.sleep(5)


def build(data_dir=DATA_DIR, limit=None, max_temp=75, resume_temp=68, rest=1.5):
    data_dir = Path(data_dir)
    catalog = pd.read_csv(data_dir / "catalog.csv", index_col=0)
    folder = data_dir / "stem_emb"
    folder.mkdir(exist_ok=True)
    todo = [i for i in catalog.index if (data_dir / "previews" / f"{i}.m4a").exists()
            and not (folder / f"{i}.npz").exists()]
    # Artists added for the listener's taste (later lines of artists.txt) go first.
    from src.catalog import read_artists
    rank = {name: n for n, (name, _) in enumerate(read_artists())}
    first = lambda i: rank.get(catalog.loc[i, "seed_artist"], -1)
    todo = sorted(todo, key=lambda i: first(i) if first(i) >= 44 else 1000)[:limit]
    print(f"Embedding {len(todo)} clips", flush=True)
    embedder = StemEmbedder()
    for n, track_id in enumerate(todo, 1):
        try:
            embeddings, energy, bpm = embedder.process(data_dir / "previews" / f"{track_id}.m4a")
            np.savez(folder / f"{track_id}.npz", embeddings=embeddings, energy=energy, bpm=bpm)
        except Exception as exc:  # one bad clip must not stop the batch
            print(f"  {track_id}: skipped ({exc})", flush=True)
        if n % 25 == 0:
            print(f"{n}/{len(todo)}  GPU {gpu_temp()}C", flush=True)
        cool_down(max_temp, resume_temp, rest)
    print("done", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-temp", type=int, default=75, help="pause when the GPU reaches this (C)")
    parser.add_argument("--resume-temp", type=int, default=68, help="resume once it cools to this (C)")
    parser.add_argument("--rest", type=float, default=1.5, help="seconds to idle after every clip")
    args = parser.parse_args()
    build(args.data_dir, args.limit, args.max_temp, args.resume_temp, args.rest)


if __name__ == "__main__":
    main()
