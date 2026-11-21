import pytest

from nora.nora_local_search import format_results, search_store
from nora.nora_store import NoraStore


def test_local_search_matches_turkish_fuzzy_and_scope(tmp_path):
    store = NoraStore(tmp_path / "state.json")
    store.add_note("Kahve çekirdeği almayı unutma")
    store.remember("kahvem", "şekersiz")
    store.add_task("raporu bitir")
    results = search_store(store, "kahve", scope="all")
    assert results and results[0]["score"] >= 0.7
    assert any(item["kind"] == "hafıza" for item in results)
    assert search_store(store, "kahve", scope="tasks") == []
    fuzzy = search_store(store, "kahvem", scope="memories")
    assert fuzzy and fuzzy[0]["id"] == "kahvem"
    assert "yerel not/hafıza/görevlerde" in format_results("yok", [])
    with pytest.raises(ValueError):
        search_store(store, "x", scope="files")


def test_local_search_does_not_index_arbitrary_text(tmp_path):
    store = NoraStore(tmp_path / "state.json")
    assert search_store(store, "gizli pano metni") == []
    assert search_store(store, "") == []
