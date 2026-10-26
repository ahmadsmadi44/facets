# Why the v1 recommendations were bad

Run on 2026-10-26 against the v1 model (librosa summary features plus the Genius knowledge layer).
I used Ahmad's eight seed songs and a request a listener would plausibly make for each. Verdicts
are my own listening judgement of the returned titles. The ground truth is Ahmad's ratings in the
blind test (see `results/ratings.md` once rated).

| Seed and request | Top results from v1 | What's wrong |
| --- | --- | --- |
| Champagne Poetry: sample + background vocals + "angelic choir sample" | It's All On Me, God Is, Water, Moon (Kanye), Flight's Booked | Half right. The gospel feel came through via Genius credits, but the list is Kanye-heavy and has filler. |
| 8am in Charlotte: melody + vocals | Only (Nicki), Coming Down, Water (Remix) (Tyla) | Introspective soul-sample rap returned trap-pop and amapiano. |
| Stories About My Brother: vocals + melody | GO (Juice WRLD), The Way Life Goes, What the Price | Wrong mood: emo-trap and Migos for a reflective storytelling song. |
| Make Them Pay: drums + sample | Panini, Super Freaky Girl, BREAK MY SOUL | "Drums" from whole-mix percussive statistics means "bright and punchy", not "drums that sound like these". |
| Love All: vocals + melody | Lil Baby, Gunna, Future | A surface "rap vocals" match that misses the soulful Jay-Z collaboration. |
| I Got A Story To Tell: vocals + drums | Tribe, Pete Rock & C.L. Smooth … Swedish House Mafia | Mostly right (90s boom bap), but one aspect alone dragged in a house track. |
| September: rhythm + backing | Narcos, Don't Push Me, Don't Matter To Me ×2 | No disco groove at all, and a duplicate version. |
| Ain't No Mountain: vocals + backing | In Love, Been Like This, Riot | No soul duet or Motown feel. |

## Root causes and fixes

1. **The seeds weren't in the catalog.** It held each artist's top 25 search hits, so Drake album cuts, Biggie, Earth Wind & Fire and Marvin Gaye were missing. *Fix:* forced seeds (`seeds.txt`), deeper Drake, and 52 more soul, Motown, 90s, soul-sample and alt-R&B artists (1,027 → 2,783 songs). Deezer is the fallback for one song missing from US iTunes.
2. **"Drums" and "vocals" were not isolated.** HPSS percussive energy and a voice-band filter still describe the whole mix. *Fix:* Demucs stem separation (drums, bass, other, vocals). Each stem is embedded with CLAP (`laion/larger_clap_music_and_speech`; the `larger_clap_music` checkpoint has a collapsed text tower).
3. **One aspect could override genre and era** (Biggie → Swedish House Mafia). *Fix:* a 0.35-weight whole-mix coherence term under the aspect scores.
4. **No diversity and duplicate versions** (four Kanye songs, *Don't Matter To Me* twice). *Fix:* MMR re-ranking, a cap of two songs per artist, and one version per title.
5. **Words like "angelic" or "boom bap" had nothing to match.** *Fix:* 94 human descriptors ("angelic vocals", "gospel choir", "boom bap drums", "sliding 808"…) scored zero-shot by CLAP on the matching stem. They're z-normalised across the catalog to remove CLAP's prompt bias, and drive both text queries and the per-song tags.
6. **Knowledge scores were flat** (any song with a sample got the same 0.5). *Fix:* graded scores: a shared sample source or a direct sample link scores above "has some sample", and a song with none scores below neutral. Combined with the "other" stem similarity.

FMA-era causes from the original task list (weak FMA features, an obscure long tail, "rock" being too broad) no longer apply. The catalog is now mainstream iTunes previews of artists Ahmad chose.
