import json

import numpy as np
import pytest

from src.data import synthetic_features
from src.evaluate import evaluate, ranking_metrics, write_results


def test_metrics_have_known_perfect_and_reversed_ranks():
    utility = np.array([1., .5, 0., -.5, -1.])
    negative = np.array([[-1., -1., 0., 1., 1.]])
    perfect = ranking_metrics([0], utility, negative, 1)
    assert perfect == dict(aspect_consistency=1., precision_at_k=1., ndcg_at_k=1.,
                           negative_aspect_avoidance_rate=1.)
    worst = ranking_metrics([4], utility, negative, 1)
    assert all(value == 0 for value in worst.values())
    assert ranking_metrics([0], utility, np.empty((0, 5)), 1)["negative_aspect_avoidance_rate"] is None


def fixture_frame():
    frame = synthetic_features(80)
    frame["split"] = ["training"] * 50 + ["validation"] * 10 + ["test"] * 20
    return frame


def test_reproducible_heldout_queries_and_artifacts(tmp_path):
    frame = fixture_frame()
    metrics, examples = evaluate(frame, users=4, k=5)
    assert (metrics, examples) == evaluate(frame, users=4, k=5)
    assert metrics["training_tracks"] == 50
    assert metrics["test_tracks"] == 20
    for query in examples:
        assert frame.loc[query["seed"], "split"] == "training"
        assert query["like"] != query["dislike"]
        for ranking in query["rankings"].values():
            assert len(ranking) == len(set(ranking)) == 5
            assert frame.loc[ranking, "split"].eq("test").all()
    for method in metrics["methods"].values():
        assert all(0 <= score <= 1 for score in method.values())
    write_results(frame, metrics, examples, tmp_path)
    assert json.loads((tmp_path / "metrics.json").read_text()) == metrics
    assert (tmp_path / "example_queries.md").read_text(encoding="utf-8").count("## Query ") == 4


def test_split_and_size_validation():
    frame = fixture_frame()
    with pytest.raises(ValueError, match="splits"):
        evaluate(frame.drop(columns="split"))
    with pytest.raises(ValueError, match="held-out"):
        evaluate(frame, k=21)
    with pytest.raises(ValueError, match="four users"):
        evaluate(frame, users=1)
