from nora.nora_clipboard import ClipboardHistory, looks_sensitive


def test_clipboard_history_is_bounded_expiring_and_session_only(qapp):
    current = [1000.0]
    written = []
    history = ClipboardHistory(writer=written.append, clock=lambda: current[0])
    assert history.record("ilk metin")
    assert not history.record("ilk metin")
    for index in range(25):
        assert history.record(f"kayıt {index}")
    assert len(history.entries) == 20
    assert history.entries[0]["text"] == "kayıt 24"
    assert "kayıt 24" in history.listing()
    history.copy("1")
    assert written == ["kayıt 24"]
    assert history.delete("1")
    current[0] += 1801
    assert history.entries == []
    history.stop()


def test_clipboard_skips_obvious_secrets_and_long_text(qapp):
    history = ClipboardHistory()
    for text in (
        "password=supersecret123",
        "parola: abc123",
        "-----BEGIN PRIVATE KEY-----\nabc",
        "gsk_abcdefghijklmnopqrstuvwx",
        "4111 1111 1111 1111",
        "otp: 123456",
        "x" * 4001,
    ):
        assert not history.record(text), text
        assert history.entries == []
    assert looks_sensitive("api_key=abcdef123456")
    assert not looks_sensitive("kahve şekersiz")
    history.stop()


def test_manual_capture_uses_reader_without_watcher(qapp):
    history = ClipboardHistory(reader=lambda: "manuel kayıt")
    assert not history.active
    assert history.capture_current()
    assert history.entries[0]["text"] == "manuel kayıt"
    history.clear()
    assert history.entries == []
    history.stop()
