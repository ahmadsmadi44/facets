# Rock song recommender

Data preparation scaffold for a future content-based rock-song recommender.
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
imputation and scaling belong in a future training pipeline fitted on training
data only. The source split is retained for evaluation.

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

Next: fit training-only imputation/scaling and a nearest-neighbor baseline.
Run data-pipeline checks with `python -m unittest discover -s tests`.
