from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.data import synthetic_features


def test_app_feedback_and_aspect_validation(tmp_path, monkeypatch):
    path = tmp_path / "features.csv"
    synthetic_features(60).to_csv(path)
    monkeypatch.setenv("SONG_FEATURES", str(path))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    assert not app.exception
    assert len(app.dataframe[0].value) == 10
    assert app.toggle(key="like_tempo").disabled
    first = app.dataframe[0].value.index[0]
    app.button(key=f"up_{first}").click().run()
    assert not app.exception
    assert app.session_state.feedback[first] is True
    assert first not in app.dataframe[0].value.index
    app.button(key=f"replace_{first}").click().run()
    assert app.session_state.feedback[first] is False
    next(button for button in app.button if button.label == "Clear song feedback").click().run()
    assert not app.session_state.feedback
    app.toggle(key="dislike_melody").set_value(True).run()
    assert any("either like or dislike" in item.value for item in app.warning)
    assert not app.exception
    app.toggle(key="like_melody").set_value(False).run()
    assert len(app.dataframe[0].value) == 10
    app.toggle(key="dislike_melody").set_value(False).run()
    assert any("Select at least" in item.value for item in app.info)


def test_missing_catalog_is_actionable(tmp_path, monkeypatch):
    monkeypatch.setenv("SONG_FEATURES", str(tmp_path / "missing.csv"))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    assert not app.exception
    assert "python -m src.data" in app.error[0].value
