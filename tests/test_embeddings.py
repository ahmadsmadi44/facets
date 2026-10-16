import numpy as np
import pandas as pd
import pytest

from src.data import synthetic_features
from src.embeddings import ASPECT_GROUPS, AspectEmbeddings, aspect_columns


def test_mapping_covers_fma_and_optional_measurements():
    families = ["tempogram", "tempo", "chroma_cens", "mfcc", "spectral_contrast",
                "rmse", "zcr", "tonnetz", "spectral_centroid"]
    frame = pd.DataFrame(columns=pd.MultiIndex.from_tuples(
        [(family, "mean", "01") for family in families]))
    groups = aspect_columns(frame)
    assert set(groups) == set(ASPECT_GROUPS)
    assert all(groups.values())
    assert len(groups["timbre"]) == 2
    assert len(groups["mood"]) == 2


def test_training_only_fit_missing_values_and_saved_roundtrip(tmp_path):
    frame = synthetic_features(40)
    frame["split"] = ["training"] * 30 + ["test"] * 10
    frame.loc[1, "mfcc__mean__00"] = np.nan
    frame.loc[2, "rms__mean__00"] = np.inf
    frame["mfcc__mean__missing"] = np.nan
    model = AspectEmbeddings(3).fit(frame)
    assert model.unavailable_aspects == ["rhythm", "tempo"]
    baseline = model.transform(frame)
    changed = frame.copy()
    changed.loc[31:, "mfcc__mean__01"] = 1e12
    other = AspectEmbeddings(3).fit(changed)
    for aspect in model.models:
        np.testing.assert_allclose(baseline[aspect].iloc[:30], other.transform(changed)[aspect].iloc[:30])
    model.save(tmp_path)
    restored = AspectEmbeddings.load(tmp_path).transform(frame)
    for aspect, values in baseline.items():
        assert values.shape[1] <= 3
        assert np.isfinite(values).all().all()
        pd.testing.assert_frame_equal(values, restored[aspect])
    assert "mfcc__mean__missing" not in model.models["timbre"][0]


def test_aspects_are_independent():
    frame = synthetic_features(30)
    first = AspectEmbeddings(2).fit(frame).transform(frame)
    frame.loc[:, frame.columns.str.startswith("mfcc__")] *= -3
    second = AspectEmbeddings(2).fit(frame).transform(frame)
    for aspect in ("melody", "energy", "mood"):
        pd.testing.assert_frame_equal(first[aspect], second[aspect])


def test_fit_and_transform_validation():
    with pytest.raises(ValueError, match="Fit"):
        AspectEmbeddings().transform(pd.DataFrame())
    with pytest.raises(ValueError, match="positive integer"):
        AspectEmbeddings(0)
    with pytest.raises(ValueError, match="two training"):
        AspectEmbeddings().fit(synthetic_features(1))
    with pytest.raises(ValueError, match="No usable"):
        AspectEmbeddings().fit(pd.DataFrame({"mfcc__mean__00": [1, 1]}))
    frame = synthetic_features(20)
    model = AspectEmbeddings().fit(frame)
    with pytest.raises(ValueError, match="Missing features"):
        model.transform(frame.drop(columns="mfcc__mean__00"))
    with pytest.raises(ValueError, match="unique"):
        model.fit(pd.concat([frame, frame]))
