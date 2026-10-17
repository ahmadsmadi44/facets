# Hip hop / R&B aspect recommender

Pick a song you like (e.g. One Dance), say **what you like about it**, and get songs that match
that part. Two ways to say it: tap aspect buttons (beat, rapping, melody, drums, vibe, ...) or
describe it in your own words ("the dancehall beat with the rapping, but not the drums"; the app
shows what it understood). Every result plays its 30-second preview, with thumbs up/down to refine.

Python 3.10+, ffmpeg on PATH.

## Run

```powershell
python -m pip install -r requirements.txt
python -m src.catalog        # artists.txt -> data/catalog.csv + 30 s previews (~5 min)
python -m src.features       # librosa features for every clip (~20 min for 1,000 tracks)
python -m src.evaluate       # offline benchmark -> results/
python -m streamlit run app.py
```

Edit [artists.txt](artists.txt) to change who is in the catalog. The current build has 1,027 tracks
from 45 artists (Drake, Travis Scott, Kanye West, Kendrick Lamar, ...). Tests: `python -m pytest -q`.

## Data

Catalog metadata and 30-second previews come from the iTunes Search API (no key needed). Previews
are for personal, local use: audio and features live in gitignored `data/` and are never committed.
Spotify was not usable because it removed audio-features, audio-analysis and preview URLs for new apps.

## Aspects (all computed from the 30 s clip, `src/features.py`)

| Aspect | Features |
| --- | --- |
| Rhythm | tempogram (24 bins), onset strength |
| Tempo | BPM, onset density, beat regularity, pulse clarity |
| Drums | MFCC / spectral contrast / loudness / low-end (<150 Hz) share of the percussive component |
| Vocals | voice-band (200-4000 Hz) timbre of the harmonic mid channel, centre-vs-side energy |
| Melody | chroma |
| Timbre | MFCC, spectral contrast |
| Energy | RMS, zero-crossing rate |
| Mood | tonnetz, spectral centroid / rolloff (brightness and harmony proxy, not emotion) |

**Vocals is a proxy, not source separation**: kick and bass also sit in the centre channel.
A 30 s preview is one slice of a song, usually the hook. Each aspect gets its own median-imputed,
standardised PCA space (up to 8 components), fit on training rows only.

## Recommender

For each selected aspect with unit embeddings:
`q = sign * alpha * mean(seeds) + beta * mean(liked songs) - gamma * mean(disliked songs)`,
sign +1 for kept aspects and -1 for avoided ones. Score = mean of `vector @ q` over selected aspects.
Defaults alpha=1, beta=0.75, gamma=0.25. Repeat votes replace earlier votes; seeds and voted songs
are excluded. With no seed, toggles rank distinctiveness (distance from the average), not absolute
values like "high BPM", so pick a seed.

## Evaluation (read this honestly)

`python -m src.evaluate` simulates 40 users who each keep one aspect and avoid another relative to a
seed, with test-only candidates and training-only preprocessing. Latest run (1,027 tracks, 106 test):

| Metric | Aspect recommender | Generic cosine |
| --- | ---: | ---: |
| Precision@10 | 0.970 | 0.260 |
| NDCG@10 | 0.979 | 0.276 |
| Negative-aspect avoidance | 0.953 | 0.263 |

The oracle uses the same feature families as the model and the baseline cannot see the request, so
this shows feature alignment, not listener satisfaction. With only 106 test candidates it is also
coarse. Real validation is you listening: play the previews and judge.

## Not yet

Collaborative filtering, real vocal separation, artist-disjoint splits, a larger catalog
(`artists.txt` is the knob), and a hosted version (previews would stay streamed from Apple).
