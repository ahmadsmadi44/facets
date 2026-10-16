"""Aspect-specific Rocchio ranking with replaceable song feedback."""

import numpy as np
import pandas as pd


class AspectRecommender:
    def __init__(self, embeddings, liked_aspects=(), disliked_aspects=(),
                 seed_songs=(), alpha=1.0, beta=0.75, gamma=0.25):
        self.liked_aspects = set(liked_aspects)
        self.disliked_aspects = set(disliked_aspects)
        selected = self.liked_aspects | self.disliked_aspects
        if not selected:
            raise ValueError("Select at least one liked or disliked aspect")
        if self.liked_aspects & self.disliked_aspects:
            raise ValueError("An aspect cannot be both liked and disliked")
        if selected - embeddings.keys():
            raise ValueError(f"Unavailable aspects: {sorted(selected - embeddings.keys())}")
        if not all(np.isfinite(v) and v >= 0 for v in (alpha, beta, gamma)):
            raise ValueError("Rocchio weights must be finite and nonnegative")
        self.alpha, self.beta, self.gamma = alpha, beta, gamma
        self.index = embeddings[next(iter(sorted(selected)))].index.copy()
        if not self.index.is_unique or self.index.empty:
            raise ValueError("Unique, nonempty track IDs are required")
        self.vectors = {}
        self.salience = {}
        for aspect in sorted(selected):
            frame = embeddings[aspect]
            if not frame.index.equals(self.index):
                raise ValueError("All aspect embeddings must have the same track IDs and order")
            values = frame.to_numpy(dtype=float)
            if not np.isfinite(values).all() or values.shape[1] == 0:
                raise ValueError("Embeddings must be finite and nonempty")
            norms = np.linalg.norm(values, axis=1, keepdims=True)
            self.vectors[aspect] = np.divide(values, norms, out=np.zeros_like(values), where=norms > 0)
            # With no references, distinctiveness is the only available signal;
            # it measures distance from training average, not musical quality.
            self.salience[aspect] = norms[:, 0] / (1 + norms[:, 0])
        self.seeds = set(seed_songs)
        self.feedback = {}
        self._positions(self.seeds)

    def _positions(self, songs):
        positions = self.index.get_indexer(list(songs))
        if (positions < 0).any():
            raise ValueError("Unknown song ID")
        return positions

    def update_feedback(self, song_id, liked):
        """A repeated vote replaces the previous vote instead of adding weight."""
        self._positions([song_id])
        if not isinstance(liked, bool):
            raise ValueError("liked must be True or False")
        self.feedback[song_id] = liked
        return self

    def recommend(self, limit=10, exclude_seen=True):
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        # Negative feedback on a seed overrides that seed's positive reference.
        seeds = self._positions(self.seeds - {s for s, liked in self.feedback.items() if not liked})
        positive = self._positions([s for s, liked in self.feedback.items() if liked])
        negative = self._positions([s for s, liked in self.feedback.items() if not liked])
        contributions = {}
        for aspect, vectors in self.vectors.items():
            sign = 1 if aspect in self.liked_aspects else -1
            query = np.zeros(vectors.shape[1])
            base = np.zeros(len(self.index))
            if len(seeds):
                query += sign * self.alpha * vectors[seeds].mean(axis=0)
            elif not self.seeds:
                base = sign * self.alpha * self.salience[aspect]
            # Song likes/dislikes refer to whole songs within selected aspects;
            # dislikes always repel, even for an aspect marked disliked.
            if len(positive):
                query += self.beta * vectors[positive].mean(axis=0)
            if len(negative):
                query -= self.gamma * vectors[negative].mean(axis=0)
            contributions[aspect] = base + vectors @ query
        result = pd.DataFrame(contributions, index=self.index)
        result["score"] = result.sum(axis=1) / len(contributions)
        if exclude_seen:
            result = result.drop(index=list(self.seeds | self.feedback.keys()))
        return result.sort_values("score", ascending=False, kind="stable").head(limit)
