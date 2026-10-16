"""Reproducible feature-alignment benchmark; no real listener relevance labels."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from src.embeddings import AspectEmbeddings, aspect_columns
from src.recommender import AspectRecommender


def unit(values):
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    return np.divide(values, norms, out=np.zeros_like(values), where=norms > 0)


def standardized(frame, columns, training):
    values = frame[columns].astype(float).replace([np.inf, -np.inf], np.nan)
    values = values.loc[:, values.loc[training].notna().any()]
    imputer = SimpleImputer(strategy="median").fit(values.loc[training])
    scaler = StandardScaler().fit(imputer.transform(values.loc[training]))
    return unit(scaler.transform(imputer.transform(values)))


def ranking_metrics(order, utility, negative_similarities, k):
    """Binary relevance = top quintile of oracle utility in the test catalog."""
    top = np.asarray(order[:k])
    relevant = utility >= np.quantile(utility, .8)
    discounts = 1 / np.log2(np.arange(len(top)) + 2)
    ideal = discounts[:min(int(relevant.sum()), len(top))].sum()
    return {
        "aspect_consistency": float(np.mean((utility[top] + 1) / 2)),
        "precision_at_k": float(relevant[top].mean()),
        "ndcg_at_k": float(np.sum(relevant[top] * discounts) / ideal) if ideal else 0.,
        "negative_aspect_avoidance_rate": (
            float((negative_similarities[:, top] <= 0).mean())
            if len(negative_similarities) else None),
    }


def evaluate(frame, users=40, k=10, seed=42):
    if users < 4 or k < 1:
        raise ValueError("At least four users and a positive k are required")
    if "split" not in frame or not frame.index.is_unique:
        raise ValueError("Unique track IDs and explicit training/test splits are required")
    training = frame.split.eq("training")
    candidates = np.flatnonzero(frame.split.eq("test"))
    references = np.flatnonzero(training)
    if len(references) < 2 or len(candidates) < k:
        raise ValueError("Need two training tracks and at least k held-out test tracks")
    model = AspectEmbeddings().fit(frame)
    embeddings = model.transform(frame)
    aspects = sorted(embeddings)
    if len(aspects) < 2:
        raise ValueError("At least two aspects are required for mixed preferences")
    groups = aspect_columns(frame)
    raw = {a: standardized(frame, groups[a], training) for a in aspects}
    generic = standardized(frame, [c for c in frame if "__" in str(c)], training)
    rng = np.random.default_rng(seed)
    samples = {"aspect": [], "generic_cosine": []}
    examples = []
    candidate_ids = frame.index[candidates]
    # Include one training reference, then restrict ranking to held-out tracks.
    for user in range(users):
        reference = int(rng.choice(references))
        positive, negative = rng.choice(aspects, 2, replace=False).tolist()
        similarities = {a: raw[a][candidates] @ raw[a][reference] for a in (positive, negative)}
        utility = (similarities[positive] - similarities[negative]) / 2
        subset = {a: pd.concat([v.iloc[[reference]], v.iloc[candidates]])
                  for a, v in embeddings.items()}
        ranked = AspectRecommender(subset, [positive], [negative],
                                   [frame.index[reference]]).recommend(k)
        orders = {
            "aspect": candidate_ids.get_indexer(ranked.index),
            "generic_cosine": np.argsort(-(generic[candidates] @ generic[reference]), kind="stable")[:k],
        }
        for method, order in orders.items():
            samples[method].append(ranking_metrics(
                order, utility, similarities[negative][None, :], k))
        if user < 4:
            examples.append({"seed": frame.index[reference], "like": positive, "dislike": negative,
                             "rankings": {m: candidate_ids[o].tolist() for m, o in orders.items()}})
    aggregates = {method: {name: float(np.mean([row[name] for row in rows]))
                           for name in rows[0]} for method, rows in samples.items()}
    metrics = {
        "protocol": "Training-only imputation/scaling/PCA; training references; test-only candidates. "
                    "Each simulated user likes one aspect and avoids another relative to a seed. "
                    "Oracle utility is mean signed cosine in standardized original aspect features; "
                    "binary relevance is the top test-catalog utility quintile (ties included). "
                    "Aspect consistency maps signed utility from [-1,1] to [0,1]. "
                    "Avoidance counts disliked-aspect cosine <= 0. Macro means over users. "
                    "Generic baseline uses cosine over all standardized audio feature columns. "
                    "Labels share input features with the model: these are alignment diagnostics, "
                    "not independent human relevance or causal evidence.",
        "seed": seed, "simulated_users": users, "k": k,
        "rows": len(frame), "training_tracks": len(references), "test_tracks": len(candidates),
        "source": sorted(frame.source.dropna().unique().tolist()) if "source" in frame else ["unknown"],
        "available_aspects": aspects, "unavailable_aspects": model.unavailable_aspects,
        "methods": aggregates,
        "aspect_minus_baseline": {name: aggregates["aspect"][name] - aggregates["generic_cosine"][name]
                                  for name in aggregates["aspect"]},
    }
    return metrics, examples


def write_results(frame, metrics, examples, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    def label(track):
        row = frame.loc[track]
        title = str(row.get("title", "Unknown title"))
        artist = str(row.get("artist", "Unknown artist"))
        return f"{track}: {title} — {artist}".replace("\n", " ").replace("\r", " ").replace("|", "\\|")
    lines = ["# Four reproducible example queries", "", f"Source: {', '.join(metrics['source'])}. "
             "Like/dislike means similarity/avoidance relative to the seed, not high/low BPM or mood.", ""]
    for i, query in enumerate(examples, 1):
        lines += [f"## Query {i}", "", f"Seed: {label(query['seed'])}", "",
                  f"Like **{query['like']}**; dislike **{query['dislike']}**.", "",
                  "| Rank | Aspect recommender | Generic cosine |", "| --- | --- | --- |"]
        rankings = query["rankings"]
        for rank, (a, b) in enumerate(zip(rankings["aspect"], rankings["generic_cosine"]), 1):
            lines.append(f"| {rank} | {label(a)} | {label(b)} |")
        lines.append("")
    (output / "example_queries.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, default=Path("data/hiphop_features.csv"))
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--users", type=int, default=40)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    frame = pd.read_csv(args.features, index_col=0)
    metrics, examples = evaluate(frame, args.users, args.k, args.seed)
    metrics["features_sha256"] = hashlib.sha256(args.features.read_bytes()).hexdigest()
    write_results(frame, metrics, examples, args.output)
    print(json.dumps(metrics["methods"], indent=2))


if __name__ == "__main__":
    main()
