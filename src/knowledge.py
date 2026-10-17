"""Human-style descriptors from Genius (bio, credits, samples) and a hybrid recommender.

Audio statistics cannot hear a sample or a backing vocal; these aspects use what people have
written and credited instead. Scores are relative to the seed song, in [0, 1].
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from src.catalog import base_title
from src.recommender import AspectRecommender

KNOWLEDGE_ASPECTS = ("sample", "backing", "people", "style")
BACKING = re.compile(r"background|backing|additional vocals|choir|chorus|harmon", re.I)
SAMPLE_WORDS = re.compile(r"sampl|interpolat|chop", re.I)
BACKING_BIO = re.compile(r"background vocal|backing vocal|harmon|choir|gospel", re.I)


def source_key(full_title):
    """'Do You Mind by Kyla' -> 'do you mind' (Genius titles contain non-breaking spaces)."""
    return base_title(full_title.replace(" ", " ").rsplit(" by ", 1)[0])


def load_records(folder):
    records = {}
    for path in Path(folder).glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("matched"):
            records[record["track_id"]] = record
    return records


class Knowledge:
    def __init__(self, tracks, records):
        self.index = tracks.index
        self.tracks = tracks
        get = lambda i: records.get(int(i), {})
        rel = lambda i, *names: {source_key(t) for n in names for t in get(i).get("relationships", {}).get(n, [])}
        self.key = {i: base_title(str(tracks.loc[i, "title"])) for i in self.index}
        self.sources = {i: rel(i, "samples", "interpolates") for i in self.index}
        self.sampled_by = {i: rel(i, "sampled_in", "interpolated_by") for i in self.index}
        self.producers = {i: {p.lower() for p in get(i).get("producers", [])} for i in self.index}
        self.writers = {i: {p.lower() for p in get(i).get("writers", [])} for i in self.index}
        self.bio = {i: get(i).get("bio", "") for i in self.index}
        self.backing = pd.Series({i: any(BACKING.search(label) for label in get(i).get("performances", {}))
                                  or bool(BACKING_BIO.search(self.bio[i])) for i in self.index})
        self.has_sample = pd.Series({i: bool(self.sources[i]) or bool(SAMPLE_WORDS.search(self.bio[i]))
                                     for i in self.index})
        self.vectorizer = TfidfVectorizer(stop_words="english", sublinear_tf=True, ngram_range=(1, 2), min_df=2)
        corpus = [f"{self.bio[i]} {tracks.loc[i].get('genre', '')}" for i in self.index]
        self.matrix = self.vectorizer.fit_transform(corpus)

    def _text_similarity(self, vector):
        scores = (self.matrix @ vector.T).toarray().ravel()
        top = scores.max()
        return pd.Series(scores / top if top > 0 else scores, index=self.index)

    def score(self, aspect, seed):
        if aspect == "sample":
            seed_key, seed_sources = self.key[seed], self.sources[seed]
            base = self._text_similarity(self.matrix[self.index.get_loc(seed)]) * 0.2
            out = []
            for i in self.index:
                if self.sources[i] & seed_sources or self.sources[i] & {seed_key} or self.key[i] in seed_sources:
                    value = 1.0
                elif self.sources[i]:
                    value = 0.5
                elif self.has_sample[i]:
                    value = 0.4
                else:
                    value = 0.0
                out.append(value)
            return (pd.Series(out, index=self.index) + base * (pd.Series(out, index=self.index) > 0)).clip(upper=1)
        if aspect == "backing":
            return self.backing.astype(float)
        if aspect == "people":
            sp, sw = self.producers[seed], self.writers[seed] - {str(self.tracks.loc[seed, "artist"]).lower()}
            return pd.Series([min(1.0, 0.7 * len(self.producers[i] & sp) / max(1, len(sp))
                                  + 0.3 * len(self.writers[i] & sw) / max(1, len(sw))) for i in self.index],
                             index=self.index)
        if aspect == "style":
            return self._text_similarity(self.matrix[self.index.get_loc(seed)])
        raise ValueError(f"Unknown knowledge aspect: {aspect}")

    def text_score(self, text):
        """How well each song's bio matches a free-text description like 'angelic vocal sample'."""
        return self._text_similarity(self.vectorizer.transform([text]))

    def explain(self, track, seed, aspects):
        notes = []
        if "sample" in aspects:
            shared = self.sources[track] & self.sources[seed]
            if shared:
                notes.append(f"shares sample/source '{sorted(shared)[0]}' with your song")
            elif self.sources[track] & {self.key[seed]} or self.key[track] in self.sources[seed]:
                notes.append("directly samples or is sampled by your song")
            elif self.sources[track]:
                notes.append(f"samples '{sorted(self.sources[track])[0]}'")
            elif self.has_sample[track]:
                notes.append("bio mentions a sample")
        if "backing" in aspects and self.backing[track]:
            notes.append("credited background/additional vocals")
        if "people" in aspects:
            shared = self.producers[track] & self.producers[seed]
            if shared:
                notes.append("shared producer: " + ", ".join(sorted(shared)[:2]))
        return notes


def hybrid_recommend(embeddings, knowledge, seed, liked, disliked, feedback=None, text="", limit=10):
    """Audio-aspect Rocchio score plus knowledge-aspect scores; dislikes subtract."""
    feedback = feedback or {}
    audio_liked = [a for a in liked if a in embeddings]
    audio_disliked = [a for a in disliked if a in embeddings]
    know_liked = [a for a in liked if a in KNOWLEDGE_ASPECTS]
    know_disliked = [a for a in disliked if a in KNOWLEDGE_ASPECTS]
    if (know_liked or know_disliked or text.strip()) and knowledge is None:
        raise ValueError("Song knowledge (python -m src.genius) is required for these aspects")
    if audio_liked or audio_disliked:
        base, weight = AspectRecommender(embeddings, audio_liked, audio_disliked, [seed]), 1.0
    else:
        # Knowledge-only request: overall sound similarity (and votes) only breaks ties.
        base, weight = AspectRecommender(embeddings, sorted(embeddings), [], [seed]), 0.3
    for track, value in feedback.items():
        base.update_feedback(track, value)
    ranked = base.recommend(len(base.index))
    ranked["score"] = ranked["score"] * weight
    for aspect in know_liked:
        ranked[aspect] = knowledge.score(aspect, seed).reindex(ranked.index)
        ranked["score"] += ranked[aspect]
    for aspect in know_disliked:
        ranked[aspect] = knowledge.score(aspect, seed).reindex(ranked.index)
        ranked["score"] -= ranked[aspect]
    if text.strip():
        ranked["feel"] = knowledge.text_score(text).reindex(ranked.index)
        ranked["score"] += ranked["feel"]
    return ranked.sort_values("score", ascending=False, kind="stable").head(limit)
