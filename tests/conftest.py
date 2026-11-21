import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolated_nora_data(tmp_path_factory):
    """Never read/write the real user's notes, preferences or model cache in tests."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("NORA_DATA_DIR", str(tmp_path_factory.mktemp("nora-data")))
        yield


@pytest.fixture(scope="session")
def qapp():
    """Offscreen QApplication; skipped when Qt GUI libraries are unavailable."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PyQt5.QtWidgets")
    app = widgets.QApplication.instance() or widgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)
    yield app


@pytest.fixture(autouse=True)
def _clear_session_groq_key():
    """Never let a test's API key leak into the next one — or the real keyring.

    Windows runners have a working Credential Manager backend, so a test that
    saves a fake key would otherwise persist it in the OS and break every later
    "no key configured" test.
    """
    try:
        from nora import nora_secrets
    except Exception:
        yield
        return
    nora_secrets._session_key = ""
    real_keyring = nora_secrets._keyring
    nora_secrets._keyring = lambda: None
    try:
        yield
    finally:
        nora_secrets._keyring = real_keyring
        nora_secrets._session_key = ""


@pytest.fixture(autouse=True)
def _no_real_spotify_deep_link(monkeypatch):
    """Never hand a spotify: URI to the real OS while testing.

    Windows/macOS register a ``spotify:`` handler, so an unpatched test would
    launch (or attempt to launch) the desktop app on a contributor's machine.
    Tests that assert the deep-link behaviour patch it again themselves.
    """
    try:
        from nora.nora_ui import NoraApp
    except Exception:
        yield
        return
    original = NoraApp.__dict__.get("_open_spotify_deep_link")
    if original is not None:
        NoraApp._real_open_spotify_deep_link = original
    monkeypatch.setattr(
        NoraApp, "_open_spotify_deep_link", lambda self, query: False, raising=False
    )
    yield
