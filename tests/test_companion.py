import random

from nora.nora_companion import mood_summary, reaction, reaction_details
from nora.nora_store import NoraStore


def test_reactions_are_bounded_and_map_to_pet_emotions(tmp_path):
    store = NoraStore(tmp_path / "state.json")
    line, emotion, delta = reaction_details("coffee", random.Random(1))
    assert "Kahve" in line and emotion in {
        "happy",
        "surprised",
        "love",
        "thinking",
        "sleepy",
        "sad",
        "angry",
        "smug",
    }
    assert delta > 0
    state = store.record_companion("coffee", affection_delta=delta, mood=emotion)
    assert state["affection"] == 22
    summary = mood_summary(state, "Kaan")
    assert "bağlılık 22/100" in summary and "Kaan" in summary
    assert reaction("unknown")


def test_affection_level_labels():
    assert "yeni arkadaş" in mood_summary({"affection": 1, "mood": "happy"})
    assert "çok yakın dost" in mood_summary({"affection": 100, "mood": "loved"})
