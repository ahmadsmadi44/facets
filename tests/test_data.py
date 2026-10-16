import numpy as np

from src.catalog import base_title, credited, split_for
from src.data import synthetic_features
from src.embeddings import ASPECT_GROUPS, aspect_columns


def test_credited_artist_is_exact():
    assert credited("Drake & Future", "future")
    assert credited("Tyler, The Creator", "tyler, the creator")
    assert not credited("Future Islands", "future")
    assert not credited("Dionas", "nas")


def test_title_dedupe_and_split_are_stable():
    assert base_title("Hotline Bling (Remastered)") == base_title("Hotline Bling")
    assert split_for(123456) == split_for(123456)
    assert {split_for(i) for i in range(1000)} == {"training", "validation", "test"}


def test_synthetic_covers_every_aspect_and_is_reproducible():
    frame = synthetic_features(50)
    assert all(aspect_columns(frame)[aspect] for aspect in ASPECT_GROUPS)
    assert np.isfinite(frame.select_dtypes("number")).all().all()
    assert frame.equals(synthetic_features(50))
