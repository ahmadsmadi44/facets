from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.data import synthetic_features
from src.intent import parse_preferences


def run(tmp_path, monkeypatch, rows=60):
    path = tmp_path / "features.csv"
    synthetic_features(rows).to_csv(path)
    monkeypatch.setenv("SONG_FEATURES", str(path))
    return AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)


def vote_buttons(app, prefix="up_"):
    return [b for b in app.button if b.key and b.key.startswith(prefix)]


def test_parse_text_into_liked_and_disliked_aspects():
    liked, _ = parse_preferences("the dancehall beat with the rapping")
    assert {"rhythm", "tempo", "drums", "vocals"} <= set(liked)
    liked, disliked = parse_preferences("the melody but not the drums")
    assert "melody" in liked and disliked == ["drums"]
    assert parse_preferences("zzz") == ([], [])
    assert parse_preferences("the beat", available=["vocals"]) == ([], [])


def test_pick_aspects_then_feedback(tmp_path, monkeypatch):
    app = run(tmp_path, monkeypatch)
    assert not app.exception
    assert any("at least one" in item.value for item in app.info)
    app.pills(key="likes").set_value(["vocals", "rhythm"]).run()
    assert not app.exception
    ups = vote_buttons(app)
    assert len(ups) == 10
    track = ups[0].key[3:]
    ups[0].click().run()
    assert app.session_state.feedback[int(track)] is True
    assert f"up_{track}" not in [b.key for b in app.button]


def test_describe_mode_shows_understanding(tmp_path, monkeypatch):
    app = run(tmp_path, monkeypatch)
    app.segmented_control(key="mode").set_value("Describe it").run()
    app.text_area(key="text").set_value("I love the rapping and the beat").run()
    assert not app.exception
    assert any("I understood" in item.value for item in app.caption)
    assert len(vote_buttons(app)) == 10


def test_missing_catalog_is_actionable(tmp_path, monkeypatch):
    monkeypatch.setenv("SONG_FEATURES", str(tmp_path / "missing.csv"))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    assert not app.exception
    assert "python -m src.catalog" in app.error[0].value
