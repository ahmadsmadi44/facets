# Two-minute demo

Setup: run the four commands in the README, then `python -m streamlit run app.py`.

- **0:00-0:20 Problem.** "Spotify-style recommendations steer by song. This steers by aspect: keep the
  drums, avoid the vocals." Show the catalog banner (1,027 tracks, 30 s previews).
- **0:20-0:50 Aspect control.** Pick Hotline Bling (Drake) as reference. Keep vocals + melody, avoid drums;
  play two results. Then keep drums + tempo, avoid vocals; show how the list changes.
- **0:50-1:15 Feedback.** Thumbs up one result, down another; list updates and excludes voted songs.
  Open vote review, flip a vote, clear.
- **1:15-1:40 Method.** Per-aspect PCA spaces, Rocchio query with signed aspects (README formula).
- **1:40-2:00 Limits.** Benchmark is simulated and shares features with the model; vocals is a proxy;
  previews are personal-use only and stay out of the repo.
