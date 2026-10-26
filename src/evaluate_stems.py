"""Do the stem embeddings capture different things? A check with labels the audio never sees.

- Vocal identity: songs by the same lead artist share a voice. If the vocals stem captures the
  voice, its nearest neighbours should be same-artist more often than whole-mix neighbours.
- Beat identity: songs sharing a producer (Genius credits) share drums and 808s. If the drums/bass
  stems capture the beat, their neighbours should share a producer more often than mix neighbours.

Reports precision@10 per stem, with a random baseline. Writes results/stem_eval.json.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.export_web import STEMS, load_embeddings, primary_artist
from src.knowledge import load_records

ROOT = Path(__file__).resolve().parents[1]


def precision_at_k(emb, labels_match, k=10):
    """Mean fraction of each query's k nearest neighbours that match it (queries with >= 1 possible match)."""
    sims = emb @ emb.T
    np.fill_diagonal(sims, -np.inf)
    top = np.argsort(-sims, axis=1)[:, :k]
    scores = [labels_match(q, top[q]).mean() for q in range(len(emb)) if labels_match(q, None) > 0]
    return float(np.mean(scores)), len(scores)


def precision_other(emb, labels_match, artists, k=10):
    sims = emb @ emb.T
    sims[artists[:, None] == artists[None, :]] = -np.inf  # also removes the diagonal
    top = np.argsort(-sims, axis=1)[:, :k]
    scores = [labels_match(q, top[q]).mean() for q in range(len(emb)) if labels_match(q, None) > 0]
    return float(np.mean(scores)), len(scores)


def main(data_dir=ROOT / "data"):
    catalog = pd.read_csv(data_dir / "catalog.csv", index_col=0)
    ids, emb, _ = load_embeddings(data_dir, catalog.index)
    emb = emb - emb.mean(0)  # same centring the app gets from PCA
    emb /= np.linalg.norm(emb, axis=2, keepdims=True)
    records = load_records(data_dir / "genius")
    artists = np.array([primary_artist(catalog.loc[i, "artist"]) for i in ids])
    producers = [set(p.lower() for p in records.get(int(i), {}).get("producers", [])) for i in ids]
    # Big hitmakers (e.g. a producer on 60 songs) would dominate; cap label frequency for a fair test.
    counts = pd.Series([p for ps in producers for p in ps]).value_counts()
    producers = [{p for p in ps if counts[p] <= 40} for ps in producers]

    def same_artist(q, nbrs):
        return (artists == artists[q]).sum() - 1 if nbrs is None else artists[nbrs] == artists[q]

    def same_producer(q, nbrs):
        if nbrs is None:
            return sum(bool(producers[q] & p) for p in producers) - 1 if producers[q] else 0
        return np.array([bool(producers[q] & producers[j]) for j in nbrs])

    def producer_other_artist(q, nbrs):
        """Shared producer among songs by a *different* artist: beat similarity without the voice confound."""
        if nbrs is None:
            return sum(bool(producers[q] & p) and artists[j] != artists[q] for j, p in enumerate(producers))                 if producers[q] else 0
        return np.array([bool(producers[q] & producers[j]) for j in nbrs])

    rng = np.random.default_rng(0)
    results = {"tracks": len(ids)}
    for name, fn in (("same_lead_artist", same_artist), ("shared_producer", same_producer),
                     ("shared_producer_other_artist", producer_other_artist)):
        row = {}
        for s, stem in enumerate(STEMS):
            e = emb[:, s].copy()
            if name == "shared_producer_other_artist":  # rank only among other artists' songs
                row[stem], n = precision_other(e, fn, artists)
                continue
            row[stem], n = precision_at_k(e, fn)
        random = rng.normal(size=(len(ids), 64))
        random /= np.linalg.norm(random, axis=1, keepdims=True)
        row["random"], _ = (precision_other(random, fn, artists) if name == "shared_producer_other_artist"
                            else precision_at_k(random, fn))
        row["queries"] = n
        results[name] = row
    out = ROOT / "results" / "stem_eval.json"
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
