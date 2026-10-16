"""Local, session-scoped Streamlit interface to the aspect recommender."""

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from src.embeddings import ASPECT_GROUPS, AspectEmbeddings
from src.recommender import AspectRecommender


@st.cache_resource
def load_catalog(path, modified):
    frame = pd.read_csv(path, index_col=0)
    model = AspectEmbeddings().fit(frame)
    return frame, model.transform(frame)


def vote(track, liked):
    st.session_state.feedback[track] = liked


def main():
    st.set_page_config(page_title="Rock aspect recommender", layout="wide")
    st.title("Rock aspect recommender")
    st.caption("Audio features come from FMA, a CC-licensed dataset. Metadata/features: CC BY 4.0; "
               "recordings have individual artist-selected licenses. No audio is hosted here.")
    st.markdown("[FMA attribution and licenses](https://github.com/mdeff/fma#acknowledgments-and-licenses): "
                "Defferrard, Benzi, Vandergheynst & Bresson, ISMIR 2017.")
    path = Path(os.environ.get("SONG_FEATURES", Path(__file__).parent / "data/rock_features.csv"))
    try:
        tracks, embeddings = load_catalog(str(path), path.stat().st_mtime_ns)
    except (OSError, ValueError) as exc:
        st.error(f"Cannot load catalog: {exc}. Run python -m src.data first.")
        st.stop()
    source = ", ".join(sorted(tracks.source.dropna().unique())) if "source" in tracks else "unknown"
    st.info(f"Catalog: {len(tracks):,} tracks · source: {source}")
    if source != "fma":
        st.warning("Synthetic or unknown source: these features do not demonstrate real musical quality.")
    st.caption("Like = match this aspect of the seed; dislike = avoid it. Without a seed, toggles "
               "rank feature distinctiveness, not high/low aspect values. Mood is a brightness/harmony proxy.")
    st.caption("Tempo/beat: standard FMA features have no explicit BPM or beat measurements; "
               "these controls remain unavailable without measured additional features.")
    liked, disliked = [], []
    for aspect in ASPECT_GROUPS:
        cols = st.columns([2, 1, 1])
        available = aspect in embeddings
        cols[0].write(aspect.title() + ("" if available else " (unavailable)"))
        like = cols[1].toggle(f"Like {aspect}", value=aspect == "melody" and available,
                              disabled=not available, key=f"like_{aspect}")
        dislike = cols[2].toggle(f"Dislike {aspect}", disabled=not available, key=f"dislike_{aspect}")
        if like and available:
            liked.append(aspect)
        if dislike and available:
            disliked.append(aspect)
    def label(track):
        return f"{track}: {tracks.loc[track].get('title', 'Unknown title')} — {tracks.loc[track].get('artist', 'Unknown artist')}"
    seeds = st.multiselect("Reference songs (optional)", tracks.index.tolist(), format_func=label)
    limit = st.slider("Number of recommendations", 1, 20, 10)
    if st.session_state.get("catalog_key") != (str(path), path.stat().st_mtime_ns):
        st.session_state.feedback = {}
        st.session_state.catalog_key = (str(path), path.stat().st_mtime_ns)
    if st.button("Clear song feedback"):
        st.session_state.feedback = {}
    st.caption(f"{len(st.session_state.feedback)} song votes in this session. Votes persist across aspect "
               "changes; clear them to start over. A new vote replaces an old vote.")
    if set(liked) & set(disliked):
        st.warning("Choose either like or dislike for each aspect.")
        st.stop()
    if not liked and not disliked:
        st.info("Select at least one available aspect.")
        st.stop()
    recommender = AspectRecommender(embeddings, liked, disliked, seeds)
    for track, feedback in st.session_state.feedback.items():
        recommender.update_feedback(track, feedback)
    ranked = recommender.recommend(limit)
    display = tracks.reindex(ranked.index).reindex(columns=["title", "artist"]).join(ranked)
    st.dataframe(display, width="stretch")
    st.caption("Scores are relative rankings, not probabilities. Seeds and voted songs are excluded.")
    if ranked.empty:
        st.info("No unseen songs remain. Clear feedback or remove reference songs.")
    for track in ranked.index:
        cols = st.columns([6, 1, 1])
        cols[0].write(label(track))
        cols[1].button("Like song", key=f"up_{track}", on_click=vote, args=(track, True))
        cols[2].button("Dislike song", key=f"down_{track}", on_click=vote, args=(track, False))
    if st.session_state.feedback:
        with st.expander("Review or replace previous votes"):
            for track, feedback in list(st.session_state.feedback.items()):
                st.write(f"{label(track)}: {'liked' if feedback else 'disliked'}")
                st.button("Change to dislike" if feedback else "Change to like", key=f"replace_{track}",
                          on_click=vote, args=(track, not feedback))


if __name__ == "__main__":
    main()
