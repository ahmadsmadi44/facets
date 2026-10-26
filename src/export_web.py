"""Export the catalog, stem embeddings, descriptors and Genius facts for the static web app.

Writes web/data/catalog.json, vectors.bin (int8, track x stem x 64) and descriptors.bin
(int8 z-scores x 16, track x descriptor). Genius bios are not exported; only credits and
sample relationships (facts) are.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from src.catalog import base_title
from src.descriptors import DESCRIPTORS, prompt, words
from src.knowledge import BACKING, BACKING_BIO, SAMPLE_WORDS, load_records, source_key

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT = ROOT / "web" / "data"
STEMS = ("mix", "drums", "bass", "other", "vocals")
DIMS = 64


def load_embeddings(data_dir, ids):
    found, emb, bpm = [], [], {}
    for i in ids:
        path = data_dir / "stem_emb" / f"{i}.npz"
        if path.exists():
            data = np.load(path)
            found.append(i)
            emb.append(data["embeddings"])
            if "bpm" in data:
                bpm[i] = float(data["bpm"])
    return found, np.stack(emb), bpm  # tracks x stems x 512


def text_embeddings(texts):
    from src.stems import StemEmbedder
    return StemEmbedder().embed_text(texts)


def primary_artist(artist):
    return artist.split(" & ")[0].split(",")[0].split(" feat")[0].strip().lower()


def display_title(full_title):
    title, _, artist = full_title.replace("\xa0", " ").rpartition(" by ")
    return f"{title} — {artist}" if title else full_title


def export(data_dir=DATA_DIR, out=OUT, text_vectors=None):
    data_dir, out = Path(data_dir), Path(out)
    catalog = pd.read_csv(data_dir / "catalog.csv", index_col=0)
    features = pd.read_csv(data_dir / "hiphop_features.csv", index_col=0, usecols=["track_id", "tempo__value__00"]) \
        if (data_dir / "hiphop_features.csv").exists() else pd.DataFrame(columns=["tempo__value__00"])
    ids, emb, stem_bpm = load_embeddings(data_dir, catalog.index)
    records = load_records(data_dir / "genius") if (data_dir / "genius").exists() else {}

    # Per-stem PCA to 64 dims, then int8. Centering removes what every hip hop clip shares.
    reduced = np.zeros((len(ids), len(STEMS), DIMS), dtype=np.float32)
    for s in range(len(STEMS)):
        reduced[:, s] = PCA(n_components=DIMS, random_state=0).fit_transform(emb[:, s])
    reduced /= np.linalg.norm(reduced, axis=2, keepdims=True) + 1e-9
    vectors = np.clip(np.round(reduced * 127 / np.abs(reduced).max()), -127, 127).astype(np.int8)

    labels = [d[0] for d in DESCRIPTORS]
    text = text_vectors if text_vectors is not None else text_embeddings([prompt(l, s) for l, s, _ in DESCRIPTORS])
    stem_of = [STEMS.index(s) for _, s, _ in DESCRIPTORS]
    raw = np.stack([emb[:, stem_of[k]] @ text[k] for k in range(len(DESCRIPTORS))], axis=1)
    z = (raw - raw.mean(0)) / (raw.std(0) + 1e-9)
    desc = np.clip(np.round(z * 16), -127, 127).astype(np.int8)

    tracks = []
    for n, i in enumerate(ids):
        row, rec = catalog.loc[i], records.get(int(i), {})
        rel = rec.get("relationships", {})
        sources = [t for name in ("samples", "interpolates") for t in rel.get(name, [])]
        bio = rec.get("bio", "")
        top = [k for k in np.argsort(-z[n]) if z[n, k] > 1.8][:3]
        bpm = stem_bpm.get(i, features.loc[i, "tempo__value__00"] if i in features.index else None)
        tracks.append({
            "id": int(i), "t": row["title"], "a": row["artist"], "a0": primary_artist(row["artist"]),
            "al": row.get("album") if isinstance(row.get("album"), str) else "",
            "art": str(row["artwork"]).replace("100x100bb", "300x300bb"),
            "p": row["preview_url"], "src": "dz" if i < 0 else "it",
            "bpm": round(float(bpm), 1) if bpm is not None and np.isfinite(bpm) else None,
            "key": base_title(str(row["title"])),
            "sk": [source_key(t) for t in sources], "sd": [display_title(t) for t in sources],
            "pr": sorted({p.lower() for p in rec.get("producers", [])}),
            "pd": rec.get("producers", [])[:4],
            "bk": int(any(BACKING.search(l) for l in rec.get("performances", {})) or bool(BACKING_BIO.search(bio))),
            "hs": int(bool(sources) or bool(SAMPLE_WORDS.search(bio))),
            "tg": [labels[k] for k in top],
            "gu": rec.get("url", ""),
        })
    meta = {"dims": DIMS, "stems": list(STEMS), "tracks": tracks,
            "descriptors": [{"label": l, "stem": s, "group": g, "words": words(l)} for l, s, g in DESCRIPTORS]}
    out.mkdir(parents=True, exist_ok=True)
    (out / "catalog.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "vectors.bin").write_bytes(vectors.tobytes())
    (out / "descriptors.bin").write_bytes(desc.tobytes())
    print(f"Exported {len(tracks)} tracks, {len(DESCRIPTORS)} descriptors to {out}")
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    export(args.data_dir, args.out)


if __name__ == "__main__":
    main()
