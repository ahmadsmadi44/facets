import pandas as pd

from src.data import synthetic_features
from src.embeddings import AspectEmbeddings
from src.intent import parse_preferences
from src.knowledge import Knowledge, hybrid_recommend, source_key


def fixture():
    tracks = synthetic_features(40)
    records = {
        1: {"bio": "Slowed down vocal sample", "producers": ["40", "Nineteen85"], "writers": ["Drake"],
            "performances": {}, "relationships": {"samples": ["Do You Mind by\xa0Kyla"]}},
        2: {"bio": "Another track", "producers": ["Nineteen85"], "writers": ["X"],
            "performances": {"Background Vocals": ["Y"]},
            "relationships": {"samples": ["Do You Mind by\xa0Kyla"]}},
        3: {"bio": "A track with a sample of gospel", "producers": ["Other"], "writers": [],
            "performances": {}, "relationships": {}},
        4: {"bio": "plain", "producers": ["Other"], "writers": [], "performances": {}, "relationships": {}},
    }
    tracks["title"] = [f"Song {i}" for i in tracks.index]
    return tracks, records


def test_source_key_handles_nonbreaking_spaces():
    assert source_key("Do You Mind by\xa0Kyla") == "do you mind"


def test_knowledge_scores_samples_producers_and_backing():
    tracks, records = fixture()
    k = Knowledge(tracks, records)
    sample = k.score("sample", 1)
    assert sample[2] == 1.0 and sample[4] == 0.0 and 0 < sample[3] < 1
    assert k.score("people", 1)[2] > 0 and k.score("people", 1)[4] == 0
    assert k.backing[2] and not k.backing[1]
    assert any("shares sample" in note for note in k.explain(2, 1, ["sample"]))


def test_hybrid_ranks_sample_and_backing_first_and_dislikes_subtract():
    tracks, records = fixture()
    tracks["split"] = "training"
    embeddings = AspectEmbeddings().fit(tracks).transform(tracks)
    k = Knowledge(tracks, records)
    ranked = hybrid_recommend(embeddings, k, 1, ["sample", "backing"], [], limit=3)
    assert ranked.index[0] == 2 and 1 not in ranked.index
    avoided = hybrid_recommend(embeddings, k, 1, ["vocals"], ["sample"], limit=39)
    assert avoided.index.get_loc(2) > avoided.index.get_loc(4)
    text = hybrid_recommend(embeddings, k, 1, ["sample"], [], text="gospel sample", limit=3)
    assert 3 in text.index[:2]


def test_background_vocals_are_not_lead_vocals():
    liked, _ = parse_preferences("the sample and background vocals", ["vocals", "sample", "backing"])
    assert liked == ["sample", "backing"]
    assert "vocals" in parse_preferences("the rapping", ["vocals"])[0]
