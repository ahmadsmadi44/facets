# Two-minute demo

Before recording: install requirements, run `python -m src.data`, then
`python -m src.evaluate`. Confirm `data/provenance.json` says `fma` to match the
committed results. Start `python -m streamlit run app.py`. Keep
`results/example_queries.md` and `results/metrics.json` open beside the browser.
If using synthetic data, say so and do not quote the FMA results as that run.

**0:00-0:20 ? Problem and source**

?This prototype recommends Rock tracks by the parts of a reference song you
want to keep or avoid. These are FMA precomputed audio features with track titles
and artists. Metadata/features are CC BY 4.0; recordings have individual licenses.
This demo ranks songs without hosting or playing audio.? Point to the source banner.

**0:20-0:45 ? Ask a specific question**

Open example query 1: choose reference ID 12227, Good Riddance by Phil Reavis.
Turn off the default Melody like, turn on Like Timbre and Dislike Mood.
?I want a similar timbre but a different harmony/brightness profile. Mood here
is a feature proxy, not a claim about emotion.? Show the results table and scores.
?The committed example compares this request against generic cosine on test
tracks only; the app searches the full catalog, so its results can differ.?

**0:45-1:10 ? Give feedback**

Click Like song on one result and Dislike song on another. Show the new results.
?Votes move the query toward liked songs and away from disliked songs, within
selected aspects. Seen tracks are excluded.? Open the vote review, replace a
vote, then clear feedback. ?These votes belong to this browser session.?

**1:10-1:35 ? Show evaluation**

Open metrics.json and the four example queries.
?Across 40 simulated preferences and 3,414 held-out FMA tracks, precision at ten
was 0.9925 for aspect selection and 0.2025 for generic cosine. Negative-aspect
avoidance was 99 percent versus 10 percent. Both methods see identical candidates;
preprocessing fits training rows only.? Point to the protocol and input hash.

**1:35-2:00 ? State the limits**

?These are feature-alignment diagnostics. The simulator shares features with
the model and defines relevance as its top quintile, which favors this method;
we have not shown human listening quality. Standard FMA has no measured tempo
or beat features, so those controls are disabled. With no reference, aspect
toggles rank distinctiveness, not absolute energy or BPM. Next steps are
independent listener labels, stronger baselines, and measured rhythm features.?
