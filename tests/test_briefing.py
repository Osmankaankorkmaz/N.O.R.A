from datetime import timedelta

from nora.nora_briefing import daily_summary, morning_briefing, weekly_plan
from nora.nora_store import NoraStore, now_local


def test_briefings_use_only_local_store(tmp_path):
    store = NoraStore(tmp_path / "state.json")
    now = now_local()
    store.add_task("raporu bitir")
    done = store.add_task("kahve al")
    store.complete_task(done["id"])
    store.add_note("bugün fikir: yerel arama")
    store.add_reminder("su iç", now + timedelta(minutes=30))
    morning = morning_briefing(store, now)
    assert "Günaydın" in morning
    assert "raporu bitir" in morning
    assert "Açık görev: 1" in morning
    summary = daily_summary(store, now)
    assert "Bugün tamamlanan görev: 1" in summary
    assert "kahve al" in summary
    assert "Bugün eklenen not: 1" in summary
    weekly = weekly_plan(store, now)
    assert "Haftalık odak planı" in weekly
    assert "1. öncelik: raporu bitir" in weekly
