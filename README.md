# Rock song recommender

Aspect-based Rock recommendations from FMA precomputed audio features, with
session-local Rocchio feedback, a Streamlit app, and an offline alignment benchmark.
Python 3.10+; no audio download or librosa installation is needed.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m src.data
python -m src.embeddings --components 8
python -m src.evaluate
python -m streamlit run app.py
```

Open the local URL printed by Streamlit. Choose optional reference songs, toggle
aspects to like or dislike, and inspect titles, artists, scores, and per-aspect
contributions. Like means match the seed in that aspect; dislike means avoid its
sound in that aspect. Conflicting toggles display a validation message. Song
feedback updates recommendations immediately and excludes seeds and voted tracks.
Review previous votes to replace them, or clear all feedback. Votes persist across
aspect changes within the browser session and are not stored on disk. The app
fits and caches embeddings from the current CSV, so it also runs without a saved
model. Set `SONG_FEATURES` to use a different compatible CSV.

For an explicitly synthetic offline demonstration:

```powershell
python -m src.data --synthetic
python -m src.evaluate
python -m streamlit run app.py --server.headless=true
```

Synthetic mode overwrites the local feature table and provenance. It invents
1,000 tracks and independent feature distributions (seed 42), not measured audio
or real songs. The app and metrics identify this source. Rebuild from FMA to
reproduce the committed results. Evaluation requires explicit `training` and
`test` splits, at least two usable aspects, and at least k test tracks.

## Results

The committed [metrics](results/metrics.json) and
[four example queries](results/example_queries.md) use **real FMA features**:
32,923 Rock/descendant tracks, 25,819 training references, 3,414 held-out test
candidates, 40 simulated users, k=10, random seed 42. Validation rows are unused.
The metrics include the input SHA-256 for reproducibility.

| Metric (macro mean over simulated users) | Aspect recommender | Generic cosine |
| --- | ---: | ---: |
| Aspect consistency | 0.6982 | 0.4996 |
| Precision@10 | 0.9925 | 0.2025 |
| NDCG@10 | 0.9938 | 0.1991 |
| Negative-aspect avoidance rate | 0.9900 | 0.1000 |

Each simulated user has a randomly sampled training reference and known
preferences: match one aspect, avoid another. Both methods rank exactly the same
test-only catalog. All imputation, scaling, and PCA fit training rows only. The
aspect method uses independent PCA spaces; the generic baseline uses cosine
similarity to the same seed over all standardized audio feature columns and
ignores aspect preferences. No feedback is supplied in this benchmark.

The scoring oracle uses standardized **original** feature families, before PCA.
For each candidate, utility is `(cosine_liked - cosine_disliked) / 2`.
Aspect consistency averages `(utility + 1) / 2` across recommendations. Binary
relevance is membership in the top utility quintile of the test catalog, ties
included. Precision is the relevant fraction of the top k; NDCG uses binary gains,
log2 rank discounts, and the best possible ranking in that same catalog. Avoidance
is the fraction with disliked-aspect cosine <= 0. All metrics lie in [0,1].

**These high scores demonstrate feature alignment under a deliberately compatible
simulator, not listener satisfaction.** The oracle shares feature families with
the model, and the baseline cannot see the positive/negative aspect request.
Top-quintile relevance is generous and synthetic preferences are simple. There
are no human relevance labels, listening trials, statistical significance claims,
or held-out real-user histories. Differences in dimensions and aspect weighting
also affect this comparison. More complex preferences, artist-disjoint splits,
independent labels, stronger baselines, and online evaluation remain future work.

```powershell
python -m src.evaluate --features data/rock_features.csv --users 40 --k 10 --seed 42 --output results
python -m pytest -q
```

Verification on 2026-10-16: all 23 tests passed, including known-ranking metric
checks, deterministic evaluation, test-only candidate checks, and Streamlit
interaction tests. The actual FMA catalog rendered 10 recommendations in
Streamlit's AppTest. A headless server returned `ok` from `/_stcore/health`, then
was terminated and its process exit and closed port were verified.

## Data and attribution

`python -m src.data` caches `fma_metadata.zip` under gitignored `data/`, verifies
its upstream SHA-1, and writes `rock_features.csv` plus `provenance.json`. It tries
the Swiss, Pisa, then Facebook mirrors with shared 600-second and 500 MB download
budgets; stalled reads may add up to 20 seconds. Verified archives work offline.
Download failures trigger an announced synthetic fallback with the reason in
provenance; parsing errors fail visibly. Check `source` before interpreting results.

FMA multirow CSV headers are parsed explicitly. Rock and descendants are selected
using `genres_all` or the top genre, then metadata and chunked features are joined
by track ID. Columns are `track_id`, `title`, `artist`, `genre`, `split`, `source`,
followed by `family__statistic__dimension` numeric audio summaries. No audio is
acquired or played. Missing titles/artists remain missing rather than invented.

Audio features come from **FMA, a CC-licensed dataset**. Attribution: Michael
Defferrard, Kirell Benzi, Pierre Vandergheynst, and Xavier Bresson,
*FMA: A Dataset for Music Analysis*, ISMIR 2017
([paper](https://arxiv.org/abs/1612.01840),
[dataset and licenses](https://github.com/mdeff/fma#acknowledgments-and-licenses)).
Metadata/features are [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/);
this filtered feature table is a modification. Recordings have individual
artist-selected licenses; metadata licensing is not a blanket audio license.

## Model and limitations

| Aspect | Feature families |
| --- | --- |
| Rhythm/beat | tempogram, fourier_tempogram, onset_strength, beat (optional) |
| Tempo | tempo, bpm (optional) |
| Melody | chroma_stft, chroma_cqt, chroma_cens |
| Timbre | mfcc, spectral_contrast |
| Energy | rms/rmse, zcr/zero_crossing_rate |
| Mood | tonnetz, spectral_centroid, spectral_rolloff |

**Tempo/beat caveat:** standard FMA features have no explicit beat or BPM
measurements. Rhythm and tempo are unavailable and disabled in the app unless
measured additional feature columns are supplied. Timbre does not substitute for
BPM. Mood is a harmony/brightness proxy, not an emotional label; chroma summaries
are not melody transcriptions, and energy features are imperfect perceptual proxies.

Independent aspect models use training-median imputation, standard scaling, and
up to eight PCA components. Infinite values count as missing; wholly missing
columns and constant groups are excluded. Saved models live in gitignored
`models/aspect_embeddings.joblib`; load only trusted joblib files. Outside the
benchmark, `AspectEmbeddings.fit` uses all rows if no split is supplied.

For each selected aspect, unit embeddings define the query:
`q = sign * alpha * mean(seeds) + beta * mean(liked songs) - gamma * mean(disliked songs)`.
Sign is +1 for liked aspects and -1 for disliked aspects. The score averages
`vector @ q` across selected aspects only; defaults are alpha=1, beta=0.75,
gamma=0.25. Negative feedback on a seed removes its positive reference. Song
dislikes always repel, including within aspects marked disliked. Scores are
relative rankings, not probabilities or calibrated musical quality.

Without seeds, toggles alone cannot identify a desired sound: the initial prior
uses signed `norm / (1 + norm)` (distance from the training mean). It does not
mean high/low energy, absolute BPM, or a desired emotional value. Supply a seed
for a specific reference. Feedback then adds Rocchio terms. This content-only
prototype has no collaborative filtering, semantic lyrics, diversity constraint,
audio playback, or guarantees of subjective similarity.
