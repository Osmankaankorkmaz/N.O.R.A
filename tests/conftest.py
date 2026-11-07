import os

import pytest


@pytest.fixture(scope="session")
def qapp():
    """Offscreen QApplication; skipped when Qt GUI libraries are unavailable."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PyQt5.QtWidgets")
    app = widgets.QApplication.instance() or widgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)
    yield app
