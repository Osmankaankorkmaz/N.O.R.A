from nora.nora_store import NoraStore


def test_companion_state_persists_and_clamps(tmp_path):
    path = tmp_path / "state.json"
    store = NoraStore(path)
    assert store.companion_state["affection"] == 20
    state = store.record_companion("coffee", affection_delta=500, mood="excited")
    assert state["affection"] == 100
    state = store.record_companion("miss", affection_delta=-500, mood="lonely")
    assert state["affection"] == 0
    reopened = NoraStore(path)
    assert reopened.companion_state["mood"] == "lonely"
    assert reopened.companion_state["last_event"] == "miss"


def test_audit_log_is_bounded_gated_and_clearable(tmp_path):
    store = NoraStore(tmp_path / "state.json")
    for index in range(205):
        store.add_audit("command", f"işlem {index}")
    assert len(store.audit_log) == 200
    assert store.audit_log[-1]["detail"] == "işlem 204"
    store.clear_audit()
    assert store.audit_log == []
    store.set_preference("audit_log", False)
    store.add_audit("command", "kayıt kapalı")
    assert store.audit_log == []


def test_export_is_deep_copy_and_completed_at_tracks_done(tmp_path):
    store = NoraStore(tmp_path / "state.json")
    task = store.add_task("raporu bitir")
    store.complete_task(task["id"])
    assert store.tasks[0]["completed_at"]
    store.complete_task(task["id"], False)
    assert "completed_at" not in store.tasks[0]
    store.remember("kahve", "şekersiz")
    exported = store.export_data()
    exported["memories"]["kahve"]["value"] = "değiştirildi"
    assert store.memories["kahve"]["value"] == "şekersiz"
    assert exported["version"] == 1
