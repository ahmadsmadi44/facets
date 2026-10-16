import numpy as np
import pandas as pd
import pytest

from src.data import synthetic_features
from src.embeddings import AspectEmbeddings
from src.recommender import AspectRecommender


@pytest.fixture
def embeddings():
    # Candidate 2 matches seed melody but opposes its timbre; 3 does the reverse.
    return {
        "melody": pd.DataFrame([[1., 0], [1, 0], [-1, 0], [0, 1]], index=[1, 2, 3, 4]),
        "timbre": pd.DataFrame([[1., 0], [-1, 0], [1, 0], [0, 1]], index=[1, 2, 3, 4]),
    }


def test_selected_aspects_control_ranking(embeddings):
    melody = AspectRecommender(embeddings, ["melody"], seed_songs=[1])
    timbre = AspectRecommender(embeddings, ["timbre"], seed_songs=[1])
    selective = AspectRecommender(embeddings, ["melody"], ["timbre"], [1])
    assert melody.recommend().index[0] == 2
    assert timbre.recommend().index[0] == 3
    scores = selective.recommend()
    assert scores.index[0] == 2
    assert scores.loc[2, "score"] == pytest.approx(1)
    assert scores.loc[3, "score"] == pytest.approx(-1)
    # Unselected timbre cannot change a melody-only ranking.
    embeddings["timbre"] *= -1000
    pd.testing.assert_frame_equal(melody.recommend(), AspectRecommender(
        embeddings, ["melody"], seed_songs=[1]).recommend())


def test_rocchio_feedback_replaces_votes_and_excludes_seen(embeddings):
    recommender = AspectRecommender(embeddings, ["melody"], seed_songs=[1])
    recommender.update_feedback(4, True)
    scores = recommender.recommend(exclude_seen=False)
    assert scores.loc[4, "score"] == pytest.approx(.75)
    recommender.update_feedback(4, False).update_feedback(4, False)
    assert recommender.recommend(exclude_seen=False).loc[4, "score"] == pytest.approx(-.25)
    assert set(recommender.recommend().index) == {2, 3}
    recommender.update_feedback(1, False)
    assert recommender.recommend(exclude_seen=False).loc[2, "score"] < 0


def test_negative_feedback_repels_even_for_disliked_aspect(embeddings):
    recommender = AspectRecommender(embeddings, disliked_aspects=["timbre"], seed_songs=[1])
    before = recommender.recommend(exclude_seen=False).loc[2, "score"]
    recommender.update_feedback(2, False)
    assert recommender.recommend(exclude_seen=False).loc[2, "score"] < before


def test_seedless_distinctiveness_and_feedback():
    vectors = {"energy": pd.DataFrame([[3., 0], [1, 0], [0, 1]], index=[1, 2, 3])}
    liked = AspectRecommender(vectors, ["energy"])
    disliked = AspectRecommender(vectors, disliked_aspects=["energy"])
    assert liked.recommend().index[0] == 1
    assert disliked.recommend().index[-1] == 1
    liked.update_feedback(3, True)
    assert liked.recommend(exclude_seen=False).index[0] == 3


@pytest.mark.parametrize("kwargs", [
    {}, {"liked_aspects": ["tempo"]},
    {"liked_aspects": ["melody"], "disliked_aspects": ["melody"]},
    {"liked_aspects": ["melody"], "seed_songs": [99]},
    {"liked_aspects": ["melody"], "gamma": -1},
    {"liked_aspects": ["melody"], "beta": np.nan},
])
def test_invalid_requests(embeddings, kwargs):
    with pytest.raises(ValueError):
        AspectRecommender(embeddings, **kwargs)


def test_invalid_feedback_and_misaligned_ids(embeddings):
    recommender = AspectRecommender(embeddings, ["melody"])
    with pytest.raises(ValueError, match="Unknown"):
        recommender.update_feedback(99, True)
    with pytest.raises(ValueError, match="True or False"):
        recommender.update_feedback(1, "like")
    with pytest.raises(ValueError, match="positive integer"):
        recommender.recommend(0)
    embeddings["timbre"] = embeddings["timbre"].iloc[::-1]
    with pytest.raises(ValueError, match="same track"):
        AspectRecommender(embeddings, ["melody", "timbre"])


def test_pipeline_to_recommendations(tmp_path):
    frame = synthetic_features(50)
    model = AspectEmbeddings(4).fit(frame)
    model.save(tmp_path)
    recommender = AspectRecommender(AspectEmbeddings.load(tmp_path).transform(frame),
                                   ["melody"], ["timbre"], [1, 2])
    recommender.update_feedback(3, True).update_feedback(4, False)
    result = recommender.recommend(7)
    assert len(result) == 7
    assert result.score.is_monotonic_decreasing
    assert not set(result.index) & {1, 2, 3, 4}
    assert np.isfinite(result).all().all()
