"""Pick a song, say what you like about it, get songs that match that."""

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from src.embeddings import AspectEmbeddings
from src.intent import LABELS, parse_preferences
from src.knowledge import KNOWLEDGE_ASPECTS, Knowledge, hybrid_recommend, load_records

DEFAULT_SONG = "One Dance"


@st.cache_resource
def load_catalog(path, modified):
    frame = pd.read_csv(path, index_col=0)
    model = AspectEmbeddings().fit(frame)
    return frame, model.transform(frame)


@st.cache_resource
def load_knowledge(path, tracks_modified):
    folder = Path(path).parent / "genius"
    if not folder.is_dir():
        return None
    records = load_records(folder)
    return Knowledge(pd.read_csv(path, index_col=0), records) if records else None


def vote(track, liked):
    st.session_state.feedback[track] = liked


def main():
    st.set_page_config(page_title="Song aspect recommender", layout="wide")
    st.title("Find more songs like the part you love")
    path = Path(os.environ.get("SONG_FEATURES", Path(__file__).parent / "data/hiphop_features.csv"))
    try:
        tracks, embeddings = load_catalog(str(path), path.stat().st_mtime_ns)
    except (OSError, ValueError) as exc:
        st.error(f"Cannot load catalog: {exc}. Run python -m src.catalog then python -m src.features first.")
        st.stop()
    knowledge = load_knowledge(str(path), path.stat().st_mtime_ns)
    source = ", ".join(sorted(tracks.source.dropna().unique())) if "source" in tracks else "unknown"
    if source != "itunes_preview":
        st.warning("Synthetic or unknown source: these features do not demonstrate real musical quality.")
    available = [a for a in LABELS if a in embeddings or (knowledge is not None and a in KNOWLEDGE_ASPECTS)]

    def label(track):
        row = tracks.loc[track]
        return f"{row.get('title', 'Unknown title')} — {row.get('artist', 'Unknown artist')}"

    if st.session_state.get("catalog_key") != (str(path), path.stat().st_mtime_ns):
        st.session_state.feedback = {}
        st.session_state.catalog_key = (str(path), path.stat().st_mtime_ns)

    st.subheader("1. Pick a song you like")
    ids = tracks.index.tolist()
    default = next((i for i in ids if DEFAULT_SONG.lower() in str(tracks.loc[i].get("title", "")).lower()), ids[0])
    seed = st.selectbox("Search the catalog", ids, index=ids.index(default), format_func=label, key="seed")
    picked = tracks.loc[seed]
    left, right = st.columns([1, 4])
    if isinstance(picked.get("artwork"), str):
        left.image(picked["artwork"])
    right.markdown(f"**{label(seed)}**")
    if isinstance(picked.get("preview_url"), str):
        right.audio(picked["preview_url"])

    st.subheader("2. What do you like about it?")
    mode = st.segmented_control("How do you want to tell me?", ["Pick aspects", "Describe it"],
                                default="Pick aspects", key="mode")
    liked, disliked, text = [], [], ""
    if mode == "Describe it":
        text = st.text_area("In your own words", key="text", height=90,
                            placeholder="e.g. the dancehall beat with the rapping on it, but not the drums")
        liked, disliked = parse_preferences(text, available)
        if text.strip():
            if liked or disliked:
                st.caption("I understood — **like:** " + (", ".join(LABELS[a] for a in liked) or "nothing")
                           + " · **avoid:** " + (", ".join(LABELS[a] for a in disliked) or "nothing")
                           + (" · I'll also match your exact words against song descriptions."
                              if knowledge is not None else ""))
            else:
                st.info("I couldn't find an aspect in that. Try words like beat, rapping, melody, vibe, "
                        "energy, drums, tempo, sound, or use Pick aspects.")
    else:
        liked = st.pills("I like…", available, selection_mode="multi", format_func=LABELS.get, key="likes") or []
        disliked = st.pills("I don't want…  (optional)", [a for a in available if a not in liked],
                            selection_mode="multi", format_func=LABELS.get, key="dislikes") or []
        disliked = [a for a in disliked if a not in liked]

    st.subheader("3. Songs for you")
    if not liked and not disliked:
        st.info("Choose at least one thing you like about the song above.")
        st.stop()
    if knowledge is None and any(a in KNOWLEDGE_ASPECTS for a in liked + disliked):
        st.info("Sample, producer, background-vocal and genre matching need song data: run python -m src.genius.")
        st.stop()
    limit = st.slider("How many songs", 1, 20, 10)
    ranked = hybrid_recommend(embeddings, knowledge, seed, liked, disliked, st.session_state.feedback,
                              text if mode == "Describe it" and knowledge is not None else "", limit)
    if ranked.empty:
        st.info("No unseen songs remain. Clear feedback.")
    for track, row in ranked.iterrows():
        info = tracks.loc[track]
        art, body, votes = st.columns([1, 6, 2])
        if isinstance(info.get("artwork"), str):
            art.image(info["artwork"])
        body.markdown(f"**{label(track)}**")
        notes = knowledge.explain(track, seed, liked) if knowledge is not None else []
        best = [a for a in row.drop("score").dropna().sort_values(ascending=False).index
                if a in liked and a not in KNOWLEDGE_ASPECTS][:2]
        if best:
            notes.append("sounds like your song on: " + ", ".join(LABELS[a].replace("The ", "") for a in best))
        if notes:
            body.caption(" · ".join(notes))
        if isinstance(info.get("preview_url"), str):
            body.audio(info["preview_url"])
        votes.button("👍 More like this", key=f"up_{track}", on_click=vote, args=(track, True))
        votes.button("👎 Less like this", key=f"down_{track}", on_click=vote, args=(track, False))
    st.caption(f"{len(st.session_state.feedback)} song votes this session. Thumbs shift the results toward or "
               "away from those songs. Scores are rankings, not probabilities. Previews are 30 s clips "
               "from iTunes for personal use.")
    if st.session_state.feedback:
        if st.button("Clear song feedback"):
            st.session_state.feedback = {}
            st.rerun()
        with st.expander("Review or replace votes"):
            for track, feedback in list(st.session_state.feedback.items()):
                st.write(f"{label(track)}: {'liked' if feedback else 'disliked'}")
                st.button("Change to dislike" if feedback else "Change to like", key=f"replace_{track}",
                          on_click=vote, args=(track, not feedback))


if __name__ == "__main__":
    main()
