# Rock song recommender

Aspect-based rock-song recommendations from precomputed audio features.
Python 3.10+; no audio download or librosa installation is needed.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m src.data
```

The command caches `fma_metadata.zip` under gitignored `data/`, verifies the
[upstream SHA-1](https://github.com/mdeff/fma#usage), and writes
`data/rock_features.csv` plus `data/provenance.json`. It tries the Pisa mirror
then Facebook, with a shared 600-second download budget (a stalled read may add
up to 20 seconds). Verified cached archives work offline. Partial downloads
are removed. Parsing errors fail visibly instead of silently replacing real data.

FMA CSVs use multirow headers. The pipeline finds Rock in `genres.csv`, filters
`tracks.csv` by its inclusive `genres_all` ancestry or top genre Rock, and joins
the precomputed librosa `features.csv` by track ID. Features stream in chunks.
Output columns: `track_id`, `title`, `artist`, `genre`, `split`, `source`, then
numeric `family__statistic__dimension` columns. Missing values remain missing;
imputation, scaling and PCA are fitted on training rows only by `src.embeddings`.
The source split is retained for evaluation.

Data attribution: Michaël Defferrard, Kirell Benzi, Pierre Vandergheynst, and
Xavier Bresson, *FMA: A Dataset for Music Analysis*, ISMIR 2017
([paper](https://arxiv.org/abs/1612.01840),
[dataset and license statement](https://github.com/mdeff/fma#acknowledgments-and-licenses)).
FMA metadata is [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
This filtered table is a modification of the original metadata/features.
Audio has separate artist-selected licenses and is not acquired here.

When downloads are blocked, fail checksum validation, or exceed the budget,
the command clearly announces a **synthetic fallback** and records the reason.
`python -m src.data --synthetic` also supports an explicit offline demo.
Synthetic output contains 1,000 invented Rock-labeled tracks, seed 42, and 74
numeric mean/std summaries: 20 MFCCs, 12 chroma bins, spectral centroid,
bandwidth, rolloff, RMS, and zero-crossing rate. Values are independent normal
draws (positive standard deviations and bounded chroma/RMS/ZCR means).
They are librosa-style fields, **not measured audio or real songs**, and cannot
establish recommendation quality. The synthetic features are not schema-identical
to FMA's complete feature set. Inspect `source` and provenance before training.

Initial run, 2026-10-16: **synthetic fallback**; Pisa DNS failed and Facebook
returned HTTP 403. No FMA data was acquired in that run.

Fit and save the per-aspect models locally:

```powershell
python -m src.embeddings --components 8
python -m pytest -q
```

`models/aspect_embeddings.joblib` stores the feature schema, training medians,
standard scaler and independent PCA for every available aspect. `models/` is
gitignored. Only load trusted model files. Infinite values are treated as missing;
columns missing throughout training and constant groups are excluded. When no
`split` column exists, all input rows train the model; callers can instead pass
an explicit boolean `training_mask` to `fit`.

Aspect mappings (original FMA MultiIndex and flattened columns both work):

| Aspect | Feature families |
| --- | --- |
| `rhythm` (beat/rhythm) | tempogram, fourier_tempogram, onset_strength, beat |
| `tempo` | tempo, bpm |
| `melody` | chroma_stft, chroma_cqt, chroma_cens |
| `timbre` | mfcc, spectral_contrast |
| `energy` | rms/rmse, zcr/zero_crossing_rate |
| `mood` | tonnetz, spectral_centroid, spectral_rolloff |

Mood is a harmonic/brightness proxy, not an emotional classification. Standard
FMA features lack explicit beat and tempo measurements; supplying measured
additional feature columns enables those aspects. Missing aspects appear in
`unavailable_aspects` and selecting them raises an error. No tempo is inferred
from unrelated timbral features.

```python
import pandas as pd
from src.embeddings import AspectEmbeddings
from src.recommender import AspectRecommender

tracks = pd.read_csv("data/rock_features.csv", index_col=0)
model = AspectEmbeddings.load()
recommender = AspectRecommender(
    model.transform(tracks),
    liked_aspects=["melody"],
    disliked_aspects=["timbre"],
    seed_songs=[tracks.index[0]],  # optional
)
ranked = recommender.recommend(limit=10)
print(tracks[["title", "artist"]].join(ranked, how="inner").sort_values("score", ascending=False))
recommender.update_feedback(ranked.index[0], liked=True)
updated = recommender.recommend(limit=10)
```

For each selected aspect, unit-length embedding vectors define the Rocchio
query `q = sign * alpha * mean(seeds) + beta * mean(liked songs)
- gamma * mean(disliked songs)`, where sign is +1 for a liked aspect and -1
for a disliked aspect. The final score averages `vector @ q` over selected
aspects only; returned aspect columns expose the individual contributions.
Defaults are alpha=1, beta=0.75, gamma=0.25. Feedback is session-local, repeated
votes replace earlier votes, and negative seed feedback removes that seed from
the seed centroid. Song dislikes always repel within selected aspects.
Seeds and voted songs are excluded from results by default.

Without seeds, aspect likes/dislikes alone cannot identify a desired sound.
The initial ranking uses signed `norm / (1 + norm)` as a distinctiveness prior
(distance from the training mean); song feedback adds Rocchio terms. This
prior describes feature prominence, not absolute energy, BPM, emotion, or
recommendation quality. Use seeds for a specific musical reference.
