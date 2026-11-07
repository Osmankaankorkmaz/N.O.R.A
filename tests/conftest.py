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
